import re

from discord.ext.commands.cooldowns import BucketType
from discord.ext import commands
import datetime
import asyncio
import discord
import random

from ext.utils.embed_utils import paginate


class Fun(commands.Cog):

    """ Toys """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(hidden=True)
    async def itscominghome(self, ctx):
        """ Football's coming home """
        await ctx.send("No it's fucking not.")
    
    @commands.command(name="8ball", aliases=["8"])
    async def eightball(self, ctx):
        """ Magic Geordie 8ball """
        
        res = ["probably", "Aye", "aye mate", "wey aye.", "aye trust is pal.",
               "Deffo m8", "fuckin aye.", "fucking rights", "think so", "absofuckinlutely",
               # Negative
               "me pal says nar.", "divn't think so", "probs not like.", "nar pal soz", "fuck no",
               "deffo not.", "nar", "wey nar", "fuck off ya daftie", "absofuckinlutely not",
               # later
               "am not sure av just had a bucket", "al tel you later", "giz a minute to figure it out",
               "mebbe like", "dain't bet on it like"
               ]
        await ctx.send(f":8ball: {ctx.author.mention} {random.choice(res)}")
    
    @commands.command()
    async def lenny(self, ctx):
        """ ( ͡° ͜ʖ ͡°) """
        lennys = ['( ͡° ͜ʖ ͡°)', '(ᴗ ͜ʖ ᴗ)', '(⟃ ͜ʖ ⟄) ', '(͠≖ ͜ʖ͠≖)', 'ʕ ͡° ʖ̯ ͡°ʔ', '( ͠° ͟ʖ ͡°)', '( ͡~ ͜ʖ ͡°)',
                  '( ͡◉ ͜ʖ ͡◉)', '( ͡° ͜V ͡°)', '( ͡ᵔ ͜ʖ ͡ᵔ )',
                  '(☭ ͜ʖ ☭)', '( ° ͜ʖ °)', '( ‾ ʖ̫ ‾)', '( ͡° ʖ̯ ͡°)', '( ͡° ل͜ ͡°)', '( ͠° ͟ʖ ͠°)', '( ͡o ͜ʖ ͡o)',
                  '( ͡☉ ͜ʖ ͡☉)', 'ʕ ͡° ͜ʖ ͡°ʔ', '( ͡° ͜ʖ ͡ °)']
        await ctx.send(random.choice(lennys))
    
    @commands.command(aliases=["horo"])
    async def horoscope(self, ctx, *, sign: commands.clean_content):
        """ Find out your horoscope for this week """
        sign = sign.title()
        horos = {
            "Aquarius": "♒", "Aries": "♈", "Cancer": "♋", "Capricorn": "♑", "Gemini": "♊", "Leo": "♌", "Libra": "♎",
            "Scorpius": "♏", "Scorpio": "♏", "Sagittarius": "♐", "Pisces": "♓", "Taurus": "♉", "Virgo": "♍",
        }
        
        # Get Sunday Just Gone.
        sun = datetime.datetime.now().date() - datetime.timedelta(days=datetime.datetime.now().weekday() + 1)
        # Get Saturday Coming
        sat = sun + datetime.timedelta(days=6)
        
        sunstring = sun.strftime('%a %d %B %Y')
        satstring = sat.strftime('%a %d %B %Y')
        
        e = discord.Embed()
        e.colour = 0x7289DA
        e.description = "*\"The stars and planets will not affect your life in any way\"*"
        try:
            e.title = f"{horos[sign]} {sign}"
        except KeyError:
            e.title = f"{sign} {sign}"
        ftstr = f"Horoscope for {sunstring} - {satstring}"
        e.set_footer(text=ftstr)
        await ctx.send(embed=e)
    
    @commands.command(usage="poll <your question>")
    @commands.bot_has_permissions(add_reactions=True)
    async def poll(self, ctx, *, question: commands.clean_content):
        """ Thumbs up / Thumbs Down """
        e = discord.Embed(color=0x7289DA)
        e.title = f"Poll"
        e.description = question
        e.set_footer(text=f"Poll created by {ctx.author.name}")
        
        m = await ctx.send(embed=e)
        await m.add_reaction('👍')
        await m.add_reaction('👎')
    
    @commands.command(aliases=["rather"])
    @commands.bot_has_permissions(add_reactions=True)
    async def wyr(self, ctx):
        """ Would you rather... """
        async def fetch():
            async with self.bot.session.get("http://www.rrrather.com/botapi") as response:
                if response.status != "200":
                    return int(response.status)
                response = await response.json()
                return response
        
        # Reduce dupes.
        cache = []
        tries = 0
        
        resp = None
        
        while tries < 10:
            resp = await fetch()
            if isinstance(resp, int):
                return await ctx.send(f"{resp} error, the wyr machine is broken :(")
            # Skip stupid shit.
            if resp["choicea"] == resp["choiceb"]:
                continue
            if resp in cache:
                tries += 1
                continue
            else:
                cache += resp
                break
        
        if resp is None:
            return
        
        async def write(response):
            title = response["title"].strip().capitalize().rstrip('.?,:')
            opta = response["choicea"].strip().capitalize().rstrip('.?,!').lstrip('.')
            optb = response["choiceb"].strip().capitalize().rstrip('.?,!').lstrip('.')
            mc = f"{ctx.author.mention} **{title}...** \n{opta} \n{optb}"
            return mc
        
        async def react(message):
            self.bot.loop.create_task(message.add_reaction('🇦'))
            self.bot.loop.create_task(message.add_reaction('🇧'))
            self.bot.loop.create_task(message.add_reaction('🎲'))
        
        m = await ctx.send(await write(resp))
        
        try:
            await react(m)
        except discord.NotFound:
            pass  # Early clicks.
        
        # Re-roller
        def check(reaction, user):
            if reaction.message.id == m.id and user == ctx.author:
                e = str(reaction.emoji)
                return e == '🎲'
        
        while True:
            try:
                rea = await self.bot.wait_for("reaction_add", check=check, timeout=120)
            except asyncio.TimeoutError:
                await m.remove_reaction('🎲', ctx.me)
                break
            rea = rea[0]
            if rea.emoji == '🎲':
                resp = await fetch()
                try:
                    await m.clear_reactions()
                except discord.Forbidden:
                    pass
                await m.edit(content=await write(resp))
    
    @commands.command(hidden=True)
    @commands.is_owner()
    async def secrettory(self, ctx):
        await ctx.send(f"The secret tory is {random.choice(ctx.guild.members).mention}")
    
    @commands.command(aliases=["choice", "pick", "select"], usage="Option 1, Option 2, Option 3 ...")
    async def choose(self, ctx, *, choices):
        """ Make a decision for me (seperate choices with commas)"""
        choices = discord.utils.escape_mentions(choices)
        x = choices.split(",")
        await ctx.send(f"{ctx.author.mention}: {random.choice(x)}")
    
    @commands.command(hidden=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.cooldown(2, 60, BucketType.user)
    async def roulette(self, ctx):
        """ Russian Roulette """
        x = ["click.", "click.", "click.", "click.", "click.", "🔫 BANG!"]
        outcome = random.choice(x)
        if outcome == "🔫 BANG!":
            try:
                await ctx.author.kick(reason="roulette")
                await ctx.send(f"🔫 BANG! {ctx.author.mention} was kicked.")
            except discord.Forbidden:
                await ctx.send(
                    f"{ctx.author.mention} fired but the bullet bounced off their thick skull. (I can't kick that "
                    f"user.)")
        else:
            await ctx.send(outcome)
    
    @commands.command(aliases=["flip", "coinflip"])
    async def coin(self, ctx):
        """ Flip a coin """
        await ctx.send(random.choice(["Heads", "Tails"]))
    
    @commands.command(hidden=True)
    @commands.guild_only()
    async def triggered(self, ctx):
        """ WEEE WOO SPECIAL SNOWFLAKE DETECTED """
        trgmsg = await ctx.send("🚨 🇹 🇷 🇮 🇬 🇬 🇪 🇷  🇼 🇦 🇷 🇳 🇮 🇳 🇬  🚨")
        for i in range(5):
            await trgmsg.edit(content="⚠ 🇹 🇷 🇮 🇬 🇬 🇪 🇷  🇼 🇦 🇷 🇳 🇮 🇳 🇬  ⚠")
            await asyncio.sleep(1)
            await trgmsg.edit(content="🚨 🇹 🇷 🇮 🇬 🇬 🇪 🇷  🇼 🇦 🇷 🇳 🇮 🇳 🇬  🚨")
            await asyncio.sleep(1)
    
    @commands.command(hidden=True)
    @commands.has_permissions(add_reactions=True)
    async def uprafa(self, ctx):
        """ Adds an upvote reaction to the last 10 messages """
        async for message in ctx.channel.history(limit=10):
            await message.add_reaction(":upvote:332196220460072970")
    
    @commands.command(hidden=True)
    @commands.has_permissions(add_reactions=True)
    async def downrafa(self, ctx):
        """ Adds a downvote reaction to the last 10 messages """
        async for message in ctx.channel.history(limit=10):
            await message.add_reaction(":downvote:332196251959427073")
    
    @commands.command(hidden=True)
    @commands.has_permissions(manage_messages=True)
    async def norafa(self, ctx, *, msgs=30):
        """ Remove reactions from last x messages """
        async for message in ctx.channel.history(limit=msgs):
            await message.clear_reactions()
    
    @commands.command(aliases=["ttj"], hidden=True)
    @commands.is_owner()
    async def thatsthejoke(self, ctx):
        """ MENDOZAAAAAAAAAAAAA """
        await ctx.send("https://www.youtube.com/watch?v=xECUrlnXCqk")
    
    @commands.command(aliases=["alreadydead"], hidden=True)
    @commands.is_owner()
    async def dead(self, ctx):
        """ STOP STOP HE'S ALREADY DEAD """
        await ctx.send("https://www.youtube.com/watch?v=mAUY1J8KizU")
    
    @commands.command(aliases=["urbandictionary"])
    async def ud(self, ctx, *, lookup: commands.clean_content):
        """ Lookup a definition from urban dictionary """
        await ctx.trigger_typing()
        url = f"http://api.urbandictionary.com/v0/define?term={lookup}"
        async with self.bot.session.get(url) as resp:
            if resp.status != 200:
                await ctx.send(f"🚫 HTTP Error, code: {resp.status}")
                return
            resp = await resp.json()
        
        tn = "http://d2gatte9o95jao.cloudfront.net/assets/apple-touch-icon-2f29e978facd8324960a335075aa9aa3.png"
        
        embeds = []
        
        resp = resp["list"]
        # Populate Embed, add to list
        e = discord.Embed(color=0xFE3511)
        e.set_author(name=f"Urban Dictionary")
        e.set_thumbnail(url=tn)
        e.set_footer(icon_url="http://pix.iemoji.com/twit33/0056.png")
        un = ctx.author
        count = 0
        if resp:
            for i in resp:
                count += 1
                e.title = i["word"]
                e.url = i["permalink"]
                de = i["definition"]
                for z in re.finditer(r'\[(.*?)\]', de):
                    z1 = z.group(1).replace(' ', "%20")
                    z = z.group()
                    de = de.replace(z,
                                    f"{z}(https://www.urbandictionary.com/define.php?term={z1})")
                e.description = de[:2047]
                if i["example"]:
                    e.add_field(name="Example", value=i["example"])
                
                e.add_field(name='Votes', value="👍🏻{i['thumbs_up']} 👎🏻{i['thumbs_down']}")
                this_e = e.copy()
                embeds.append(this_e)
                e.clear_fields()
        else:
            e.description = f"🚫 No results found for {lookup}."
            e.set_footer(text=un)
            return await ctx.send(embed=e)
        
        await paginate(ctx, embeds)


def setup(bot):
    bot.add_cog(Fun(bot))
