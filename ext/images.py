import os
import typing
from PIL import Image, ImageDraw, ImageOps, ImageFont
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType
import textwrap
import discord
from lxml import html
import random
import json
from io import BytesIO

from ext.utils import embed_utils

targets = ["andejay", "andy_the_cupid_stunt", "chaosmachinegr", "Charede", "darknessdreams_1"
           "DobbyM8", "frostinator08", "GameProdigy", "Jamdearest", "KidneyCowboy", "Lord_Zath", "Masterchief1567",
           "nebelfuss", "painezor", "Pelzmorph", "pops_place", "Redberen", "SeaRaptor00", "song_mg", "spacepickshovel",
           "StatsBloke", "tcfreer", "texashula", "the_shadewe", "thegrumpybeard", "TigersDen", "wookie_legend",
           "Xairen", "Yuzral"]


def make_bauble(img):
    # Open Avatar file.
    avatar = Image.open(r"F:/Logos/" + img).convert(mode="RGBA")
    
    # Create Canvas & Paste Avatar
    canvas = Image.new("RGBA", (300, 350), (0, 0, 0, 255))
    canvas.paste(avatar, (0, 50))
    
    # Apply Bauble mask.
    msk = Image.open("images/Bauble_MASK.png").convert('L')
    canvas.putalpha(msk)
    
    # Apply bauble top overlay
    bauble_top = Image.open("images/BaubleTop.png").convert(mode="RGBA")
    canvas.paste(bauble_top, mask=bauble_top)
    
    output_loc = r"F:/Logo-Output/" + img.split('.')[0]
    canvas.save(output_loc + ".png")


def bulk_image():
    directory = r'F:\Logos'
    for img in os.listdir(directory):
        make_bauble(img)


def draw_tinder(image, av, name):
    # Base Image
    im = Image.open("Images/tinder.png").convert(mode="RGBA")
    # Prepare mask
    msk = Image.open("Images/circlemask.png").convert('L')
    msk = ImageOps.fit(msk, (185, 185))
    
    # User Avatar
    avt = Image.open(BytesIO(av)).convert(mode="RGBA")
    avo = ImageOps.fit(avt, (185, 185))
    avo.putalpha(msk)
    im.paste(avo, box=(100, 223, 285, 408), mask=msk)
    
    # Player
    user_av = Image.open(BytesIO(image)).convert(mode="RGBA")
    plo = ImageOps.fit(user_av, (185, 185), centering=(0.5, 0.0))
    plo.putalpha(msk)
    im.paste(plo, box=(313, 223, 498, 408), mask=msk)
    # Write "it's a mutual match"
    txt = f"You and {name} have liked each other."
    f = ImageFont.truetype('Whitney-Medium.ttf', 24)
    w, h = f.getsize(txt)
    d = ImageDraw.Draw(im)
    d.text((300 - w / 2, 180), txt, font=f, fill="#ffffff")

    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    return output


def draw_bob(image, response):
    """ Pillow Bob Rossifying """
    im = Image.open(BytesIO(image)).convert(mode="RGBA")
    bob = Image.open("Images/rossface.png")
    for coords in response:
        x = int(coords["faceRectangle"]["left"])
        y = int(coords["faceRectangle"]["top"])
        w = int(coords["faceRectangle"]["width"])
        h = int(coords["faceRectangle"]["height"])
        roll = int(coords["faceAttributes"]["headPose"]["roll"]) * -1
        vara = int(x - (w / 4))
        varb = int(y - (h / 2))
        varc = int(x + (w * 1.25))
        vard = int((y + (h * 1.25)))
        xsize = varc - vara
        ysize = vard - varb
        thisbob = ImageOps.fit(bob, (xsize, ysize)).rotate(roll)
        im.paste(thisbob, box=(vara, varb, varc, vard), mask=thisbob)
    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    return output


def draw_knob(image, response):
    im = Image.open(BytesIO(image)).convert(mode="RGBA")
    knob = Image.open("Images/knob.png")
    
    for coords in response:
        mlx = int(coords["faceLandmarks"]["mouthLeft"]["x"])
        mrx = int(coords["faceLandmarks"]["mouthRight"]["x"])
        lipy = int(coords["faceLandmarks"]["upperLipBottom"]["y"])
        lipx = int(coords["faceLandmarks"]["upperLipBottom"]["x"])
        
        angle = int(coords["faceAttributes"]["headPose"]["roll"] * -1)
        w = int((mrx - mlx)) * 2
        h = w
        tk = ImageOps.fit(knob, (w, h)).rotate(angle)
        im.paste(tk, box=(int(lipx - w / 2), int(lipy)), mask=tk)
    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    return output


def draw_eyes(image, response):
    """ Draws the eyes """
    im = Image.open(BytesIO(image))
    for i in response:
        # Get eye bounds
        lix = int(i["faceLandmarks"]["eyeLeftInner"]["x"])
        lox = int(i["faceLandmarks"]["eyeLeftOuter"]["x"])
        lty = int(i["faceLandmarks"]["eyeLeftTop"]["y"])
        # lby = int(i["faceLandmarks"]["eyeLeftBottom"]["y"])
        rox = int(i["faceLandmarks"]["eyeRightOuter"]["x"])
        rix = int(i["faceLandmarks"]["eyeRightInner"]["x"])
        rty = int(i["faceLandmarks"]["eyeRightTop"]["y"])
        # rby = int(i["faceLandmarks"]["eyeRightBottom"]["y"])
        
        lw = lix - lox
        rw = rox - rix
        
        # Inflate
        lix = lix + lw
        lox = lox - lw
        lty = lty - lw
        # lby = lby + lw
        rox = rox + rw
        rix = rix - rw
        rty = rty - rw
        # rby = rby + rw
        
        # Recalculate with new sizes.
        lw = lix - lox
        rw = rox - rix
        
        # Open Eye Image, resize, paste twice
        eye = Image.open("Images/eye.png")
        left = ImageOps.fit(eye, (lw, lw))
        right = ImageOps.fit(eye, (rw, rw))
        im.paste(left, box=(lox, lty), mask=left)
        im.paste(right, box=(rix, rty), mask=right)
    
    # Prepare for sending and return
    output = BytesIO()
    im.save(output, "PNG")
    output.seek(0)
    return output


def draw_tard(image, quote):
    """ Draws the "it's retarded" image """
    # Open Files
    im = Image.open(BytesIO(image))
    base = Image.open("Images/retardedbase.png")
    msk = Image.open("Images/circlemask.png").convert('L')
    
    # Resize avatar, make circle, paste
    ops = ImageOps.fit(im, (250, 250))
    ops.putalpha(msk)
    smallmsk = msk.resize((35, 40))
    small = ops.resize((35, 40))
    largemsk = msk.resize((100, 100))
    large = ops.resize((100, 100)).rotate(-20)
    base.paste(small, box=(175, 160, 210, 200), mask=smallmsk)
    base.paste(large, box=(325, 90, 425, 190), mask=largemsk)
    
    # Drawing tex
    d = ImageDraw.Draw(base)
    
    # Get best size for text
    def get_first_size(quote_text):
        font_size = 72
        ttf = 'Whitney-Medium.ttf'
        ftsz = ImageFont.truetype(ttf, font_size)
        width = 300
        quote_text = textwrap.fill(quote_text, width=width)
        while font_size > 0:
            # Make lines thinner if too wide.
            while width > 1:
                if ftsz.getsize(quote_text)[0] < 237 and ftsz.getsize(quote)[1] < 89:
                    return width, ftsz
                width -= 1
                quote_text = textwrap.fill(quote, width=width)
                ftsz = ImageFont.truetype(ttf, font_size)
            font_size -= 1
            ftsz = ImageFont.truetype(ttf, font_size)
            width = 40

    wid, font = get_first_size(quote)
    quote = textwrap.fill(quote, width=wid)
    # Write lines.
    moveup = font.getsize(quote)[1]
    d.text((245, (80 - moveup)), quote, font=font, fill="#000000")
    
    # Prepare for sending
    output = BytesIO()
    base.save(output, "PNG")
    output.seek(0)
    df = discord.File(output, filename="retarded.png")
    return df


def ruin(image):
    """ Generates the Image """
    im = Image.open(BytesIO(image))
    base = Image.open("Images/localman.png")
    ops = ImageOps.fit(im, (256, 256))
    base.paste(ops, box=(175, 284, 431, 540))
    output = BytesIO()
    base.save(output, "PNG")
    output.seek(0)
    # output
    df = discord.File(output, filename="retarded.png")
    return df


async def get_faces(ctx, target):
    """ Retrieve face features from Project Oxford """
    if isinstance(target, discord.Member):
        target = str(target.avatar_url_as(format="png"))
    elif target is None:
        for i in ctx.message.attachments:
            if i.height is None:  # Not an image.
                continue
            target = i.url
            break
        else:
            await ctx.reply('🚫 To use this command either upload an image, tag a user, or specify a url.')
            return None, None, None
    elif "://" not in target:
        await ctx.reply(f"{target} doesn't look like a valid url.")
        return None, None, None
    
    # Prepare POST
    oxk = ctx.bot.credentials['Oxford']['OxfordKey']
    h = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": oxk}
    body = {"url": target}
    p = {"returnFaceId": "False", "returnFaceLandmarks": "True", "returnFaceAttributes": "headPose"}
    d = json.dumps(body)
    url = "https://westeurope.api.cognitive.microsoft.com/face/v1.0/detect"

    # Get Project Oxford reply
    async with ctx.bot.session.post(url, params=p, headers=h, data=d) as resp:
        if resp.status != 200:
            if resp.status == 400:
                await ctx.reply(await resp.json(), mention_author=False)
            else:
                await ctx.reply(
                    f"HTTP Error {resp.status} recieved accessing project oxford's facial recognition API.",
                    mention_author=False)
            return None, None, None
        response = await resp.json()
    
    # Get target image as file
    async with ctx.bot.session.get(target) as resp:
        if resp.status != 200:
            await ctx.reply(f"{resp.status} code accessing project oxford.", mention_author=False)
        image = await resp.content.read()
    return image, response, target


# TODO: XKCD Command. https://xkcd.com/json.html


class Images(commands.Cog):
    """ Image manipulation commands """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(usage="")
    @commands.cooldown(2, 90, BucketType.user)
    async def tinder(self, ctx):
        """ Try to Find your next date. """
        with ctx.typing():
            if ctx.author.id == 272722118192529409:
                return await ctx.reply("Nobody will ever swipe right on you, Kegs.", mention_author=True)
            match = random.choice([True, False, False])
            if not match:
                return await ctx.reply("Nobody swiped right on you.", mention_author=False)

            async with self.bot.session.get(str(ctx.author.avatar_url_as(format="png"))) as resp:
                av = await resp.content.read()
            match = random.choice(ctx.guild.members)
            # TODO: Get presence intents.
            # match = random.choice([i for i in ctx.guild.members if str(i.status) != "offline"])
            name = match.display_name

            async with self.bot.session.get(str(match.avatar_url_as(format="png"))) as resp:
                target = await resp.content.read()
                output = await self.bot.loop.run_in_executor(None, draw_tinder, target, av, name)
            if match == ctx.author:
                caption = f"{ctx.author.mention} matched with themself, How pathetic."
            elif match == ctx.me:
                caption = f"{ctx.author.mention} Fancy a shag?"
            else:
                caption = f"{ctx.author.mention} matched with {match.mention}"
            icon = "https://cdn0.iconfinder.com/data/icons/social-flat-rounded-rects/512/tinder-512.png"
            base_embed = discord.Embed()
            base_embed.description = caption
            base_embed.colour = 0xFD297B
            base_embed.set_author(name=ctx.invoked_with, icon_url=icon)
            base_embed.description = caption
            await embed_utils.embed_image(ctx, base_embed, output, filename="Tinder.png")

    @commands.command(aliases=["bob", "ross"], usage='<@user, link to image, or upload a file>')
    async def bobross(self, ctx, *, target: typing.Union[discord.Member, str] = None):
        """ Bob Rossify """
        with ctx.typing():
            image, response, target = await get_faces(ctx, target)
            
            if response is None:
                return await ctx.reply("🚫 No faces were detected in your image.", mention_author=False)
            
            image = await self.bot.loop.run_in_executor(None, draw_bob, image, response)
            icon = "https://cdn4.vectorstock.com/i/thumb-large/79/33/painting-icon-image-vector-14647933.jpg"
            
            base_embed = discord.Embed()
            base_embed.colour = 0xb4b2a7  # titanium h-white
            base_embed.set_author(name=ctx.invoked_with, icon_url=icon)
            base_embed.description = ctx.author.mention
            base_embed.add_field(name="Source", value=target)
            await embed_utils.embed_image(ctx, base_embed, image, filename="bobross.png")
            
            # Clean up
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

    @commands.is_nsfw()
    @commands.command(usage='<@user, link to image, or upload a file>')
    # TODO: Open mouth.
    async def knob(self, ctx, *, target: typing.Union[discord.Member, str] = None):
        """ Draw knobs in mouth on an image. Mention a user to use their avatar. Only works for human faces."""
        async with ctx.typing():
            image, response, target = await get_faces(ctx, target)
            
            if response is None:
                return await ctx.reply("🚫 No faces were detected in your image.", mention_author=False)
            
            image = await self.bot.loop.run_in_executor(None, draw_knob, image, response)
            icon = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/" \
                   "18_icon_TV_%28Hungary%29.svg/48px-18_icon_TV_%28Hungary%29.svg.png"
            
            base_embed = discord.Embed()
            base_embed.colour = 0xff66cc
            base_embed.set_author(name=ctx.invoked_with, icon_url=icon)
            base_embed.description = ctx.author.mention
            base_embed.add_field(name="Source", value=target)
            await embed_utils.embed_image(ctx, base_embed, image, filename="Knob.png")
           
            # Clean up
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

    @commands.command(usage='<@user, link to image, or upload a file>')
    async def eyes(self, ctx, *, target: typing.Union[discord.Member, str] = None):
        """ Draw Googly eyes on an image. Mention a user to use their avatar. Only works for human faces."""
        with ctx.typing():
            image, response, target = await get_faces(ctx, target)
            if response is None:
                return await ctx.reply("No faces were detected in your image.", mention_author=True)
            
            image = await self.bot.loop.run_in_executor(None, draw_eyes, image, response)
            icon = "https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/microsoft/209/eyes_1f440.png"
            
            base_embed = discord.Embed()
            base_embed.colour = 0xFFFFFF
            base_embed.set_author(name=ctx.invoked_with, icon_url=icon)
            base_embed.description = ctx.author.mention
            base_embed.add_field(name="Source", value=target)
            await embed_utils.embed_image(ctx, base_embed, image, filename="eyes.png")
            
            # Clean up
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    @commands.command(usage='<@user> <quote>')
    async def tard(self, ctx, target: discord.Member, *, quote):
        """ Generate an "oh no, it's retarded" image with a user's avatar and a quote """
        with ctx.typing():
            if target.id == 210582977493598208:
                target = ctx.author
                quote = "I think I'm smarter than Painezor"
            async with self.bot.session.get(str(target.avatar_url_as(format="png", size=1024))) as resp:
                if resp.status != 200:
                    return await ctx.reply(f"Error retrieving avatar for target {target} {resp.status}",
                                           mention_author=False)
                image = await resp.content.read()
            df = await self.bot.loop.run_in_executor(None, draw_tard, image, quote)
            # TODO: Embedify
            
            await ctx.reply(file=df, mention_author=False)
    
    @tard.error
    async def tard_error(self, ctx, exc):
        if isinstance(exc, commands.BadArgument):
            return await ctx.reply("🚫 Bad argument provided: Make sure you're pinging a user or using their ID",
                                   mention_author=True)

    @commands.command(aliases=["localman", "local", "ruin"], usage="[@member or leave blank to use yourself.]")
    async def ruins(self, ctx, *, user: discord.User = None):
        """ Local man ruins everything """
        with ctx.typing():
            if user is None:
                user = ctx.author
            av = str(user.avatar_url_as(format="png", size=256))
            async with self.bot.session.get(av) as resp:
                if resp.status != 200:
                    await ctx.reply(f"{resp.status} Error getting {user}'s avatar", mention_author=False)
                image = await resp.content.read()
            df = await self.bot.loop.run_in_executor(None, ruin, image)
            await ctx.reply(file=df, mention_author=False)

    @commands.command(hidden=True)
    async def butter(self, ctx):
        """ What is my purpose? """
        await ctx.reply(file=discord.File("Images/butter.png"), mention_author=False)
    
    @commands.command(hidden=True)
    async def fixed(self, ctx):
        """ Fixed! """
        await ctx.reply(file=discord.File("Images/fixed.png"), mention_author=False)
    
    @commands.command(hidden=True)
    async def ructions(self, ctx):
        """ WEW. RUCTIONS. """
        await ctx.reply(file=discord.File("Images/ructions.png"), mention_author=False)
    
    @commands.command(hidden=True)
    async def helmet(self, ctx):
        """ Helmet"""
        await ctx.reply(file=discord.File("Images/helmet.jpg"), mention_author=False)
    
    @commands.command(hidden=True, aliases=["f"])
    async def pressf(self, ctx):
        """ Press F to pay respects """
        await ctx.reply("https://i.imgur.com/zrNE05c.gif", mention_author=False)
    
    @commands.command(hidden=True)
    async def goala(self, ctx):
        """ Party on Garth """
        await ctx.reply(file=discord.File('Images/goala.gif'), mention_author=False)
        
    @commands.command(usage="<an emoji>")
    async def emoji(self, ctx, emoji: typing.Union[discord.Emoji, discord.PartialEmoji]):
        """ View a bigger version of an Emoji """
        e = discord.Embed()
        e.title = emoji.name
        if emoji.animated:
            e.description = "This is an animated emoji."
        url = str(emoji.url)
        
        try:
            e.add_field(name="Emoji Source", value=f"{emoji.guild} (ID: {emoji.guild.id})")
        except AttributeError:  # Partial Emoji doesn't have guild.
            pass

        e.colour = await embed_utils.get_colour(url)
        
        e.set_image(url=url)
        e.set_footer(text=url)
        await ctx.reply(embed=e, mention_author=False)

def setup(bot):
    bot.add_cog(Images(bot))
