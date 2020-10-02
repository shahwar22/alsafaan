import re
from collections import defaultdict

import discord
from discord.ext import commands

import ext.utils.football as football
import ext.utils.embed_utils as embed_utils
from importlib import reload


class Test(commands.Cog):
    """ Test Commands """
    def __init__(self, bot):
        self.bot = bot
        reload(football)
        reload(embed_utils)


def setup(bot):
    bot.add_cog(Test(bot))