import discord
import asyncio
from chode.lmstudio import call_lmstudio

def ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def format_timestamp(timestamp_str):
    import datetime
    ts = datetime.datetime.fromisoformat(timestamp_str)
    return f"{ts.strftime('%A')} the {ordinal(ts.day)} of {ts.strftime('%b').lower()}"

async def send_long_message(channel, message):
    for i in range(0, len(message), 2000):
        await channel.send(message[i:i+2000])

def reword_prompt(prompt: str, max_tokens=80) -> str:
    custom_system = (
        f"Reword the following prompt to be more descriptive and detailed, "
        f"while keeping it to approximately {max_tokens} tokens. Return only the reworded prompt."
    )
    new_prompt = call_lmstudio(prompt + "\n\n" + custom_system)
    return new_prompt.strip()

def read_whatsnew():
    try:
        with open("whatsnew.txt", "r") as f:
            return f.read()
    except Exception as e:
        return "Error: 'whatsnew.txt' could not be read."
