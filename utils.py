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

async def add_reaction_if_interesting(message: discord.Message):
    import random
    # Only proceed with a 10% chance.
    if random.random() > 0.1:
        return
    if len(message.content) < 5:
        return
    prompt = (
        f"Given the following message:\n\"{message.content}\"\n"
        "Suggest one reaction emoji that best expresses an appropriate reaction to this message. "
        "If the message is not interesting, reply with 'none'. Return only the emoji or 'none'."
    )
    reaction = await asyncio.to_thread(call_lmstudio, prompt)
    reaction = reaction.strip()
    if reaction.lower() != "none" and reaction:
        try:
            await message.add_reaction(reaction)
        except Exception as e:
            print(f"[DEBUG] Error adding reaction: {e}")
def get_member_info(member: discord.Member) -> str:
    status = str(member.status)
    activities = []
    for activity in member.activities:
        if hasattr(activity, "name") and activity.name:
            activities.append(activity.name)
    if activities:
        activity_str = ", ".join(activities)
    else:
        activity_str = "not playing anything"
    return f"{member.display_name} is {status} and currently {activity_str}."
