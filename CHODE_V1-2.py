/*
 * MIT License
 * 
 * Copyright (c) [2025] BIZZOMEPHISTO
 * 
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * 
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */


import discord
from discord.ext import commands
import sqlite3
import json
import datetime
import uuid
import urllib.request
import urllib.parse
import websocket  # Requires the websocket-client package
import io
import asyncio
import requests
import os
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import time

# ==========================
# Helper Functions for Time Formatting
# ==========================
def ordinal(n):
    """Return an ordinal string of a number (e.g., 1 -> '1st', 2 -> '2nd')."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def format_timestamp(timestamp_str):
    """Convert an ISO timestamp string to a simplified format like 'Saturday the 8th of feb'."""
    ts = datetime.datetime.fromisoformat(timestamp_str)
    return f"{ts.strftime('%A')} the {ordinal(ts.day)} of {ts.strftime('%b').lower()}"

# ==========================
# Helper Function for Sending Long Messages
# ==========================
async def send_long_message(channel, message):
    """Send a message in chunks if it exceeds 2000 characters."""
    for i in range(0, len(message), 2000):
        await channel.send(message[i:i+2000])

# ==========================
# Helper Function to Reword Prompts (80 tokens)
# ==========================
def reword_prompt(prompt: str, max_tokens=80) -> str:
    """
    Reword the given prompt to be more descriptive and detailed,
    while keeping it to roughly max_tokens tokens.
    Uses LMStudio's chat completions endpoint.
    """
    custom_system = (
        f"Reword the following prompt to be more descriptive and detailed, "
        f"while keeping it to approximately {max_tokens} tokens. Return only the reworded prompt."
    )
    new_prompt = chat_completion(prompt, system_message=custom_system)
    return new_prompt.strip()

# ==========================
# Helper Function to Add Reaction if Interesting
# (Now using message.add_reaction with a 10% chance)
# ==========================
async def add_reaction_if_interesting(message: discord.Message):
    """
    Uses LMStudio to decide if a message is interesting and, if so,
    adds a reaction emoji that best fits the message.
    This function only proceeds with a 10% chance.
    """
    if random.random() > 0.1:
        return
    if len(message.content) < 5:
        return
    prompt = (f"Given the following message:\n\"{message.content}\"\n"
              "Suggest one reaction emoji that best expresses an appropriate reaction to this message. "
              "If the message is not interesting, reply with 'none'. Return only the emoji or 'none'.")
    reaction = await asyncio.to_thread(call_lmstudio, prompt)
    reaction = reaction.strip()
    if reaction.lower() != "none" and reaction:
        try:
            await message.add_reaction(reaction)
        except Exception as e:
            print(f"[DEBUG] Error adding reaction: {e}")

# ==========================
# Load Environment Variables
# ==========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    raise ValueError("Discord token not found in environment variables. Check your .env file.")

# ==========================
# Database Setup (SQLite)
# ==========================
conn = sqlite3.connect("memories.db")
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT,
    channel_id TEXT,
    user_id TEXT,
    message TEXT,
    timestamp TEXT
)''')
conn.commit()

def store_memory(server_id, channel_id, user_id, message):
    """Store a message in the local database for long-term memory."""
    timestamp = datetime.datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO memories (server_id, channel_id, user_id, message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (str(server_id), str(channel_id), str(user_id), message, timestamp)
    )
    conn.commit()

def get_recent_conversation(server_id, channel_id, limit=10):
    """
    Retrieve the most recent conversation history from the database.
    Returns a formatted string of messages (oldest first) with simplified timestamps.
    """
    c.execute(
        "SELECT user_id, message, timestamp FROM memories WHERE server_id=? AND channel_id=? ORDER BY timestamp DESC LIMIT ?",
        (str(server_id), str(channel_id), limit)
    )
    rows = c.fetchall()
    conversation = ""
    for row in reversed(rows):
        formatted_ts = format_timestamp(row[2])
        conversation += f"User {row[0]} at {formatted_ts}: {row[1]}\n"
    return conversation

# ==========================
# Server Configuration Storage
# ==========================
def load_server_config(server_id):
    """Load configuration for a given server from a JSON file."""
    try:
        with open(f"config_{server_id}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_server_config(server_id, config):
    """Save configuration for a given server to a JSON file."""
    with open(f"config_{server_id}.json", "w") as f:
        json.dump(config, f, indent=4)

# ==========================
# ComfyUI Integration Functions
# ==========================
SERVER_ADDRESS = "127.0.0.1:8188"

def queue_prompt(prompt):
    """Queue the prompt for processing in ComfyUI."""
    client_id = str(uuid.uuid4())
    payload = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"http://{SERVER_ADDRESS}/prompt", data=data)
    result = json.loads(urllib.request.urlopen(req).read())
    print(f"[DEBUG] queue_prompt result: {result}")
    return result

def get_image(filename, subfolder, folder_type):
    """Retrieve an image from ComfyUI using the /view endpoint."""
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/view?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    """Retrieve prompt execution history from ComfyUI."""
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/history/{prompt_id}") as response:
        history = json.loads(response.read())
        print(f"[DEBUG] get_history for prompt_id {prompt_id}: {history}")
        return history

def generate_and_send_images(prompt_text: str, ctx):
    """
    Generates images using a local ComfyUI workflow defined in flux.json and streams
    them to Discord as soon as each image finishes.
    A random seed is injected into the workflow.
    Images are sent immediately upon receiving a queue update indicating one image is done.
    """
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

        ws.settimeout(20)
        processed_nodes = set()
        while True:
            try:
                out = ws.recv()
                print(f"[DEBUG] Received websocket message: {out}")
            except Exception as e:
                print(f"[DEBUG] Websocket error or timeout: {e}")
                break

            try:
                msg = json.loads(out)
            except Exception as e:
                print(f"[DEBUG] Error parsing JSON: {e}")
                continue

            if msg.get("type") == "queue_update" and msg.get("delta") == -1:
                history = get_history(prompt_id)
                outputs = history.get(prompt_id, {}).get("outputs", {})
                for node_id, node_output in outputs.items():
                    if node_id not in processed_nodes:
                        for image in node_output.get("images", []):
                            try:
                                img_data = get_image(image["filename"], image["subfolder"], image["type"])
                            except Exception as e:
                                print(f"[DEBUG] Error downloading image for node {node_id}: {e}")
                                continue
                            print(f"[DEBUG] Image for node {node_id} downloaded, sending to Discord...")
                            send_future = asyncio.run_coroutine_threadsafe(
                                ctx.send(content=f"{ctx.author.mention}", file=discord.File(fp=io.BytesIO(img_data), filename=f"image_{node_id}.png")),
                                bot.loop
                            )
                            try:
                                send_future.result(timeout=10)
                            except Exception as e:
                                print(f"[DEBUG] Error sending image for node {node_id} to Discord: {e}")
                        processed_nodes.add(node_id)
            if msg.get("type") == "executing":
                data = msg.get("data", {})
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    print("[DEBUG] Overall execution complete message received.")
                    break

        history = get_history(prompt_id)
        outputs = history.get(prompt_id, {}).get("outputs", {})
        for node_id, node_output in outputs.items():
            if node_id not in processed_nodes:
                for image in node_output.get("images", []):
                    try:
                        img_data = get_image(image["filename"], image["subfolder"], image["type"])
                    except Exception as e:
                        print(f"[DEBUG] Error downloading image for node {node_id}: {e}")
                        continue
                    print(f"[DEBUG] Final image for node {node_id} downloaded, sending to Discord...")
                    send_future = asyncio.run_coroutine_threadsafe(
                        ctx.send(content=f"{ctx.author.mention}", file=discord.File(fp=io.BytesIO(img_data), filename=f"image_{node_id}.png")),
                        bot.loop
                    )
                    try:
                        send_future.result(timeout=10)
                    except Exception as e:
                        print(f"[DEBUG] Error sending image for node {node_id} to Discord: {e}")
                processed_nodes.add(node_id)
    except Exception as e:
        ws.close()
        raise Exception(f"Error during image generation: {e}")
    ws.close()

# ==========================
# LMStudio Integration Functions
# ==========================
LMSTUDIO_URL = "http://127.0.0.1:1234"

def list_models():
    """List available models from LMStudio."""
    url = f"{LMSTUDIO_URL}/v1/models"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return f"Error fetching models: {e}"

def chat_completion(prompt: str, system_message: str = "You are chode the chatbot.") -> str:
    """
    Use the LMStudio chat completions endpoint to generate a chat-based response.
    """
    url = f"{LMSTUDIO_URL}/v1/chat/completions"
    payload = {
        "model": "default",
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error communicating with LMStudio: {e}"

def text_completion(prompt: str) -> str:
    """Use the LMStudio completions endpoint to generate text."""
    url = f"{LMSTUDIO_URL}/v1/completions"
    payload = {
        "model": "default",
        "prompt": prompt,
        "max_tokens": 150
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["text"]
    except Exception as e:
        return f"Error communicating with LMStudio: {e}"

def get_embeddings(text: str):
    """Retrieve embeddings using LMStudio."""
    url = f"{LMSTUDIO_URL}/v1/embeddings"
    payload = {
        "model": "default",
        "input": text
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("data")
    except Exception as e:
        return f"Error communicating with LMStudio: {e}"

def call_lmstudio(prompt: str) -> str:
    """Calls LMStudio's chat completion endpoint."""
    return chat_completion(prompt)

# ==========================
# Discord Bot Setup
# ==========================
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix="!!", intents=intents)

# Command: chodehelp
@bot.command(name="chodehelp")
async def chodehelp(ctx):
    """
    Send the contents of 'whatsnew.txt' to LMStudio as a prompt so that Chode
    returns the new features exactly as provided.
    """
    try:
        with open("whatsnew.txt", "r") as f:
            content = f.read()
    except Exception as e:
        await ctx.send("Error: 'whatsnew.txt' could not be read.")
        return
    system_message = "Return the following text exactly as is, without any modifications."
    response_text = await asyncio.to_thread(call_lmstudio, content + "\n\n" + system_message)
    if len(response_text) > 2000:
        await send_long_message(ctx.channel, response_text)
    else:
        await ctx.send(response_text)

@bot.command(name="setup")
async def setup(ctx, *, personality: str):
    """
    Set the bot's personality for this server.
    Only the server owner or a user with the CHODEADMIN role can use this command.
    The personality is unique to this server.
    """
    if ctx.guild and (ctx.author == ctx.guild.owner or any(role.name == "CHODEADMIN" for role in ctx.author.roles)):
        config = load_server_config(ctx.guild.id)
        config["personality"] = personality
        save_server_config(ctx.guild.id, config)
        await ctx.send("Personality has been updated!")
    else:
        await ctx.send("You do not have permission to use this command here.")

@bot.command(name="genimg")
async def genimg(ctx, *, prompt: str):
    """Generate an image using the local ComfyUI installation and send it immediately when ready."""
    print(f"[DEBUG] genimg command triggered with prompt: {prompt}")
    final_prompt = prompt
    # Check if the prompt ends with "++" to trigger rewording.
    if prompt.strip().endswith("++"):
        final_prompt = prompt.strip()[:-2].strip()
        final_prompt = reword_prompt(final_prompt)
    elif "make this prompt better" in prompt.lower():
        final_prompt = reword_prompt(prompt)
    await ctx.send(f"Image generation started. Prompt used: {final_prompt}")
    try:
        await asyncio.to_thread(generate_and_send_images, final_prompt, ctx)
    except Exception as e:
        await ctx.send(f"Error generating image: {e}")
        print(f"[DEBUG] Error in genimg command: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Determine a unique server identifier.
    if message.guild:
        server_id = str(message.guild.id)
    else:
        server_id = f"DM-{message.author.id}"
    
    # Store the message in the database.
    store_memory(server_id, message.channel.id, message.author.id, message.content)

    # Process commands (they start with "!!")
    if message.content.startswith("!!"):
        await bot.process_commands(message)
        return

    # For DMs, automatically process the message as an LLM prompt.
    if message.guild is None:
        conversation_history = get_recent_conversation(server_id, message.channel.id, limit=10)
        prompt_for_llm = (
            f"Conversation History:\n{conversation_history}\n"
            f"User {message.author.name} said: {message.content}\n"
            f"Respond as chode:"
        )
        async with message.channel.typing():
            response_text = await asyncio.to_thread(call_lmstudio, prompt_for_llm)
        if len(response_text) > 2000:
            await send_long_message(message.channel, response_text)
        else:
            await message.channel.send(response_text)
        return

    # For guild messages that mention the bot:
    if bot.user in message.mentions:
        content_lower = message.content.lower()
        ctx_obj = await bot.get_context(message)
        # Check if the message requests image generation via mention.
        if ("generate" in content_lower and any(word in content_lower for word in ["photo", "image", "picture"])):
            new_prompt = message.clean_content.replace(bot.user.mention, "").strip()
            final_prompt = new_prompt
            if new_prompt.strip().endswith("++"):
                final_prompt = new_prompt.strip()[:-2].strip()
                final_prompt = reword_prompt(final_prompt)
            elif "make this prompt better" in new_prompt.lower():
                final_prompt = reword_prompt(new_prompt)
            await message.channel.send(f"Image generation started. Prompt used: {final_prompt}")
            await asyncio.to_thread(generate_and_send_images, final_prompt, ctx_obj)
            return
        elif "what server" in content_lower:
            prompt_for_llm = (
                f"The user asked: '{message.content}'. The server details are as follows: "
                f"Name: {message.guild.name}, ID: {message.guild.id}, and there are {message.guild.member_count} members. "
                f"Respond in your own words as Chode."
            )
        else:
            conversation_history = get_recent_conversation(message.guild.id, message.channel.id, limit=10)
            server_info = (
                f"Server Name: {message.guild.name}, "
                f"Server ID: {message.guild.id}, "
                f"Member Count: {message.guild.member_count}"
            )
            config = load_server_config(message.guild.id)
            personality = config.get("personality", "You are chode, a friendly chatbot.")
            prompt_for_llm = (
                f"Server Info: {server_info}\n"
                f"Conversation History:\n{conversation_history}\n"
                f"User {message.author.name} said: {message.content}\n"
                f"Respond as chode:"
            )
        async with message.channel.typing():
            response_text = await asyncio.to_thread(call_lmstudio, prompt_for_llm)
        if len(response_text) > 2000:
            await send_long_message(message.channel, response_text)
        else:
            await message.channel.send(response_text)
        return
    else:
        # For non-command guild messages that do not mention the bot, add a reaction if interesting.
        asyncio.create_task(add_reaction_if_interesting(message))
        await bot.process_commands(message)

bot.run(TOKEN)
