import discord
from discord.ext import commands
from collections import Counter
import datetime


class GlobalChecks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_check(self.disabled_commands)
        self.bot.add_check(self.ignored)
        self.bot.commands_used = Counter()
    
    def ignored(self, ctx):
        return ctx.author.id not in self.bot.ignored
    
    def disabled_commands(self, ctx):
        if ctx.author.permissions_in(ctx.channel).manage_channels:
            return True
        try:
            if ctx.command.parent is not None:
                if ctx.command.parent.name in self.bot.disabled_cache[ctx.guild.id]:
                    raise commands.DisabledCommand
            
            if ctx.command.name in self.bot.disabled_cache[ctx.guild.id]:
                raise commands.DisabledCommand
            else:
                return True
        except (KeyError, AttributeError):
            return True


class Reactions(commands.Cog):
    """ This is a utility cog for the r/NUFC discord to react to certain messages. This category has no commands. """
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        self.bot.commands_used[ctx.command.name] += 1
    
    # TODO: Move to notifications.
    # TODO: Create custom Reaction setups per serve r
    # TODO: Bad words filter.
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        # ignore bots
        if message.author.bot:
            return
        
        # ignore dms
        if message.guild is None:
            return
        
        # ignore Toonbot command messages.
        for i in self.bot.prefix_cache[message.guild.id]:
            if message.content.startswith(i):
                return
        
        # TODO - Cross server.
        if not message.guild.id == 332159889587699712:
            return
        
        # Filter out deleted numbers - Toonbot.
        try:
            int(message.content)
        except ValueError:
            pass
        else:
            return
        
        # Todo: Code "If message was not deleted by bot or user return "
        
        delchan = self.bot.get_channel(id=335816981423063050)
        e = discord.Embed(title="Deleted Message")
        e.description = f"'{message.content}'"
        e.set_author(name=message.author.name)
        e.add_field(name="User ID", value=message.author.id)
        e.add_field(name="Channel", value=message.channel.mention)
        e.set_thumbnail(url=message.author.avatar_url)
        e.timestamp = datetime.datetime.now()
        e.set_footer(text=f"Created: {message.created_at}")
        e.colour = message.author.color
        if message.attachments:
            att = message.attachments[0]
            if hasattr(att, "height"):
                e.add_field(name=f"Attachment info {att.filename} ({att.size} bytes)",
                            value=f"{att.height}x{att.width}")
                e.set_image(url=att.proxy_url)
        await delchan.send(embed=e)
    
    @commands.Cog.listener()
    async def on_message(self, m):
        c = m.content.lower()
        # ignore bot messages
        if m.author.bot:
            return
        
        if m.guild and m.guild.id == 332159889587699712:
            autokicks = ["make me a mod", "make me mod", "give me mod"]
            for i in autokicks:
                if i in c:
                    try:
                        await m.author.kick(reason="Asked to be made a mod.")
                    except discord.Forbidden:
                        return await m.channel.send(f"Done. {m.author.mention} is now a moderator.")
                    await m.channel.send(f"{m.author} was auto-kicked.")
            if "https://www.reddit.com/r/" in c and "/comments/" in c:
                if "nufc" not in c:
                    rm = "*Reminder: Please do not vote on submissions or comments in other subreddits.*"
                    await m.channel.send(rm)
        # Emoji reactions
        if "toon toon" in c:
            try:
                await m.channel.send("**BLACK AND WHITE ARMY**")
            except discord.Forbidden:
                pass


def setup(bot):
    bot.add_cog(Reactions(bot))
    bot.add_cog(GlobalChecks(bot))
