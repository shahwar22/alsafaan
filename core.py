import discord
from discord.ext import commands
from datetime import datetime
import aiohttp
import asyncio
import asyncpg
import json

from discord.ext.commands import ExtensionAlreadyLoaded

with open('credentials.json') as f:
    credentials = json.load(f)


async def run():
    db = await asyncpg.create_pool(**credentials['Postgres'])
    bot = Bot(database=db)
    try:
        await bot.start(credentials['bot']['token'])
    except KeyboardInterrupt:
        for i in bot.cogs:
            bot.unload_extension(i.name)
        await db.close()
        bot.fixture_driver.quit()
        bot.score_driver.quit()
        await bot.logout()


class Bot(commands.Bot):
    def __init__(self, **kwargs):
        
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(
            description="Football lookup bot by Painezor#8489",
            command_prefix=".tb ",
            owner_id=210582977493598208,
            activity=discord.Game(name="Use .tb help"),
            intents=intents
        )
        self.fixture_driver = None
        self.score_driver = None
        self.db = kwargs.pop("database")
        self.credentials = credentials
        self.initialised_at = datetime.utcnow()
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def on_ready(self):
        print(f'{self.user}: {datetime.now().strftime("%d-%m-%Y %H:%M:%S")}\n-----------------------------------')
        # Startup Modules
        load = [
            'ext.reactions',  # needs to be loaded fist.
            'ext.automod', 'ext.admin', 'ext.errors', 'ext.fixtures', 'ext.fun', 'ext.help', 'ext.images', 'ext.info',
            'ext.mod', 'ext.mtb', 'ext.notifications', 'ext.nufc', 'ext.quotes', 'ext.reminders', 'ext.scores',
            'ext.sidebar', 'ext.twitter', 'ext.lookups', "ext.transfers", 'ext.tv',
        ]
        for c in load:
            try:
                self.load_extension(c)
            except ExtensionAlreadyLoaded:
                pass
            except Exception as e:
                print(f'Failed to load cog {c}\n{type(e).__name__}: {e}')
            else:
                print(f"Loaded extension {c}")


loop = asyncio.get_event_loop()
loop.run_until_complete(run())
