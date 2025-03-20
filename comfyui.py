import json
import urllib.request
import urllib.parse
import uuid
import websocket
import random
import asyncio
import io
import time
import discord

SERVER_ADDRESS = "127.0.0.1:8188"

def queue_prompt(prompt):
    client_id = str(uuid.uuid4())
    payload = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://{SERVER_ADDRESS}/prompt", data=data)
    result = json.loads(urllib.request.urlopen(req).read())
    return result

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/view?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/history/{prompt_id}") as response:
        history = json.loads(response.read())
        print(f"[DEBUG] get_history for prompt_id {prompt_id}: {history}")
        return history

def generate_and_send_images(prompt_text: str, ctx):
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    try:
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={client_id}")
        print(f"[DEBUG] Connected to ComfyUI websocket with client_id {client_id}")
    except Exception as e:
        raise Exception(f"Failed to connect to ComfyUI websocket: {e}")
    
    try:
        with open("flux.json", "r") as f:
            workflow = json.load(f)
        print("[DEBUG] Loaded flux.json successfully.")
    except Exception as e:
        ws.close()
        raise Exception(f"Failed to load flux.json: {e}")
    
    if "6" in workflow and "inputs" in workflow["6"]:
        workflow["6"]["inputs"]["text"] = prompt_text
        print(f"[DEBUG] Updated flux.json node '6' prompt with: {prompt_text}")
    else:
        ws.close()
        raise Exception("flux.json does not contain a valid prompt node '6'.")
    
    random_seed = random.randint(0, 2**32 - 1)
    if "31" in workflow and "inputs" in workflow["31"]:
        workflow["31"]["inputs"]["seed"] = random_seed
        print(f"[DEBUG] Updated flux.json node '31' seed with: {random_seed}")
    else:
        print("[DEBUG] No valid seed node ('31') found in flux.json; skipping seed update.")
    
    try:
        result = queue_prompt(workflow)
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise Exception("No prompt_id returned from queue_prompt")
        print(f"[DEBUG] Prompt queued with id: {prompt_id}")
    except Exception as e:
        ws.close()
        raise Exception(f"Error during image generation: {e}")
    
    ws.settimeout(30)
    processed_nodes = set()
    # We'll break the loop if no new update is received for 5 seconds.
    last_update = time.time()
    while True:
        try:
            out = ws.recv()
            print(f"[DEBUG] Received websocket message: {out}")
            last_update = time.time()  # update timestamp on every successful recv
        except Exception as e:
            print(f"[DEBUG] Websocket error or timeout: {e}")
            # If we haven't seen an update for over 5 seconds, break the loop.
            if time.time() - last_update > 5:
                break
            continue

        try:
            msg = json.loads(out)
        except Exception as e:
            print(f"[DEBUG] Error parsing JSON: {e}")
            continue

        # Check for queue_update messages.
        if msg.get("type") == "queue_update" and msg.get("delta") == -1:
            history = get_history(prompt_id)
            outputs = history.get(prompt_id, {}).get("outputs", {})
            for node_id, node_output in outputs.items():
                if node_id not in processed_nodes:
                    for image in node_output.get("images", []):
                        try:
                            img_data = get_image(image["filename"], image["subfolder"], image["type"])
                            print(f"[DEBUG] Sending image for node {node_id}")
                        except Exception as e:
                            print(f"[DEBUG] Error downloading image for node {node_id}: {e}")
                            continue
                        future = asyncio.run_coroutine_threadsafe(
                            ctx.send(
                                content=f"{ctx.author.mention}",
                                file=discord.File(fp=io.BytesIO(img_data), filename=f"image_{node_id}.png")
                            ),
                            ctx.bot.loop
                        )
                        try:
                            future.result(timeout=10)
                        except Exception as e:
                            print(f"[DEBUG] Error sending image for node {node_id} to Discord: {e}")
                    processed_nodes.add(node_id)
        
        # Optionally, if you detect a final execution message, break out.
        if msg.get("type") == "executing":
            data = msg.get("data", {})
            if data.get("node") is None and data.get("prompt_id") == prompt_id:
                print("[DEBUG] Overall execution complete message received.")
                break

        # Also, if no new message received for >5 seconds, break.
        if time.time() - last_update > 5:
            print("[DEBUG] No new updates received for 5 seconds, breaking loop.")
            break

    # Process any remaining nodes.
    history = get_history(prompt_id)
    outputs = history.get(prompt_id, {}).get("outputs", {})
    for node_id, node_output in outputs.items():
        if node_id not in processed_nodes:
            for image in node_output.get("images", []):
                try:
                    img_data = get_image(image["filename"], image["subfolder"], image["type"])
                    print(f"[DEBUG] Sending final image for node {node_id}")
                except Exception as e:
                    print(f"[DEBUG] Error downloading image for node {node_id}: {e}")
                    continue
                future = asyncio.run_coroutine_threadsafe(
                    ctx.send(
                        content=f"{ctx.author.mention}",
                        file=discord.File(fp=io.BytesIO(img_data), filename=f"image_{node_id}.png")
                    ),
                    ctx.bot.loop
                )
                try:
                    future.result(timeout=10)
                except Exception as e:
                    print(f"[DEBUG] Error sending image for node {node_id} to Discord: {e}")
            processed_nodes.add(node_id)
    ws.close()
