import requests

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
