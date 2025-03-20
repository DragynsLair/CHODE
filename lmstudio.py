import requests
from chode import config

LMSTUDIO_URL = "http://127.0.0.1:1234"

def chat_completion(prompt: str, system_message: str = "You are chode the chatbot.") -> str:
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

def call_lmstudio(prompt: str) -> str:
    return chat_completion(prompt)

def call_lmstudio_with_personality(prompt: str, guild_id: str) -> str:
    # Attempt to load personality configuration for the given guild.
    try:
        conf = config.load_server_config(guild_id)
    except Exception as e:
        conf = {}
    # Use a default personality if none is found.
    personality = conf.get("personality", "You are chode, a friendly chatbot.")
    # Use the personality as the system message.
    return chat_completion(prompt, system_message=personality)
