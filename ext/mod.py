import asyncio
from collections import defaultdict
import datetime
import typing

from ext.utils import embed_utils
from ext.utils.timed_events import parse_time, spool_reminder
from ext.utils.embed_utils import paginate
from discord.ext import commands
import discord


# TODO: Find a way to use a custom converter for temp mute/ban and merge into main command.

async def get_prefix(bot, message):
    if message.guild is None:
        pref = [".tb ", "!", "-", "`", "!", "?", ""]
    else:
        pref = bot.prefix_cache[message.guild.id]
    if not pref:
        pref = [".tb "]
    return commands.when_mentioned_or(*pref)(bot, message)

class Mod(commands.Cog):
    """ Guild Moderation Commands """
    
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.update_cache())
        self.bot.prefix_cache = defaultdict(list)
        self.bot.loop.create_task(self.update_prefixes())
        self.bot.command_prefix = get_prefix
        if not hasattr(self.bot, "lockdown_cache"):
            self.bot.lockdown_cache = {}
    
    def me_or_mod(self):
        def predicate(ctx):
            return ctx.author.permissions_in(ctx.channel).manage_channels or ctx.author.id == self.bot.owner_id
        return commands.check(predicate)
    
    # Listeners
    @commands.Cog.listener()
    async def on_message(self, message):
        ctx = await self.bot.get_context(message)
        if ctx.message.content == ctx.me.mention:
            if message.guild is None:
                return await ctx.reply(f'What?')
            try:
                await ctx.reply(f"Forgot your prefixes? They're ```css"
                               f"\n{', '.join(self.bot.prefix_cache[message.guild.id])}```", mention_author=True)
            except discord.Forbidden:
                return
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        connection = await self.bot.db.acquire()
        await connection.execute("""
        with gid as (
                INSERT INTO guild_settings (guild_id) VALUES ($1)
        RETURNING guild_id
        )
        INSERT INTO prefixes (prefix, guild_id)
        VALUES
        ( $2, (SELECT guild_id FROM gid)
        );
        """, guild.id,  '.tb ')
        await self.bot.db.release(connection)
        await self.update_prefixes()

    async def update_prefixes(self):
        self.bot.prefix_cache.clear()
        connection = await self.bot.db.acquire()
        records = await connection.fetch("""SELECT * FROM prefixes""")
        await self.bot.db.release(connection)
        
        for r in records:
            guild_id = r["guild_id"]
            prefix = r["prefix"]
            self.bot.prefix_cache[guild_id].append(prefix)
        
        # Items ending in space must come first.
        for guild, pref_list in self.bot.prefix_cache.items():
            for i in range(len(pref_list)):
                if pref_list[i].endswith(' '):
                    pref_list = [pref_list[i]] + pref_list[:i] + pref_list[i + 1:]
            self.bot.prefix_cache[guild] = pref_list
            
    async def update_cache(self):
        self.bot.disabled_cache = defaultdict(list)
        connection = await self.bot.db.acquire()
        records = await connection.fetch("""SELECT * FROM disabled_commands""")
        await self.bot.db.release(connection)
        
        for r in records:
            try:
                self.bot.disabled_cache[r["guild_id"]].append(r["command"])
            except KeyError:
                self.bot.disabled_cache.update({r["guild_id"]: [r["command"]]})
    
    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def leave(self, ctx):
        """ Politely ask me to leave the server. """
        m = await ctx.reply('Are you sure you want me to go? All of your settings will be wiped.', mention_author=True)
        await embed_utils.bulk_react(ctx, m, ['✅', '🚫'])

        def check(reaction, user):
            if reaction.message.id == m.id and user == ctx.author:
                emoji = str(reaction.emoji)
                return emoji.startswith(('✅', '🚫'))
            
        try:
            res = await self.bot.wait_for("reaction_add", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.reply("Response timed out after 30 seconds, I will stay for now.", mention_author=True)
        res = res[0]

        if res.emoji.startswith('✅'):
            await ctx.reply('Farewell!', mention_author=False)
            await ctx.guild.leave()
        else:
            await ctx.reply("Okay, I'll stick around a bit longer then.", mention_author=False)
            await m.remove_reaction('✅', ctx.me)

    @commands.command(aliases=['nick'])
    @commands.has_permissions(manage_nicknames=True)
    async def name(self, ctx, *, new_name: str):
        """ Rename the bot for your server. """
        await ctx.me.edit(nick=new_name)
        await ctx.reply(f"My new name is {new_name} on your server.", mention_author=False)
    
    @commands.command(usage="say <Channel (optional)< <what you want the bot to say>")
    @commands.check(me_or_mod)
    async def say(self, ctx, destination: typing.Optional[discord.TextChannel] = None, *, msg):
        """ Say something as the bot in specified channel """
        if destination is None:
            destination = ctx.channel
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await destination.send(msg)
    
    @commands.command(usage="topic <New Channel Topic>")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def topic(self, ctx, *, new_topic):
        """ Set the topic for the current channel """
        await ctx.channel.edit(topic=new_topic)
        await ctx.reply(f"Topic changed to: '{new_topic}'", mention_author=False)
    
    @commands.command(usage="pin <(Message ID you want pinned) or (new message to pin.)>")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def pin(self, ctx, *, message: typing.Union[discord.Message, int, str]):
        """ Pin a message to the current channel """
        if isinstance(message, int):
            message = await ctx.channel.fetch_message(message)
        elif isinstance(message, str):
            message = await ctx.reply(message, mention_author=True)
        await message.pin()
    
    @commands.command(usage="rename <member> <new name>")
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def rename(self, ctx, member: discord.Member, nickname: commands.clean_content):
        """ Rename a member """
        try:
            await member.edit(nick=nickname)
        except discord.Forbidden:
            await ctx.reply("⛔ I can't change that member's nickname.", mention_author=True)
        except discord.HTTPException:
            await ctx.reply("❔ Member edit failed.", mention_author=True)
        else:
            await ctx.reply(f"{member.mention} has been renamed.", mention_author=False)
    
    @commands.command(usage="delete_empty_roles")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def delete_empty_roles(self, ctx):
        """ Delete any unused roles on the server """
        targets = [i for i in ctx.guild.roles if i.name.lower() != "muted" and not i.members]
        deleted = []
        for i in targets:
            deleted.append(i.name)
            await i.delete()
        await ctx.reply(f'Found and deleted {len(deleted)} empty roles: {", ".join(deleted)}', mention_author=False)
    
    @commands.command(usage="kick <@member1  @member2 @member3> <reason>")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, members: commands.Greedy[discord.Member], *, reason="unspecified reason."):
        """ Kicks the user from the server """
        if not members:
            return
        
        success = []
        fail = []
        
        for i in members:
            try:
                await i.kick(reason=f"{ctx.author.name}: {reason}")
            except discord.Forbidden:
                fail.append(f"{i} (Higher Role)")
            except discord.HTTPException:
                fail.append(f"{i.mention} (Error)")
            else:
                success.append(i.mention)
        
        if success:
            await ctx.reply(f"✅ {', '.join(success)} kicked for: \"{reason}\".", mention_author=False)
        if fail:
            await ctx.reply(f"⚠ Kicking failed for {', '.join(fail)}.", mention_author=True)
            
    @commands.command(usage="ban <@member1 [user_id2, @member3, @member4]> "
                            "<(Optional: Days to delete messages from)> <(Optional: reason)>",
                      aliases=["hackban"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, targets: commands.Greedy[typing.Union[discord.Member, int]],
                  delete_days: typing.Optional[int] = 1, *, reason="Not specified"):
        """ Bans a list of members (or User IDs) from the server, deletes all messages for the last x days """
        for i in targets:
            if isinstance(i, discord.Member):
                try:
                    await i.ban(reason=f"{ctx.author.name}: {reason}", delete_message_days=delete_days)
                    outstr = f"☠ {i.mention} was banned by {ctx.author} for: \"{reason}\""
                    if delete_days:
                        outstr += f", messages from last {delete_days} day(s) were deleted."
                    await ctx.reply(outstr, mention_author=False)
                except discord.Forbidden:
                    await ctx.reply(f"⛔ Sorry, I can't ban {i.mention}.", mention_author=True)
                except discord.HTTPException:
                    await ctx.reply(f"⚠ Banning failed for {i.mention}.", mention_author=True)
                except Exception as e:
                    await ctx.reply(f"⚠ Banning failed for {i.mention}.", mention_author=True)
                    print("Failed while banning member\n", e)
            else:
                try:
                    await self.bot.http.ban(i, ctx.message.guild.id)
                    target = await self.bot.fetch_user(i)
                    outstr = f"☠ UserID {i} {target} was banned for reason: \"{reason}\""
                    if delete_days:
                        outstr += f", messages from last {delete_days} day(s) were deleted."
                    await ctx.reply(outstr, mention_author=False)
                except discord.HTTPException:
                    await ctx.reply(f"⚠ Banning failed for UserID# {i}.", mention_author=True)
                except Exception as e:
                    await ctx.reply(f"⚠ Banning failed for UserID# {i}.", mention_author=True)
                    print("Failed while banning ID#.\n", e)
    
    @commands.command(usage="unban <UserID of member: e.g. 13231232131> ")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, *, who):
        """ Unbans a user from the server """
        # Try to get by user_id.
        user = discord.Object(who)
        await ctx.guild.unban(user)
        if who.isdigit():
            try:
                await self.bot.http.unban(who, ctx.guild.id)
            except discord.Forbidden:
                await ctx.reply("⛔ I can't unban that user.", mention_author=True)
            except discord.HTTPException:
                await ctx.reply("❔ Unban failed.", mention_author=True)
            else:
                await ctx.reply(f"🆗 {who} was unbanned", mention_author=False)
        else:
            try:
                un, discrim = who.split('#')
                for i in await ctx.guild.bans():
                    if i.user.display_name == un and i.discriminator == discrim:
                        try:
                            await self.bot.http.unban(i.user.id, ctx.guild.id)
                        except discord.Forbidden:
                            await ctx.reply("⛔ I can't unban that user.", mention_author=True)
                        except discord.HTTPException:
                            await ctx.reply("❔ Unban failed.", mention_author=True)
                        else:
                            await ctx.reoky(f"🆗 {who} was unbanned", mention_author=False)
                        return  # Stop iterating when found.
            except ValueError:
                for i in await ctx.guild.bans():
                    if i.user.name == who:
                        try:
                            await self.bot.http.unban(i.user.id, ctx.guild.id)
                        except discord.Forbidden:
                            await ctx.reply(f"⛔ I can't unban {i}.", mention_author=True)
                        except discord.HTTPException:
                            await ctx.reply(f"❔ Unban failed for {i.user}", mention_author=True)
                        else:
                            await ctx.reply(f"🆗 {i.user} was unbanned", mention_author=False)
                        return  # Stop iterating when found.
    
    @commands.command(aliases=['bans'])
    @commands.has_permissions(view_audit_log=True)
    @commands.bot_has_permissions(view_audit_log=True)
    async def banlist(self, ctx):
        """ Show the banlist for the server """
        ban_lines = [f"\💀 {x.user.name}#{x.user.discriminator}: {x.reason}\n" for x in await ctx.guild.bans()]
        if not ban_lines:
            ban_lines = ["☠ No bans found!"]

        e = discord.Embed(color=0x111)
        n = f"≡ {ctx.guild.name} discord ban list"
        e.set_author(name=n, icon_url=ctx.guild.icon_url)
        e.set_thumbnail(url="https://i.ytimg.com/vi/eoTDquDWrRI/hqdefault.jpg")
        e.title = "User (Reason)"

        ban_embeds = embed_utils.rows_to_embeds(e, ban_lines)
        await paginate(ctx, ban_embeds)
    
    ### Mutes & Blocks
    @commands.command(usage="Block <Optional: #channel> <@member1 @member2> <Optional: reason>")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def block(self, ctx, channel: typing.Optional[discord.TextChannel], members: commands.Greedy[discord.Member]):
        """ Block a user from seeing or talking in this channel  """
        if channel is None:
            channel = ctx.channel

        ow = discord.PermissionOverwrite(read_messages=False, send_messages=False)
        for i in members:
            await channel.set_permissions(i, overwrite=ow)
        
        await ctx.reply(f'Blocked {" ,".join([i.mention for i in members])} from {channel.mention}',
                        mention_author=False)

    @commands.command(usage="unblock <Optional: #channel> <@member1 @member2> <Optional: reason>")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unblock(self, ctx, channel:typing.Optional[discord.TextChannel], members:commands.Greedy[discord.Member]):
        if channel is None:
            channel = ctx.channel
            
        for i in members:
            await channel.set_permissions(i, overwrite=None)

        await ctx.reply(f'Unblocked {" ,".join([i.mention for i in members])} from {channel.mention}',
                        mention_author=False)
        
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.command(usage="mute <@user1 @user2 @user3> <reason>")
    async def mute(self, ctx, members: commands.Greedy[discord.Member], *, reason="No reason given."):
        """ Prevent member(s) from talking on your server. """
        muted_role = discord.utils.get(ctx.guild.roles, name='Muted')
        if not muted_role:
            muted_role = await ctx.guild.create_role(name="Muted")  # Read Messages / Read mesasge history.
            await muted_role.edit(position=ctx.me.top_role.position - 1)
            m_overwrite = discord.PermissionOverwrite(add_reactions=False, send_messages=False)
            for i in ctx.guild.text_channels:
                await i.set_permissions(muted_role, overwrite=m_overwrite)
        
        muted = []
        not_muted = []
        for i in members:
            if i.top_role >= ctx.me.top_role:
                members.remove(i)
                not_muted.append(i)
                continue
            else:
                muted.append(i)
                await i.add_roles(muted_role, reason=f"{ctx.author}: {reason}")

        if muted:
            await ctx.reply(f"Muted {', '.join([i.mention for i in muted])} for {reason}", mention_author=False)
        if not_muted:
            await ctx.reply(f"⚠ Could not mute {', '.join([i.mention for i in not_muted])},"
                    f" they are the same or higher role than me.", mention_author=True)
        
                
    @commands.command(usage="<@user @user2>")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx, members: commands.Greedy[discord.Member]):
        """ Allow members to talk again. """
        muted_role = discord.utils.get(ctx.guild.roles, name='Muted')
        if not muted_role:
            return await ctx.reply(f"No 'muted' role found on {ctx.guild.name}", mention_author=True)
        
        success, fail = [], []
        for i in members:
            try:
                await i.remove_roles(muted_role)
            except discord.Forbidden:
                fail.append(i.mention)
            else:
                success.append(i.mention)
        
        if success:
            await ctx.reply(f"🆗 Unmuted {', '.join(success)}", mention_author=False)
        if fail:
            await ctx.reply(f"🚫 Could not unmute {', '.join(fail)}", mention_author=True)
        
    
    @commands.command(aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clean(self, ctx, number: int = 100):
        """ Deletes my messages from the last x messages in channel"""
        try:
            prefixes = tuple(self.bot.prefix_cache[ctx.guild.id])
        except KeyError:
            prefixes = ctx.prefix
        
        def is_me(m):
            return m.author == ctx.me or m.content.startswith(prefixes)
        
        try:
            deleted = await ctx.channel.purge(limit=number, check=is_me)
            s = "s" if len(deleted) > 1 else ""
            await ctx.reply(f'♻ Deleted {len(deleted)} bot and command messages{s}', mention_author=False)
        except discord.NotFound:
            pass
    
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def prefix(self, ctx):
        """ Add, remove, or List bot prefixes for this server to use them instead of the default .tb """
        try:
            prefixes = self.bot.prefix_cache[ctx.guild.id]
        except KeyError:
            prefixes = ['.tb ']
            connection = await self.bot.db.acquire()
            await connection.execute("""INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2)""", ctx.guild.id, '.tb ')
            await self.bot.db.release(connection)
            await self.update_prefixes()
        
        prefixes = ', '.join([f"'{i}'" for i in prefixes])
        await ctx.reply(f"Current Command prefixes for this server: ```{prefixes}```", mention_author=False)
    
    @prefix.command(name="add", aliases=["set"])
    @commands.has_permissions(manage_guild=True)
    async def pref_add(self, ctx, prefix):
        """ Add a prefix to your server's list of bot prefixes """
        try:
            prefixes = self.bot.prefix_cache[ctx.guild.id]
        except KeyError:
            prefixes = ['.tb ']
        
        if prefix not in prefixes:
            connection = await self.bot.db.acquire()
            await connection.execute("""INSERT INTO prefixes (guild_id,prefix) VALUES ($1,$2) """, ctx.guild.id,
                                     prefix)
            await self.bot.db.release(connection)
            await ctx.reply(f"Added '{prefix}' to {ctx.guild.name}'s prefixes list.", mention_author=False)
            await self.update_prefixes()
        else:
            await ctx.reply(f"'{prefix}' was already in {ctx.guild.name}'s prefix list", mention_author=False)
        
        prefixes = ', '.join([f"'{i}'" for i in self.bot.prefix_cache[ctx.guild.id]])
        await ctx.reply(f"Current Command prefixes for this server: ```{prefixes}```", mention_author=False)
    
    @prefix.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def pref_del(self, ctx, prefix):
        """ Remove a prefix from your server's list of bot prefixes """
        try:
            prefixes = self.bot.prefix_cache[ctx.guild.id]
        except KeyError:
            prefixes = ['.tb ']
        if prefix in prefixes:
            connection = await self.bot.db.acquire()
            await connection.execute("""DELETE FROM prefixes WHERE (guild_id,prefix) = ($1,$2) """, ctx.guild.id,
                                     prefix)
            await self.bot.db.release(connection)
            await ctx.reply(f"Deleted '{prefix}' from {ctx.guild.name}'s prefixes list.", mention_author=False)
            await self.update_prefixes()
        else:
            await ctx.reply(f"'{prefix}' was not in {ctx.guild.name}'s prefix list", mention_author=False)
        
        prefixes = ', '.join([f"'{i}'" for i in self.bot.prefix_cache[ctx.guild.id]])
        await ctx.reply(f"Current Command prefixes for this server: ```{prefixes}```", mention_author=False)
    
    @commands.command(usage="<command name to enable>")
    async def enable(self, ctx, command: str):
        """Re-enables a disabled command for this server"""
        disable = self.bot.get_command('disable')
        await ctx.invoke(disable, command)
    
    @commands.command(usage="<command name to disable>")
    @commands.has_permissions(manage_guild=True)
    async def disable(self, ctx, command: str):
        """Disables a command for this server."""
        command = command.lower()
        
        if ctx.invoked_with == "enable":
            if command not in self.bot.disabled_cache[ctx.guild.id]:
                return await ctx.reply(f"The {command} command is not disabled on this server.", mention_author=False)
            else:
                connection = await self.bot.db.acquire()
                async with connection.transaction():
                    await connection.execute("""
                        DELETE FROM disabled_commands WHERE (guild_id,command) = ($1,$2)
                        """, ctx.guild.id, command)
                await self.bot.db.release(connection)
                await self.update_cache()
                return await ctx.reply(f"The {command} command was enabled for {ctx.guild.name}", mention_author=False)
        elif ctx.invoked_with == "disable":
            if command in self.bot.disabled_cache[ctx.guild.id]:
                return await ctx.reply(f"The {command} command is already disabled on this server.",
                                       mention_author=False)
        
        
        if command in ('disable', 'enable'):
            return await ctx.reply('You cannot disable the disable command.', mention_author=True)
        elif command not in [i.name for i in list(self.bot.commands)]:
            return await ctx.reply('Unrecognised command name.', mention_author=True)
        
        connection = await self.bot.db.acquire()
        await connection.execute(""" INSERT INTO disabled_commands (guild_id,command) VALUES ($1,$2) """,
                                 ctx.guild.id, command)
        await self.bot.db.release(connection)
        await self.update_cache()
        return await ctx.reply(f"The {command} command was disabled for {ctx.guild.name}", mention_author=False)
    
    @commands.command(usage="disabled")
    @commands.has_permissions(manage_guild=True)
    async def disabled(self, ctx):
        """ Check which commands are disabled on this server """
        try:
            disabled = self.bot.disabled_cache[ctx.guild.id]
            header = f"The following commands are disabled on this server:"
            embeds = embed_utils.rows_to_embeds(discord.Embed(), disabled)
            await paginate(ctx, embeds, header=header)
        except KeyError:
            return await ctx.reply(f'No commands are currently disabled on {ctx.guild.name}', mention_author=False)

    @commands.command(usage="tempban <members: @member1 @member2> <time (e.g. 1d1h1m1s)> <(Optional: reason)>")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx,  members: commands.Greedy[discord.Member], time, *,
                      reason: commands.clean_content = None):
        """ Temporarily ban member(s) """
        try:
            delta = await parse_time(time.lower())
        except ValueError:
            return await ctx.reply('Invalid time specified, use format `1d1h30m10s`', mention_author=True)
        remind_at = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remind_at, "%H:%M:%S on %a %d %b")
    
        for i in members:
            try:
                await ctx.guild.ban(i, reason=reason)
            except discord.Forbidden:
                await ctx.reply(f"🚫 I can't ban {i.mention}.", mention_author=True)
                continue
        
            connection = await self.bot.db.acquire()
            record = await connection.fetchrow(""" INSERT INTO reminders (message_id, channel_id, guild_id,
            reminder_content,
            created_time, target_time. user_id, mod_action, mod_target) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *""", ctx.message.id, ctx.channel.id, ctx.guild.id, reason, datetime.datetime.now(), remind_at,
                                              ctx.author.id, "unban", i.id)
            await self.bot.db.release(connection)
            self.bot.reminders.append(self.bot.loop.create_task(spool_reminder(ctx.bot, record)))
    
        e = discord.Embed()
        e.title = "⏰ User banned"
        e.description = f"{[i.mention for i in members]} will be unbanned for \n{reason}\nat\n {human_time}"
        e.colour = 0x00ffff
        e.timestamp = remind_at
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(usage="tempmute <members: @member1 @member2> <time (e.g. 1d1h1m1s)> <(Optional: reason)>")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def tempmute(self, ctx, members: commands.Greedy[discord.Member], time,
                       *, reason: commands.clean_content = None):
        """ Temporarily mute member(s) """
        try:
            delta = await parse_time(time.lower())
        except ValueError:
            return await ctx.reply('Invalid time specified, use format `1d1h30m10s`', mention_author=True)
        remind_at = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remind_at, "%H:%M:%S on %a %d %b")
    
        # Role.
        muted_role = discord.utils.get(ctx.guild.roles, name='Muted')
        if not muted_role:
            muted_role = await ctx.guild.create_role(name="Muted")  # Read Messages / Read mesasge history.
            await muted_role.edit(position=ctx.me.top_role.position - 1)
            m_overwrite = discord.PermissionOverwrite(add_reactions=False, send_messages=False)
        
            for i in ctx.guild.text_channels:
                await i.set_permissions(muted_role, overwrite=m_overwrite)

        # Mute
        for i in members:
            await i.add_roles(muted_role, reason=f"{ctx.author}: {reason}")
            connection = await self.bot.db.acquire()
            record = await connection.fetchrow(""" INSERT INTO reminders
            (message_id, channel_id, guild_id, reminder_content,
             created_time, target_time, user_id, mod_action, mod_target)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *""",
            ctx.message.id, ctx.channel.id, ctx.guild.id, reason,
            ctx.message.created_at, remind_at, ctx.author.id, "unmute", i.id)
            await self.bot.db.release(connection)
            self.bot.reminders.append(self.bot.loop.create_task(spool_reminder(ctx.bot, record)))
    
        e = discord.Embed()
        e.title = "⏰ User muted"
        e.description = f"{', '.join([i.mention for i in members])} temporarily muted:"
        e.add_field(name="Until", value=human_time)
        if reason is not None:
            e.add_field(name="Reason", value=str(reason))
        e.colour = 0x00ffff
        e.timestamp = remind_at
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(usage="tempblock <members: @member1 @member2> <time (e.g. 1d1h1m1s)> <(Optional: reason)>")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def tempblock(self, ctx, channel: typing.Optional[discord.TextChannel],
                        members: commands.Greedy[discord.Member], time, *, reason: commands.clean_content = None):
        """ Temporarily mute member(s) """
        if channel is None:
            channel = ctx.channel
    
        try:
            delta = await parse_time(time.lower())
        except ValueError:
            return await ctx.reply('Invalid time specified, use format `1d1h30m10s`', mention_author=True)
        remind_at = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remind_at, "%H:%M:%S on %a %d %b")
    
        ow = discord.PermissionOverwrite(read_messages=False, send_messages=False)
    
        # Mute, send to notification channel if exists.
        for i in members:
            await channel.set_permissions(i, overwrite=ow)
        
            connection = await self.bot.db.acquire()
            record = await connection.fetchval(""" INSERT INTO reminders (message_id, channel_id, guild_id,
            reminder_content,
            created_time, target_time. user_id, mod_action, mod_target) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *""", ctx.message.id, channel.id, ctx.guild.id, reason, datetime.datetime.now(), remind_at,
                                              ctx.author.id, "unblock", i.id)
            await self.bot.db.release(connection)
            self.bot.reminders.append(self.bot.loop.create_task(spool_reminder(ctx.bot, record)))
    
        e = discord.Embed()
        e.title = "⏰ User blocked"
        e.description = f"{', '.join([i.mention for i in members])} will be blocked from {channel.mention} " \
                        f"\n{reason}\nuntil\n {human_time}"
        e.colour = 0x00ffff
        e.timestamp = remind_at
        await ctx.reply(embed=e, mention_author=False)
        
    @commands.command()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def lockdown(self, ctx, top_role:typing.Optional[discord.Role]):
        """ Anti-raid command: Stop un-roled people sending messages in the discord.
        Mention a role to stop people below that role from sending messages as the cutoff. """
        if not top_role:
            top_role = ctx.guild.default_role
        
        target_position = top_role.position
        
        if ctx.author.top_role.position < target_position:
            target_position = ctx.author.top_role.position - 1
        
        new_perms = discord.Permissions(send_messages=False)

        self.bot.lockdown_cache[ctx.guild.id] = []
        modified_roles = []
        for i in ctx.guild.roles:
            if not i.permissions.send_messages:  # if role does not have send message perm override set, skip.
                continue
            
            if i.position <= target_position:  # If we are below the target position
                self.bot.lockdown_cache[ctx.guild.id].append((i.id, i.permissions))  # Save id, permissions tuple.
                await i.edit(permissions=new_perms, reason="Raid lockdown.")
                modified_roles.append(i.name)
                
        if not modified_roles:
            return await ctx.reply('⚠ No roles were modified.', mention_author=True)
        await ctx.reply(f"⚠ {len(modified_roles)} roles can no longer send messages.", mention_author=True)
        output = modified_roles.pop(0)
        for x in modified_roles:
            if len(x + output + 10 > 2000):
                output += f", {x}"
            else:
                await ctx.reply(f"```{output}```", mention_author=True)
                output = x
        await ctx.reply(f"```{output}```", mention_author=True)

    @commands.command(usage="")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unlock(self, ctx):
        """ Unlock a previously set lockdown. """
        if not ctx.guild.id in self.bot.lockdown_cache:
            return await ctx.reply('Lockdown not in progress.', mention_author=False)
        
        count = 0
        for role in self.bot.lockdown_cache[ctx.guild.id]:
            # Role tuple is role id, permissions.
            r = ctx.guild.get_role(role[0])
            await r.edit(permissions=role[1], reason="Unlock raid.")
            count += 1
        
        self.bot.lockdown_cache.pop(ctx.guild.id)  # dump from cache, no longer needed.
        await ctx.reply(f'Restored send_messages permissions to {count} roles', mention_author=True)
    

def setup(bot):
    bot.add_cog(Mod(bot))
