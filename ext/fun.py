from discord.ext.commands.cooldowns import BucketType
from discord.ext import commands
from ext.utils import embed_utils
from importlib import reload
import datetime
import asyncio
import discord
import random
import re

poll_emojis = ["1\N{variation selector-16}\N{combining enclosing keycap}",
               "2\N{variation selector-16}\N{combining enclosing keycap}",
               "3\N{variation selector-16}\N{combining enclosing keycap}",
               "4\N{variation selector-16}\N{combining enclosing keycap}",
               "5\N{variation selector-16}\N{combining enclosing keycap}",
               "6\N{variation selector-16}\N{combining enclosing keycap}",
               "7\N{variation selector-16}\N{combining enclosing keycap}",
               "8\N{variation selector-16}\N{combining enclosing keycap}",
               "9\N{variation selector-16}\N{combining enclosing keycap}",
               ":keycap_ten:"]


class Fun(commands.Cog):
    """ Toys """
    
    def __init__(self, bot):
        self.bot = bot
        reload(embed_utils)
    
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
        await ctx.reply(f":8ball: {random.choice(res)}", mention_author=False)
    
    @commands.command()
    async def lenny(self, ctx):
        """ ( ͡° ͜ʖ ͡°) """
        lennys = ['( ͡° ͜ʖ ͡°)', '(ᴗ ͜ʖ ᴗ)', '(⟃ ͜ʖ ⟄) ', '(͠≖ ͜ʖ͠≖)', 'ʕ ͡° ʖ̯ ͡°ʔ', '( ͠° ͟ʖ ͡°)', '( ͡~ ͜ʖ ͡°)',
                  '( ͡◉ ͜ʖ ͡◉)', '( ͡° ͜V ͡°)', '( ͡ᵔ ͜ʖ ͡ᵔ )',
                  '(☭ ͜ʖ ☭)', '( ° ͜ʖ °)', '( ‾ ʖ̫ ‾)', '( ͡° ʖ̯ ͡°)', '( ͡° ل͜ ͡°)', '( ͠° ͟ʖ ͠°)', '( ͡o ͜ʖ ͡o)',
                  '( ͡☉ ͜ʖ ͡☉)', 'ʕ ͡° ͜ʖ ͡°ʔ', '( ͡° ͜ʖ ͡ °)']
        await ctx.reply(random.choice(lennys), mention_author=False)
    
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
        await ctx.reply(embed=e, mention_author=False)
    
    @commands.command(usage="Is this an example question? Yes, No")
    @commands.bot_has_permissions(add_reactions=True)
    async def poll(self, ctx, *, poll_string):
        """ Create a poll with multiple choice answers.
        
        End the question with a ? and separate each answer with """
        try:
            question, answers = poll_string.split('?')
            if answers:     
                answers = list(zip(poll_emojis, answers.split(',')))
        except ValueError:
            question = poll_string
            answers = []
        
        e = discord.Embed(color=0x7289DA)
        e.set_author(name=f"Poll")
        e.title = question + "?"
        e.description = ""
        e.set_footer(text=f"Poll created by {ctx.author.name}")
        
        for x, y in answers:
            e.description += f"{x} **{y}**\n"
        
        m = await ctx.reply(embed=e, mention_author=False)
        if answers:
            await embed_utils.bulk_react(ctx, m, [i[0] for i in answers])
        else:
            await embed_utils.bulk_react(ctx, m, ['👍', '👎'])
    
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
                return await ctx.reply(f"{resp} error, the wyr machine is broken.", mention_author=False)
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
            mc = f"**{title}...** \n{opta} \n{optb}"
            return mc
        
        m = await ctx.reply(await write(resp), mention_author=False)
        await embed_utils.bulk_react(ctx, m, ['🇦', '🇧', '🎲'])
        
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
        await ctx.reply(f"The secret tory is {random.choice(ctx.guild.members).mention}", mention_author=False)
    
    @commands.command(aliases=["choice", "pick", "select"], usage="Option 1, Option 2, Option 3 ...")
    async def choose(self, ctx, *, choices):
        """ Make a decision for me (seperate choices with commas)"""
        choices = discord.utils.escape_mentions(choices)
        x = choices.split(",")
        await ctx.reply(f"{random.choice(x)}", mention_author=False)
    
    @commands.command(hidden=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.cooldown(2, 60, BucketType.user)
    async def roulette(self, ctx):
        """ Russian Roulette """
        x = ["click.", "click.", "click.", "click.", "click.", "🔫 BANG!"]
        outcome = random.choice(x)
        if outcome == "🔫 BANG!":
            try:
                await ctx.reply(f"🔫 BANG!", mention_author=True)
                await ctx.author.kick(reason="roulette")
            except discord.Forbidden:
                await ctx.reply(f"Your skull is too thick to penetrate with these bullets.", mention_author=True)
        else:
            await ctx.reply(outcome, mention_author=False)
    
    @commands.command(aliases=["flip", "coinflip"])
    async def coin(self, ctx):
        """ Flip a coin """
        await ctx.reply(random.choice(["Heads", "Tails"]), mention_author=False)
    
    @commands.command(hidden=True)
    @commands.guild_only()
    async def triggered(self, ctx):
        """ WEEE WOO SPECIAL SNOWFLAKE DETECTED """
        trgmsg = await ctx.reply("🚨 🇹 🇷 🇮 🇬 🇬 🇪 🇷  🇼 🇦 🇷 🇳 🇮 🇳 🇬  🚨", mention_author=False)
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
        await ctx.reply("https://www.youtube.com/watch?v=xECUrlnXCqk", mention_author=False)
    
    @commands.command(aliases=["alreadydead"], hidden=True)
    @commands.is_owner()
    async def dead(self, ctx):
        """ STOP STOP HE'S ALREADY DEAD """
        await ctx.reply("https://www.youtube.com/watch?v=mAUY1J8KizU", mention_author=False)
    
    @commands.command(aliases=["urbandictionary"])
    async def ud(self, ctx, *, lookup: commands.clean_content):
        """ Lookup a definition from urban dictionary """
        await ctx.trigger_typing()
        url = f"http://api.urbandictionary.com/v0/define?term={lookup}"
        async with self.bot.session.get(url) as resp:
            if resp.status != 200:
                await ctx.reply(f"🚫 HTTP Error, code: {resp.status}", mention_author=False)
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
            return await ctx.reply(embed=e, mention_author=False)
        
        await embed_utils.paginate(ctx, embeds)
    
    @commands.command(usage="1d6+3")
    async def roll(self, ctx, *, roll_string="d20"):
        """ Roll a set of dice in the format XdY+Z. Start the roll with 'adv' or 'dis' to roll with (dis)advantage """
        
        advantage = True if roll_string.startswith("adv") else False
        disadvantage = True if roll_string.startswith("dis") else False
        
        e = discord.Embed()
        e.title = "🎲 Dice Roller"
        if advantage:
            e.title += " (Advantage)"
        if disadvantage:
            e.title += " (Disadvantage)"
        
        e.description = ""
        
        roll_list = roll_string.split(' ')
        if len(roll_list) == 1:
            roll_list = [roll_string]
        
        total = 0
        bonus = 0
        for roll in roll_list:
            if not roll:
                continue
            
            if roll.isdigit():
                if roll == "1":
                    e.description += f"{roll}: **1**\n"
                    total += 1
                    continue
                result = random.randint(1, int(roll))
                e.description += f"{roll}: **{result}**\n"
                total += int(result)
                continue
            
            try:
                if "+" in roll:
                    roll, b = roll.split('+')
                    bonus += int(b)
                elif "-" in roll:
                    roll, b = roll.split("-")
                    bonus -= int(b)
            except ValueError:
                bonus = 0
            
            if roll in ["adv", "dis"]:
                sides = 20
                dice = 1
            else:
                try:
                    dice, sides = roll.split('d')
                    dice = int(dice)
                except ValueError:
                    dice = 1
                    try:
                        sides = int(roll.strip('d'))
                    except ValueError:
                        continue
                else:
                    sides = int(sides)
                
                if dice > 100 or sides > 10001:
                    return await ctx.reply('Fuck off, no.', mention_author=True)
            
            e.description += f"{roll}: "
            total_roll = 0
            roll_info = ""
            curr_rolls = []
            for i in range(dice):
                first_roll = random.randrange(1, 1 + sides)
                roll_outcome = first_roll
                
                if roll in ["adv", "dis"]:
                    second_roll = random.randrange(1, 1 + sides)
                    if (advantage and second_roll > first_roll) or (disadvantage and second_roll < first_roll):
                        roll_outcome = second_roll
                        roll_info += f"({first_roll}, __{second_roll}__)"
                    else:
                        roll_info += f"(__{first_roll}__, {second_roll})"
                else:
                    curr_rolls.append(str(roll_outcome))
                
                total_roll += roll_outcome
                
                if dice == 1 and sides >= 20:
                    if roll_outcome == 1:
                        e.colour = discord.Colour.red()
                        e.set_footer(text="Critical Failure")
                    elif roll_outcome == sides:
                        e.colour = discord.Colour.green()
                        e.set_footer(text="Critical.")
            
            roll_info += ", ".join(curr_rolls)
            
            if bonus:
                roll_info += f" + {str(bonus)}" if bonus > 0 else f" {str(bonus).replace('-', ' - ')}"
            total_roll += bonus
            e.description += f"{roll_info} = **{total_roll}**" + "\n"
            
            total += total_roll
        
        if len(roll_list) > 1:
            e.description += f"\n**Total: {total}**"
        
        await ctx.reply(embed=e, mention_author=False)


def setup(bot):
    bot.add_cog(Fun(bot))
