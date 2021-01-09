import discord
from discord.ext import commands
from collections import Counter


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
