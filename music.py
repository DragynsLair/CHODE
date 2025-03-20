import discord
import asyncio
from chode import utils
import yt_dlp as youtube_dl
import random

# Global dictionaries for music queue, history, and control messages.
music_queues = {}            # Key: guild.id, Value: list of song queries
music_history = {}           # Key: guild.id, Value: list of previously played song queries
music_control_messages = {}  # Key: guild.id, Value: message ID of the current control message

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as e:
            print(f"[DEBUG] Error extracting info: {e}")
            raise e
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

async def play_song(ctx, query: str):
    """Plays the song immediately and sets up a control message with reaction controls."""
    vc = ctx.voice_client
    guild_id = ctx.guild.id
    # If a song is currently playing, push it to history.
    if vc and vc.source and hasattr(vc.source, "data"):
        music_history.setdefault(guild_id, []).append(vc.source.data.get("webpage_url", ""))
    try:
        player = await YTDLSource.from_url(query, loop=ctx.bot.loop, stream=True)
    except Exception as e:
        await ctx.send("Error retrieving audio. Please try a different query.")
        print(f"[DEBUG] Error in YTDLSource.from_url: {e}")
        return

    async def after_playing(error):
        if error:
            print(f"[DEBUG] Player error: {error}")
        # Note: We now explicitly call play_next in next_command.
        # The after callback can be used for logging or additional cleanup.
        print("[DEBUG] after_playing callback triggered.")

    vc.play(player, after=after_playing)
    # Send a control message with reaction buttons.
    control_msg = await ctx.send(f"Now playing: {player.title} - {player.data.get('webpage_url', 'No URL')}")
    await control_msg.add_reaction("⏮")  # Previous
    await control_msg.add_reaction("⏯")  # Pause/Resume
    await control_msg.add_reaction("⏭")  # Next
    music_control_messages[guild_id] = control_msg.id
    music_history.setdefault(guild_id, []).append(query)

async def play_next(ctx):
    """Plays the next song from the queue if available; otherwise disconnects."""
    guild_id = ctx.guild.id
    if guild_id in music_queues and music_queues[guild_id]:
        next_query = music_queues[guild_id].pop(0)
        await ctx.send(f"Now playing next song: {next_query}")
        await play_song(ctx, next_query)
    else:
        vc = ctx.voice_client
        if vc and vc.is_connected():
            await ctx.send("No more songs in the queue. Disconnecting from voice channel.")
            await vc.disconnect()

async def prev_command(ctx):
    """Plays the previous song from history, if available."""
    guild_id = ctx.guild.id
    if guild_id in music_history and music_history[guild_id]:
        prev_query = music_history[guild_id].pop()
        await ctx.send(f"Now playing previous song: {prev_query}")
        await play_song(ctx, prev_query)
    else:
        await ctx.send("No previous song found.")

async def pause_command(ctx):
    """Toggles pause/resume on the current song."""
    vc = ctx.voice_client
    if not vc:
        await ctx.send("I'm not connected to a voice channel!")
        return
    if vc.is_playing():
        vc.pause()
        await ctx.send("Paused the song.")
    elif vc.is_paused():
        vc.resume()
        await ctx.send("Resumed the song.")

async def play_command(ctx, query: str):
    """Handles play command; if a song is already playing, adds to the queue."""
    vc = ctx.voice_client
    if vc.is_playing() or vc.is_paused():
        guild_id = ctx.guild.id
        music_queues.setdefault(guild_id, []).append(query)
        await ctx.send("Song added to the queue!")
    else:
        await play_song(ctx, query)

async def next_command(ctx):
    """Skips to the next song and starts playback immediately."""
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        await ctx.send("I'm not connected to a voice channel!")
        return
    if vc.is_playing() or vc.is_paused():
        vc.stop()  # Stop current song.
        await ctx.send("Skipping to the next song...")
        # Explicitly call play_next to start the next song.
        await play_next(ctx)
    else:
        await ctx.send("There is no song playing right now.")

async def stop_command(ctx):
    """Stops the current song, clears the queue, and disconnects from the voice channel."""
    vc = ctx.voice_client
    if not vc:
        await ctx.send("I'm not connected to a voice channel!")
        return
    if vc.source and hasattr(vc.source, "data"):
        song_url = vc.source.data.get("webpage_url", "URL not found")
        await ctx.send(f"Stopping the song. Here is the link: {song_url}")
    else:
        await ctx.send("No song is currently playing.")
    music_queues[ctx.guild.id] = []
    vc.stop()
    await vc.disconnect()
