import asyncio
import discord
from discord.ext import commands
from chode import config, database, lmstudio, comfyui, music, utils

def setup_commands(bot):
    @bot.command(name="chodehelp")
    async def chodehelp(ctx):
        content = utils.read_whatsnew()
        # Use a default system message for help.
        system_message = "Return the following text exactly as is, without any modifications."
        response_text = await asyncio.to_thread(lmstudio.call_lmstudio, content + "\n\n" + system_message)
        if len(response_text) > 2000:
            await utils.send_long_message(ctx.channel, response_text)
        else:
            await ctx.send(response_text)

    @bot.command(name="setup")
    async def setup(ctx, *, personality: str):
        if ctx.guild and (ctx.author == ctx.guild.owner or any(role.name == "CHODEADMIN" for role in ctx.author.roles)):
            conf = config.load_server_config(ctx.guild.id)
            conf["personality"] = personality
            config.save_server_config(ctx.guild.id, conf)
            await ctx.send("Personality has been updated!")
        else:
            await ctx.send("You do not have permission to use this command here.")

    @bot.command(name="genimg")
    async def genimg(ctx, *, prompt: str):
        final_prompt = prompt
        if prompt.strip().endswith("++"):
            await ctx.send("Hold on while I reword your prompt...")
            final_prompt = prompt.strip()[:-2].strip()
            final_prompt = utils.reword_prompt(final_prompt)
        elif "make this prompt better" in prompt.lower():
            final_prompt = utils.reword_prompt(prompt)
        await ctx.send(f"Image generation started. Prompt used: {final_prompt}")
        try:
            await asyncio.to_thread(comfyui.generate_and_send_images, final_prompt, ctx)
        except Exception as e:
            await ctx.send(f"Error generating image: {e}")
            print(f"[DEBUG] Error in genimg command: {e}")

    @bot.command(name="play")
    async def play(ctx, *, query: str):
        if not ctx.author.voice:
            await ctx.send("You are not connected to a voice channel!")
            return

        if not ctx.voice_client:
            try:
                await ctx.author.voice.channel.connect()
            except Exception as e:
                await ctx.send("Failed to connect to the voice channel.")
                print(f"[DEBUG] Voice connection error: {e}")
                return

        if not query.startswith("http"):
            query = f"ytsearch:{query}"

        await ctx.send("Searching for the song...")
        vc = ctx.voice_client
        if vc.is_playing() or vc.is_paused():
            guild_id = ctx.guild.id
            music.music_queues.setdefault(guild_id, []).append(query)
            await ctx.send("Song added to the queue!")
        else:
            await music.play_song(ctx, query)

    @bot.command(name="next")
    async def next_song(ctx):
        await music.next_command(ctx)

    @bot.command(name="prev")
    async def prev_song(ctx):
        await music.prev_command(ctx)

    @bot.command(name="pause")
    async def pause_song(ctx):
        await music.pause_command(ctx)

    @bot.command(name="stop")
    async def stop_song(ctx):
        await music.stop_command(ctx)

    @bot.event
    async def on_reaction_add(reaction, user):
        if user.bot:
            return
        message = reaction.message
        if not message.guild:
            return
        guild_id = message.guild.id
        if guild_id in music.music_control_messages and message.id == music.music_control_messages[guild_id]:
            ctx = await bot.get_context(message)
            emoji = reaction.emoji
            if emoji == "⏮":
                await prev_song(ctx)
            elif emoji == "⏯":
                await pause_song(ctx)
            elif emoji == "⏭":
                await next_song(ctx)
            try:
                await message.remove_reaction(emoji, user)
            except Exception:
                pass

    @bot.event
    async def on_message(message):
        # Ignore messages sent by the bot itself.
        if message.author == bot.user:
            return

        # Determine the server identifier.
        if message.guild:
            server_id = message.guild.id
            # Load personality for this server (default provided if missing).
            conf = config.load_server_config(server_id)
            personality = conf.get("personality", "You are Chode, a friendly chatbot.")
        else:
            server_id = f"DM-{message.author.id}"
            personality = "You are Chode, a friendly chatbot."  # Default in DMs

        # Store the message in the database.
        database.store_memory(server_id, message.channel.id, message.author.id, message.content)

        # Process commands if the message starts with the command prefix.
        if message.content.startswith("!!"):
            await bot.process_commands(message)
            return

        # For DM messages, process as conversation (and include member info if available).
        if message.guild is None:
            # Remove any bot mention from content.
            cleaned_content = message.clean_content.replace(bot.user.mention, "").strip()
            member_info = utils.get_member_info(message.author) if hasattr(utils, "get_member_info") else ""
            conversation_history = database.get_recent_conversation(server_id, message.channel.id)
            prompt_for_llm = (
                f"System: {personality}\n"
                f"Conversation History:\n{conversation_history}\n"
                f"User {message.author.name} (Status: {member_info}) said: {cleaned_content}\n"
                f"Respond as Chode:"
            )
            async with message.channel.typing():
                response_text = await asyncio.to_thread(lmstudio.call_lmstudio, prompt_for_llm)
            if len(response_text) > 2000:
                await utils.send_long_message(message.channel, response_text)
            else:
                await message.channel.send(response_text)
            # Also process DM commands.
            await bot.process_commands(message)
            return

        # For guild messages where the bot is mentioned.
        if bot.user in message.mentions:
            content_lower = message.content.lower()
            ctx_obj = await bot.get_context(message)
            # If asking what a user is playing, filter out the bot's own mention.
            if "what is" in content_lower and "playing" in content_lower:
                members = [m for m in message.mentions if m != bot.user]
                if members and hasattr(utils, "get_member_info"):
                    member_info = utils.get_member_info(members[0])
                    await message.channel.send(member_info)
                    return

            # For image generation when the bot is mentioned.
            if "generate" in content_lower and any(word in content_lower for word in ["photo", "image", "picture"]):
                new_prompt = message.clean_content.replace(bot.user.mention, "").strip()
                final_prompt = new_prompt
                if new_prompt.strip().endswith("++"):
                    await message.channel.send("Hold on while I reword your prompt...")
                    final_prompt = new_prompt.strip()[:-2].strip()
                    final_prompt = utils.reword_prompt(final_prompt)
                elif "make this prompt better" in new_prompt.lower():
                    final_prompt = utils.reword_prompt(new_prompt)
                await message.channel.send(f"Image generation started. Prompt used: {final_prompt}")
                await asyncio.to_thread(comfyui.generate_and_send_images, final_prompt, ctx_obj)
                return
            elif "what server" in content_lower:
                prompt_for_llm = (
                    f"System: {personality}\n"
                    f"The user asked: '{message.content}'. The server details are as follows: "
                    f"Name: {message.guild.name}, ID: {message.guild.id}, and there are {message.guild.member_count} members. "
                    f"Respond in your own words as Chode."
                )
            else:
                conversation_history = database.get_recent_conversation(message.guild.id, message.channel.id)
                server_info = (
                    f"Server Name: {message.guild.name}, Server ID: {message.guild.id}, Member Count: {message.guild.member_count}"
                )
                # Remove the bot's mention from the content.
                cleaned_content = message.clean_content.replace(bot.user.mention, "").strip()
                prompt_for_llm = (
                    f"System: {personality}\n"
                    f"Server Info: {server_info}\nConversation History:\n{conversation_history}\n"
                    f"User {message.author.name} said: {cleaned_content}\nRespond as Chode:"
                )
            async with message.channel.typing():
                response_text = await asyncio.to_thread(lmstudio.call_lmstudio, prompt_for_llm)
            if len(response_text) > 2000:
                await utils.send_long_message(message.channel, response_text)
            else:
                await message.channel.send(response_text)
            return

        # For any other guild message, process commands and add a reaction if interesting.
        else:
            asyncio.create_task(utils.add_reaction_if_interesting(message))
            await bot.process_commands(message)
