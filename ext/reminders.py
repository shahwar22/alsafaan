from copy import deepcopy

from discord.ext import commands
import datetime
import discord

from ext.utils.embed_utils import paginate
from ext.utils import timed_events

from importlib import reload


class Reminders(commands.Cog):
    """ Set yourself reminders """
    def __init__(self, bot):
        self.bot = bot
        self.active_module = True
        self.bot.reminders = []  # A list of tasks.
        self.bot.loop.create_task(self.spool_initial())
        reload(timed_events)
    
    def cog_unload(self):
        for i in self.bot.reminders:
            i.cancel()
    
    async def spool_initial(self):
        connection = await self.bot.db.acquire()
        records = await connection.fetch("""SELECT * FROM reminders""")
        async with connection.transaction():
            for r in records:
                self.bot.reminders.append(self.bot.loop.create_task(timed_events.spool_reminder(self.bot, r)))
        await self.bot.db.release(connection)
    
    @commands.group(aliases=['reminder', 'remind', 'remindme'],
                    usage="<Amount of time> <Reminder message>",
                    invoke_without_command=True)
    async def timer(self, ctx, time, *, message: commands.clean_content):
        """ Remind you of something at a specified time.
            Format is remind 1d2h3m4s <note>, e.g. remind 1d3h Kickoff."""
        delta = await timed_events.parse_time(time.lower())
        
        remind_at = datetime.datetime.now() + delta
        human_time = datetime.datetime.strftime(remind_at, "%a %d %b at %H:%M:%S")
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            record = await connection.fetchrow(""" INSERT INTO reminders
            (message_id, channel_id, guild_id, reminder_content, created_time, target_time, user_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
                                               ctx.message.id, ctx.channel.id, ctx.guild.id, message,
                                               ctx.message.created_at,
                                               remind_at, ctx.author.id)
        await self.bot.db.release(connection)
        self.bot.reminders.append(self.bot.loop.create_task(timed_events.spool_reminder(self.bot, record)))
        
        e = discord.Embed()
        e.title = "⏰ Reminder Set"
        e.description = f"**{human_time}**\n{message}"
        e.colour = 0x00ffff
        e.timestamp = remind_at
        await ctx.send(embed=e)
    
    @timer.command(aliases=["timers"])
    async def list(self, ctx):
        """ Check your active reminders """
        connection = await self.bot.db.acquire()
        records = await connection.fetch(""" SELECT * FROM reminders WHERE user_id = $1 """, ctx.author.id)
        await self.bot.db.release(connection)
        
        embeds = []
        e = discord.Embed()
        e.description = ""
        e.colour = 0x7289DA
        e.title = f"⏰ {ctx.author.name}'s reminders"
        for r in records:
            delta = r['target_time'] - datetime.datetime.now()
            this_string = "**`" + str(delta).split(".")[0] + "`** " + r['reminder_content'] + "\n"
            if len(e.description) + len(this_string) > 2000:
                embeds.append(deepcopy(e))
                e.description = ""
            else:
                e.description += this_string
        embeds.append(e)
        await paginate(ctx, embeds)


# TODO: timed poll.


def setup(bot):
    bot.add_cog(Reminders(bot))
