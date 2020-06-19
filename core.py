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
        await db.close()
        await bot.logout()


class Bot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(
            description="Football lookup bot by Painezor#8489",
            help_command=Help(),
            command_prefix=".tb ",
            owner_id=210582977493598208,
            activity=discord.Game(name="Use .tb help")
        )
        self.db = kwargs.pop("database")
        self.credentials = credentials
        self.initialised_at = datetime.utcnow()
        self.session = aiohttp.ClientSession(loop=self.loop)
    
    async def on_ready(self):
        print(f'{self.user}: {datetime.now().strftime("%d-%m-%Y %H:%M:%S")}\n-----------------------------------')
        # Startup Modules
        load = [
            'ext.reactions',  # needs to be loaded fist.
            'ext.automod', 'ext.admin', 'ext.errors', 'ext.fixtures', 'ext.fun', 'ext.images', 'ext.info', 'ext.mod',
            'ext.mtb', 'ext.notifications', 'ext.nufc', 'ext.quotes', 'ext.reminders', 'ext.scores', 'ext.sidebar',
            'ext.twitter', 'ext.transfer_lookup', "ext.transfer_ticker", 'ext.tv',
        ]
        for c in load:
            try:
                self.load_extension(c)
            except ExtensionAlreadyLoaded:
                pass
            except Exception as e:
                print(f'Failed to load cog {c}\n{type(e).__name__}: {e}')


loop = asyncio.get_event_loop()
loop.run_until_complete(run())
