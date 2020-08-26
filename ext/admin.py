from discord.ext import commands
import discord
from os import system
import inspect

# to expose to the eval command
import datetime
from collections import Counter

from discord.ext.commands import ExtensionNotLoaded

from ext.utils import codeblocks


class Admin(commands.Cog):
    """Code debug & 1oading of modules"""

    def __init__(self, bot):
        self.bot = bot
        self.bot.socket_stats = Counter()
        self.bot.loop.create_task(self.update_ignored())

    async def update_ignored(self):
        connection = await self.bot.db.acquire()
        records = await connection.fetch(""" SELECT * FROM ignored_users """)
        self.bot.ignored = {}
        for r in records:
            self.bot.ignored.update({r["user_id"]: r["reason"]})

    @commands.command()
    @commands.is_owner()
    async def setavatar(self, ctx, new_pic: str):
        """ Change the bot's avatar """
        async with self.bot.session.get(new_pic) as resp:
            if resp.status != 200:
                await ctx.send(f"HTTP Error: Status Code {resp.status}")
                return None
            profile_img = await resp.read()
            await self.bot.user.edit(avatar=profile_img)

    @commands.command(aliases=['clean_console', 'cc'])
    @commands.is_owner()
    async def clear_console(self, ctx):
        """ Clear the command window. """
        system('cls')
        print(f'{self.bot.user}: {self.bot.initialised_at}\n-----------------------------------------')
        await ctx.send("Console cleared.")
        print(f"Console cleared at: {datetime.datetime.utcnow()}")

    @commands.command(aliases=["releoad", "relaod"])  # I can't fucking type.
    @commands.is_owner()
    async def reload(self, ctx, *, module: str):
        """Reloads a module."""
        try:
            self.bot.reload_extension(module)
        except ExtensionNotLoaded:
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(codeblocks.error_to_codeblock(e))
        else:
            await ctx.send(f':gear: Reloaded {module}')

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx, *, module: str):
        """Loads a module."""
        try:
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(codeblocks.error_to_codeblock(e))
        else:
            await ctx.send(f':gear: Loaded {module}')

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx, *, module: str):
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send(codeblocks.error_to_codeblock(e))
        else:
            await ctx.send(f':gear: Unloaded {module}')

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx, *, code: str):
        """Evaluates code."""
        code = code.strip('` ')

        env = {
            'bot': self.bot,
            'ctx': ctx,
        }
        env.update(globals())
        try:
            result = eval(code, env)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            etc = codeblocks.error_to_codeblock(e)
            if len(etc) > 2000:
                await ctx.send('Too long for discord, output sent to console.')
            else:
                return await ctx.send(etc)
        else:
            await ctx.send(f"```py\n{result}```")

    @commands.command()
    @commands.is_owner()
    async def guilds(self, ctx):
        guilds = []
        for i in self.bot.guilds:
            guilds.append(f"{i.id}: {i.name}")
        guilds = "\n".join(guilds)
        await ctx.send(guilds)

    @commands.command()
    @commands.is_owner()
    async def commandstats(self, ctx):
        p = commands.Paginator()
        counter = self.bot.commands_used
        width = len(max(counter, key=len))
        total = sum(counter.values())

        fmt = '{0:<{width}}: {1}'
        p.add_line(fmt.format('Total', total, width=width))
        for key, count in counter.most_common():
            p.add_line(fmt.format(key, count, width=width))

        for page in p.pages:
            await ctx.send(page)

    @commands.is_owner()
    @commands.command(aliases=['logout', 'restart'])
    async def kill(self, ctx):
        """Restarts the bot"""
        await self.bot.db.close()
        await self.bot.logout()
        await ctx.send(":gear: Restarting.")

    @commands.is_owner()
    @commands.command(aliases=['streaming', 'watching', 'listening'])
    async def playing(self, ctx, *, status):
        """ Change status to <cmd> {status} """
        values = {"playing": 0, "streaming": 1, "watching": 2, "listening": 3}

        act = discord.Activity(type=values[ctx.invoked_with], name=status)

        await self.bot.change_presence(activity=act)
        await ctx.send(f"Set status to {ctx.invoked_with} {status}")

    @commands.command()
    @commands.is_owner()
    async def shared(self, ctx, *, user_id: int):
        """ Check ID for shared servers """
        matches = []
        for i in self.bot.guilds:
            if i.get_member(user_id) is not None:
                matches.append(f"{i.name} ({i.id})")

        e = discord.Embed(color=0x00ff00)
        if not matches:
            e.description = f"User id {user_id} not found on shared servers."
            return await ctx.send(embed=e)

        e.title = f"Shared servers for User ID: {user_id}"
        e.description = "\n".join(matches)
        await ctx.send(embed=e)

    @commands.command()
    @commands.is_owner()
    async def ignore(self, ctx, users: commands.Greedy[discord.User], *, reason=None):
        """ Toggle Ignoring commands from a user (reason optional)"""
        replies = []
        connection = await self.bot.db.acquire()
        for i in users:
            if i.id in self.bot.ignored:
                sql = """ INSERT INTO ignored_users (user_id,reason) = ($1,$2) """
                escaped = [i.id, reason]
                replies.append(f"Stopped ignoring commands from {i}.")
            else:
                sql = """ DELETE FROM ignored_users WHERE user_id = $1"""
                escaped = [i.id]
                self.bot.ignored.update({f"{i.id}": reason})
                replies.append(f"Ignoring commands from {i}.")
            await connection.execute(sql, *escaped)
        await self.bot.db.release(connection)
        await ctx.send("\n".join(replies))


def setup(bot):
    bot.add_cog(Admin(bot))
