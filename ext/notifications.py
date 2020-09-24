import asyncio
from discord.ext import commands
import discord
import typing

from ext.utils import codeblocks


class Notifications(commands.Cog):
    """ Guild Moderation Commands """
    
    def __init__(self, bot):
        self.bot = bot
        self.records = []
        self.bot.loop.create_task(self.update_cache())
    
    # TODO: On Channel Delete - Cascades!
    # TODO: Custom welcome message
    # TODO: Port on_message_delete
    # TODO: Custom Reactions.
    
    async def update_cache(self):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            self.records = await connection.fetch("""SELECT * FROM guild_settings""")
        await self.bot.db.release(connection)
        
    # Master info command.
    @commands.has_permissions(manage_guild=True)
    @commands.group(invoke_without_command=True, usage="mod")
    async def mod(self, ctx):
        """ Shows the status of various mod tools."""
        # Get settings.
        e = discord.Embed(color=0x7289DA)
        e.description = ""
        e.set_author(name=ctx.guild.name)
        e.title = f"Notification message settings"
        
        try:
            r = [r for r in self.records if r["guild_id"] == ctx.guild.id][0]
        except IndexError:
            e.description = "No configuration set."
        else:
            for key, value in dict(r).items():
                if value is not None:
                    try:
                        value = self.bot.get_channel(value).mention
                    except AttributeError:
                        value = "Deleted channel."
                    e.description += f"{key}: {value} \n"
                else:
                    e.description += f"{key}: Not set\n"
        
        e.set_thumbnail(url=ctx.guild.icon_url)
        await ctx.send(embed=e)
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(usage="joins <#channel> to set a new channel, or leave blank to show current information.")
    async def joins(self, ctx, channel: typing.Optional[discord.TextChannel]):
        """ Send member information to a channel on join. """
        if channel is None:  # Give current info
            joins = [r['joins_channel_id'] for r in self.records if r["guild_id"] == ctx.guild.id][0]
            ch = self.bot.get_channel(joins)
            if ch is None:
                return await ctx.send(f'Join information is not currently being output.')
            else:
                return await ctx.send(f'Join information is currently being output to {ch.mention}')
        
        if not ctx.me.permissions_in(channel).send_messages:
            return await ctx.send(f'🚫 I cannot send messages to {channel.mention}.')
        
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        
        await ctx.send(f'Information about new users will be sent to {channel.mention} when they join.')
    
    @commands.has_permissions(manage_channels=True)
    @joins.command(name="off", alaises=["none", "disable"], usages="joins off")
    async def joins_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Information about new users will no longer be output.')
    
    @commands.has_permissions(manage_guild=True)
    @commands.group(usage="leaves <#channel> to set a new channel, or leave blank to show current setting")
    async def leaves(self, ctx, channel: typing.Optional[discord.TextChannel] = None):
        """ Set a channel to show information about new member joins """
        if channel is None:  # Show current info
            leaves = [r['leaves_channel_id'] for r in self.records if r["guild_id"] == ctx.guild.id][0]
            ch = self.bot.get_channel(leaves)
            if ch is None:
                return await ctx.send(f'Member leaves are not currently being output.')
            else:
                return await ctx.send(f'Member leave information is currently being output to {ch.mention}')
        
        if not ctx.me.permissions_in(channel).send_messages:
            return await ctx.send(f'🚫 I cannot send messages to {channel.mention}.')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute("""
                UPDATE guild_settings SET leaves_channel_id = $2 WHERE guild_id = $1
                """, ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        
        await ctx.send(f'Notifications will be sent to {channel.mention} when users leave.')
    
    @commands.has_permissions(manage_channels=True)
    @leaves.command(name="off", alaises=["none", "disable"], usage="leaves off")
    async def leaves_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET joins_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Leave notifications will no longer be output.')
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(usage="mutes <#channel> to set a new channel or leave blank to show current setting>")
    async def mutes(self, ctx, channel: typing.Optional[discord.TextChannel] = None):
        """ Set a channel to show messages about user mutings """
        if channel is None:  # Show current info
            mutes = [r['mutes_channel_id'] for r in self.records if r["guild_id"] == ctx.guild.id][0]
            ch = self.bot.get_channel(mutes)
            if ch is None:
                return await ctx.send(f'Mute notifications are not currently being output.')
            else:
                return await ctx.send(f'Mute notifications are currently being output to {ch.mention}')
        
        if not ctx.me.permissions_in(channel).send_messages:
            return await ctx.send(f'🚫 I cannot send messages to {channel.mention}.')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" UPDATE guild_settings SET mutes_channel_id = $2 WHERE guild_id = $1""",
                                     ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(f"Notifications will be output to {channel.mention} when a member is muted.")

    @commands.has_permissions(manage_channels=True)
    @mutes.command(name="off", alaises=["none", "disable"], usage="leaves off")
    async def mutes_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET mutes_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Mute and block notifications will no longer be output.')
    
    @commands.has_permissions(manage_channels=True)
    @commands.group(usage="emojis <#channe> to set a new channel or leave blank to show current setting>")
    async def emojis(self, ctx, channel: typing.Optional[discord.TextChannel] = None):
        """ Set a channel to show when emojis are changed. """
        if channel is None:
            emojis = [r['emojis_channel_id'] for r in self.records if r["guild_id"] == ctx.guild.id][0]
            ch = self.bot.get_channel(emojis)
            if ch is None:
                return await ctx.send(f'Emoji change notifications are not currently being output.')
            else:
                return await ctx.send(f'Emoji change notifications are currently being output to {ch.mention}')
        
        if not ctx.me.permissions_in(channel).send_messages:
            return await ctx.send(f'🚫 I cannot send messages to {channel.mention}.')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute("""
                UPDATE guild_settings SET emojis_channel_id = $2 WHERE guild_id = $1
                """, ctx.guild.id, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(f"Notifications will be output to {channel.mention} when emojis are changed.")

    @emojis.command()
    @commands.has_permissions(manage_channels=True)
    async def emojis_off(self, ctx):
        connection = await self.bot.db.acquire()
        await connection.execute(""" UPDATE guild_settings SET emojis_channel_id = $2 WHERE guild_id = $1""",
                                 ctx.guild.id, None)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('Emoji update notifications will no longer be output.')

    # Listeners
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await asyncio.sleep(10)  # Time for other cogs to do their shit.
        await self.update_cache()
        print(f"[Join] {guild.id} ({guild.name})")
        
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        connection = await self.bot.db.acquire()
        await connection.execute("""DELETE FROM guild_settings WHERE guild_id = $1""", guild.id)
        await self.bot.db.release(connection)
        print(f"[Remove] {guild.id} ({guild.name})")

    # TODO: Blocked
    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Notify about member mute/un-mute.
        muted_role = discord.utils.find(lambda r: r.name.lower() == 'muted', before.guild.roles)
        if muted_role in before.roles and muted_role not in after.roles:
            content = f"🙊 {before.mention} was unmuted"
        elif muted_role not in before.roles and muted_role in after.roles:
            content = f"🙊 {before.mention} was muted"
        else:
            return
        
        try:
            mutes = [r['mutes_channel_id'] for r in self.records if r["guild_id"] == before.guild.id][0]
        except IndexError:
            return  # Notification channel note set.
        
        ch = self.bot.get_channel(mutes)
        
        if ch is None:
            return
        
        try:
            async for entry in before.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                content += f" by {entry.user} for {entry.reason}"
        except discord.Forbidden:
            pass  # Missing permissions to get reason.
        await ch.send(content)
            
    @commands.Cog.listener()
    async def on_member_join(self, new_member):
        try:
            joins = [r['joins_channel_id'] for r in self.records if r["guild_id"] == new_member.guild.id][0]
            ch = self.bot.get_channel(joins)
            if ch is None:
                return
        except IndexError:
            return
        
        # Extended member join information.
        e = discord.Embed()
        e.colour = 0x7289DA
        s = sum(1 for m in self.bot.get_all_members() if m.id == new_member.id)
        e.title = str(new_member)
        e.add_field(name="Status", value=str(new_member.status).title(), inline=True)
        e.add_field(name='User ID', value=new_member.id, inline=True)
        e.add_field(name='Mutual Servers', value=f'{s} shared', inline=True)
        if new_member.bot:
            e.description = '**This is a bot account**'
        
        coloured_time = codeblocks.time_to_colour(new_member.created_at)
        
        e.add_field(name="Account Created", value=coloured_time)
        e.set_thumbnail(url=new_member.avatar_url)
        
        try:
            await ch.send(embed=e)
        except discord.Forbidden:  # If you wanna fuck up your settings it's not my fault.
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
    
        # Default outputs
        try:
            ch = [r['leaves_channel_id'] for r in self.records if r["guild_id"] == member.guild.id][0]
            ch = self.bot.get_channel(ch)
        except (AttributeError, TypeError, IndexError):
            ch = None
        output = f"⬅ {member.mention} left the server."
        
        # Check if in mod action log and override to specific channels.
        try:
            async for x in member.guild.audit_logs(limit=1):
                if x.target == member:
                    if x.action == discord.AuditLogAction.kick:
                        output = f"👢 {member.mention} was kicked by {x.user} for {x.reason}."
                    elif x.action == discord.AuditLogAction.ban:
                        output = f"☠ {member.mention} was banned by {x.user} for {x.reason}."
        except discord.Forbidden:
            pass  # We cannot see audit logs.
        
        if ch is None:
            return  # Rip.
        
        await ch.send(output)
        
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        try:
            emojis = [r['emojis_channel_id'] for r in self.records if r["guild_id"] == guild.id][0]
        except IndexError:
            return
        
        ch = guild.get_channel(emojis)
        
        if ch is None:
            return
        
        # Find if it was addition or removal.
        new_emoji = [i for i in after if i not in before]
        if not new_emoji:
            try:
                removed_emoji = [i for i in before if i not in after][0]
                await ch.send(f"The '{removed_emoji}' emoji was removed")
            except IndexError:
                await ch.send("An emoji was removed.")
        else:
            notif = f"The {new_emoji[0]} emoji was created"
            if guild.me.permissions_in(ch).manage_emojis:
                emoji = await guild.fetch_emoji(new_emoji[0].id)
                notif += " by " + emoji.user.mention
            await ch.send(notif)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        try:
            unbans = [r['leaves_channel_id'] for r in self.records if r["guild_id"] == guild.id][0]
        except (IndexError, AttributeError):
            return

        ch = self.bot.get_channel(unbans)
        if ch is None:
            return
        
        await ch.send(f"🆗 {user} (ID: {user.id}) was unbanned.")
        
        
def setup(bot):
    bot.add_cog(Notifications(bot))
