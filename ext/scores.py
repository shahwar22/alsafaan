# Discord.py
from io import BytesIO

import discord
from discord.ext import commands

# Web Scraping
import os
from lxml import html
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

# Imaging
from PIL import Image

# Data manipulation
import datetime
import asyncio

# Config
import json

# TODO: Lookup Scores per league.
# TODO: Build reactor menu.
# TODO: Code Goals
# TODO: Code Stats

default_leagues = [
    "WORLD: Friendly international",
    "WORLD: Friendly International",
    "EUROPE: Champions League",
    "EUROPE: Euro",
    "ENGLAND: Premier League",
    "ENGLAND: Championship",
    "ENGLAND: League One",
    "ENGLAND: FA Cup",
    "ENGLAND: EFL Cup",
    "FRANCE: Ligue 1",
    "FRANCE: Coupe de France",
    "GERMANY: Bundesliga",
    "ITALY: Serie A",
    "NETHERLANDS: Eredivisie",
    "SCOTLAND: Premiership",
    "USA: MLS", "SPAIN: LaLiga"
]


class ScoresChannel(commands.Cog):
    """ Live Scores channel module """

    def __init__(self, bot):
        self.bot = bot
        self.scores_on = True
        self.score_channel_cache = {}
        self.score_channel_league_cache = {}
        self.bot.live_games = {}
        self.msgdict = {}
        self.bot.loop.create_task(self.update_cache())

        self.bot.scores = self.bot.loop.create_task(self.score_loop())

        # Loop frequency // Debug 15, normal 60.
        self.interval_timer = 60

    async def update_cache(self):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            channels = await connection.fetch("""SELECT * FROM scores_channels""")
            whitelists = await connection.fetch("""SELECT * FROM scores_channels_leagues""")
        await self.bot.db.release(connection)

        channel_cache = {}
        whitelist_cache = {}
        for r in channels:
            try:
                channel_cache[r["guild_id"]].append(r["channel_id"])
            except KeyError:
                channel_cache.update({r["guild_id"]: [r["channel_id"]]})

        for r in whitelists:
            try:
                whitelist_cache[r["channel_id"]].append(r["league"])
            except KeyError:
                whitelist_cache[r["channel_id"]] = [r["league"]]

        self.score_channel_cache = channel_cache
        self.score_channel_league_cache = whitelist_cache

    def cog_unload(self):
        self.scores_on = False
        self.bot.scores.cancel()

    # Core Loop
    async def score_loop(self):
        """ Score Checker Loop """
        await self.bot.wait_until_ready()
        while self.scores_on:
            try:
                games = await self.bot.loop.run_in_executor(None, self.fetch_data)
            except Exception as e:
                print("Exception in score_loop.")
                print(type(e).__name__)
                print(e.args)
                await asyncio.sleep(5)
                continue
            await self.write_raw(games)
            # Iterate: Check vs each server's individual config settings
            await self.localise_data()

            # Send message to server.
            if self.scores_on:
                try:
                    await self.spool_messages()
                except discord.ConnectionClosed:
                    continue
            else:
                return

            # Loop.
            await asyncio.sleep(self.interval_timer)

    # Spawn Chrome
    def spawn_chrome(self):
        caps = DesiredCapabilities().CHROME
        caps["pageLoadStrategy"] = "normal"  # complete
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920x1200")
        chrome_options.add_argument('--no-proxy-server')
        chrome_options.add_argument("--proxy-server='direct://'")
        chrome_options.add_argument("--proxy-bypass-list=*")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        driver_path = os.getcwd() + "\\chromedriver.exe"
        prefs = {'profile.default_content_setting_values': {'images': 2, 'javascript': 2}}
        chrome_options.add_experimental_option('prefs', prefs)
        driver = webdriver.Chrome(desired_capabilities=caps, chrome_options=chrome_options, executable_path=driver_path)
        driver.set_page_load_timeout(20)
        return driver

    def fetch_data(self):
        driver = self.spawn_chrome()
        driver.get("http://www.flashscore.com/")
        WebDriverWait(driver, 2)

        fixture_list = driver.find_element_by_class_name('leagues--live')
        fixture_list = fixture_list.get_attribute('innerHTML')
        fixture_list = html.fromstring(fixture_list)

        fixture_list = fixture_list.xpath('./div')

        driver.quit()
        games = {}
        lg = "Unknown League"
        for i in fixture_list:
            # Header rows do not have IDs
            if not i.xpath('.//@id'):
                lg = ": ".join(i.xpath('.//span//text()'))
                games[lg] = {}
            else:
                game_id = ''.join(i.xpath('.//@id'))
                games[lg][game_id] = {}

                # Time
                time = i.xpath('.//div[contains(@class,"event__stage--block")]//text()')
                if not time:
                    time = i.xpath('.//div[contains(@class,"event__time")]//text()')

                time = "".join(time).replace('FRO', "").strip("\xa0").strip()
                if "Finished" in time:
                    time = "FT"
                elif "After ET" in time:
                    time = "AET"
                elif "Half Time" in time:
                    time = "HT"
                elif "Postponed" in time:
                    time = "PP"
                elif ":" not in time:
                    time += "'"
                games[lg][game_id]["time"] = time
                games[lg][game_id]["home_team"] = "".join(i.xpath('.//div[contains(@class,"home")]//text()')).strip()
                games[lg][game_id]["away_team"] = "".join(i.xpath('.//div[contains(@class,"away")]//text()')).strip()
                # games[lg][game_id]["aggregate"] = "".join(i.xpath('.//div[@class="event__part"]//text()')).strip()
                score = "".join(i.xpath('.//div[contains(@class,"event__scores")]//text()')).strip()
                score = "vs" if not score else score
                games[lg][game_id]["score"] = score

        return games

    async def write_raw(self, games):
        for league, data in games.items():
            # i is a game_id
            raw = f"**{league}**\n"
            for k, v in data.items():
                time = f"{data[k]['time']}"

                time = "✅ FT" if time == "FT" else time
                time = "✅ AET" if time == "AET" else time
                time = "⏸️ HT" if time == "HT" else time
                time = "🚫 PP" if time == "PP" else time
                time = f"🔜 {time}" if ":" in time else time
                time = f"⚽ {time}" if "'" in time else time

                home = data[k]["home_team"]
                away = data[k]["away_team"]
                score = data[k]["score"]

                raw += f"`{time}` {home} {score} {away}\n"

            games[league]["raw"] = raw
        self.bot.live_games = games

    async def localise_data(self):
        for g, cl in self.score_channel_cache.items():
            for c in cl:
                try:
                    leagues = self.score_channel_league_cache[c]
                except KeyError:
                    leagues = default_leagues
                
                if c not in self.msgdict:
                    self.msgdict[c] = {}
                    self.msgdict[c]["msg_list"] = []

                self.msgdict[c]["raw_data"] = []

                today = datetime.datetime.now().strftime(
                    "Live Scores for **%a %d %b %Y** (last updated at **%H:%M:%S**)\n\n")
                rawtext = today
                for j in leagues:
                    if j not in self.bot.live_games:
                        continue
                    if len(rawtext) + len(self.bot.live_games[j]["raw"]) < 1999:
                        rawtext += self.bot.live_games[j]["raw"] + "\n"
                    else:
                        self.msgdict[c]["raw_data"] += [rawtext]
                        rawtext = self.bot.live_games[j]["raw"] + "\n"

                    if rawtext == today:
                        rawtext += "Either there's no games today, something broke, or you have your list of leagues " \
                                   "set very small\n\n You can add more leagues with `ls add league_name`."
                self.msgdict[c]["raw_data"] += [rawtext]

    async def spool_messages(self):
        if not self.scores_on:
            return
        for c, v in self.msgdict.items():
            # Create messages if none exist.
            # Or if a different number of messages is required.
            if not self.msgdict[c]["msg_list"] or len(self.msgdict[c]["msg_list"]) != len(self.msgdict[c]["raw_data"]):
                ch = self.bot.get_channel(c)
                try:
                    await ch.purge()
                except discord.Forbidden:
                    await ch.send(
                        "Unable to clean previous messages, please make sure I have manage_messages permissions.")
                except AttributeError:
                    print(f'Live Scores Loop: Invalid channel: {c}')
                    continue
                for d in self.msgdict[c]["raw_data"]:
                    # Append message ID to our list
                    try:
                        m = await ch.send(d)
                        self.msgdict[c]["msg_list"].append(m)
                    except discord.Forbidden:
                        pass
            else:
                # Edit message pairs if pre-existing.
                tuples = list(zip(self.msgdict[c]["msg_list"], self.msgdict[c]["raw_data"]))
                for x, y in tuples:
                    try:
                        await x.edit(content=y)
                    except discord.NotFound as e:
                        print("-- error editing scores channel --")
                        print(x)
                        print(e)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def ls(self, ctx, channel: discord.TextChannel = None):
        """ View the status of your live scores channels. """
        e = discord.Embed(color=0x0000ff)
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = "Live-scores channel config"
        e.description = ""

        try:
            score_channels = self.score_channel_cache[ctx.guild.id]
        except KeyError:
            return await ctx.send(f"{ctx.guild.name} has no live-scores channel set.")

        if len(score_channels) != 1:
            if not channel:
                channels = ", ".join([self.bot.get_channel(i).mention for i in score_channels])
                return await ctx.send(
                    f"{ctx.guild.name} currently has {len(score_channels)} score channels set: {channels}\n"
                    f"Use {ctx.prefix}ls #channel to get the status of a specific one.")
            elif channel not in score_channels:
                await ctx.send(f'{channel.mention} is not set as one of your score channels.')
        else:
            channel = score_channels[0]

        e.add_field(name="Channel", value=self.bot.get_channel(channel).mention)
        await ctx.send(embed=e)

    @ls.command(usage="ls create")
    @commands.has_permissions(manage_channels=True)
    async def create(self, ctx):
        """ Create a live-scores channel for your server. """
        try:
            ow = {ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True,
                                                      embed_links=True, read_message_history=True),
                  ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                      read_message_history=True)
                  }
            reason = f'{ctx.author} (ID: {ctx.author.id}) creating a live-scores channel.'
            ch = await ctx.guild.create_text_channel(name="live-scores", overwrites=ow, reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                "Unable to create live-scores channel. Please make sure I have the manage_channels permission.")
        except discord.HTTPException:
            return await ctx.send(
                "An unknown error occured trying to create the live-scores channel, please try again later.")

        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" 
                INSERT INTO scores_channels (guild_id,channel_id) VALUES ($1,$2)
                """, ctx.guild.id, ch.id)

        await ctx.send(f"The {ch} channel was created succesfully.")
        await self.bot.db.release(connection)
        await self.update_cache()

    # Delete from Db on delete..
    @commands.Cog.listener()
    async def on_channel_delete(self, channel):
        connection = await self.bot.db.acquire()
        await connection.execute(""" 
            DELETE FROM scores_channels WHERE channel_id = $1
            """, channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()

    async def _pick_channels(self, ctx, channels):
        # Assure guild has transfer channel.
        try:
            guild_cache = self.score_channel_cache[ctx.guild.id]
        except KeyError:
            await ctx.send(f'{ctx.guild.name} does not have any live scores channels set.')
            channels = []
        else:
            # Channel picker for invoker.
            def check(message):
                return ctx.author.id == message.author.id and message.channel_mentions

            # If no Query provided we check current whitelists.
            if not channels:
                channels = [self.bot.get_channel(i) for i in list(guild_cache)]
            if ctx.channel.id in guild_cache:
                channels = [ctx.channel]
            elif len(channels) != 1:
                async with ctx.typing():
                    mention_list = " ".join([i.mention for i in channels])
                    m = await ctx.send(
                        f"{ctx.guild.name} has multiple live-score channels set: ({mention_list}), please specify "
                        f"which one(s) to check or modify.")
                    try:
                        channels = await self.bot.wait_for("message", check=check, timeout=30)
                        channels = channels.channel_mentions
                        await m.delete()
                    except asyncio.TimeoutError:
                        await m.edit(
                            content="Timed out waiting for you to reply with a channel list. No channels were "
                                    "modified.")
                        channels = []
        return channels

    @ls.command(usage="ls add <(Optional: #channel #channel2)> <search query>")
    @commands.has_permissions(manage_channels=True)
    async def add(self, ctx, channels: commands.Greedy[discord.TextChannel], *, qry: commands.clean_content = None):
        """ Add a league to your live-scores channel """
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return  # rip

        if qry is None:
            return await ctx.send("Specify a competition name to search for.")

        m = await ctx.send(f"Searching for {qry}...")
        res = await self._search(ctx, m, qry)

        if not res:
            return await ctx.send("Didn't find any leagues. Your channels were not modified.")

        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in self.score_channel_cache[ctx.guild.id]:
                    replies.append(f'🚫 {c.mention} is not set as a scores channel.')
                    continue
                try:
                    leagues = self.score_channel_league_cache[c.id]
                except KeyError:
                    leagues = default_leagues.copy()

                if res in leagues:
                    replies.append(f"⚠️**{res}** was already in {c.mention}'s tracked leagues.")
                    continue
                else:
                    leagues.append(res)

                async with connection.transaction():
                    for lg in leagues:
                        await connection.execute(""" 
                            INSERT INTO scores_channels_leagues (league,channel_id) 
                            VALUES ($1,$2)
                            ON CONFLICT DO NOTHING
                            """, lg, c.id)
                leagues = ', '.join(leagues)
                replies.append(
                    f"✅ **{res}** added to the tracked leagues for {c.mention},"
                    f" the new tracked leagues list is: {leagues}")
        await self.bot.db.release(connection)
        await self.update_cache()

        await ctx.send("\n".join(replies))

    @ls.command(aliases=["del", "delete"], usage="ls remove <(Optional: #channel #channel2)> <Country: League Name>")
    @commands.has_permissions(manage_channels=True)
    async def remove(self, ctx, channels: commands.Greedy[discord.TextChannel], *, target: commands.clean_content):
        """ Remove a competition from your live-scores channels """
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return  # rip

        replies = []
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            for c in channels:
                if c.id not in self.score_channel_cache[ctx.guild.id]:
                    replies.append(f'{c.mention} is not set as a scores channel.')
                    continue
                try:
                    leagues = self.score_channel_league_cache[c.id]
                    if target not in leagues:
                        replies.append(f"🚫 **{target}** was not in {c.mention}'s tracked leagues.")
                    else:
                        await connection.execute(""" 
                            DELETE FROM scores_channels_leagues WHERE (league,channel_id) = ($1,$2)
                        """, target, c.id)
                except KeyError:
                    leagues = default_leagues
                    leagues.remove(target)
                    for lg in leagues:
                        await connection.execute(""" 
                            INSERT INTO scores_channels_leagues (league,channel_id) VALUES ($1,$2)
                            ON CONFLICT DO NOTHING
                        """, lg, c.id)

                replies.append(f"✅ **{target}** was deleted from the tracked leagues for {c.mention}.")
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send('\n'.join(replies))

    @ls.command(usage="ls remove <(Optional: #channel #channel2)>")
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Reset live-scores channels to the list of default competitions """
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return  # rip

        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in self.score_channel_cache:
                    replies.append(f"🚫 {c.mention} was not set as a scores channel.")
                    continue
                if c.id not in self.score_channel_league_cache:
                    replies.append(f"⚠️ {c.mention} is already using the default leagues.")
                    continue
                async with connection.transaction():
                    await connection.execute(""" 
                        DELETE FROM scores_channels_leagues WHERE channel_id = $1
                    """, c.id)
                replies.append(f"✅ {c.mention} had it's tracked leagues reset to the default.")

        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send("\n".join(replies))

    async def _search(self, ctx, m, qry):
        # aiohttp lookup for json.
        qry = qry.replace("'", "")

        qryurl = f"https://s.flashscore.com/search/?q={qry}&l=1&s=1&f=1%3B1&pid=2&sid=1"
        async with self.bot.session.get(qryurl) as resp:
            res = await resp.text()
            res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
            res = json.loads(res)

        resdict = {}
        key = 0
        # Remove irrel.
        for i in res["results"]:
            # Format for LEAGUE
            if i["participant_type_id"] == 0:
                # Sample League URL: https://www.flashscore.com/soccer/england/premier-league/
                resdict[str(key)] = {"Match": i['title']}
                key += 1

        if not resdict:
            return await m.edit(content=f"No results for query: {qry}")

        if len(resdict) == 1:
            try:
                await m.delete()
            except discord.Forbidden:
                pass
            return resdict["0"]["Match"]

        id_strings = ""
        for i in resdict:
            id_strings += f"{i}: {resdict[i]['Match']}\n"

        try:
            await m.edit(content=f"Please type matching id: ```{id_strings}```")
        except discord.HTTPException:
            # TODO: Paginate.
            return await m.edit(content=f"Too many matches to display, please be more specific.")

        def check(message):
            if message.author.id == ctx.author.id and message.content in resdict:
                return True

        try:
            match = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await m.delete()

        mcontent = match.content
        try:
            await m.delete()
            await match.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        return resdict[mcontent]["Match"]

    async def pick_game(self, ctx, qry):
        matches = []
        key = 0
        for league in self.bot.live_games:
            for game_id in self.bot.live_games[league]:
                # Ignore our output strings.
                if game_id == "raw":
                    continue

                home = self.bot.live_games[league][game_id]["home_team"]
                away = self.bot.live_games[league][game_id]["away_team"]

                if qry in home.lower() or qry in away.lower():
                    game = f"{home} vs {away} ({league})"
                    matches.append((key, game, league, game_id))
                    key += 1

        if not matches:
            return None, None

        if len(matches) == 1:
            # return league and game of only result.
            return matches[0][2], matches[0][3]

        selector = "Please Type Matching ID```"
        for i in matches:
            selector += f"{i[0]}: {i[1]}\n"
        selector += "```"

        try:
            m = await ctx.send(selector, delete_after=30)
        except discord.HTTPException:
            # TODO: Paginate.
            return await ctx.send(content=f"Too many matches to display, please be more specific.")

        def check(message):
            if message.author.id == ctx.author.id and message.content.isdigit():
                if int(message.content) < len(matches):
                    return True

        try:
            match = await self.bot.wait_for("message", check=check, timeout=30)
            match = int(match.content)
        except asyncio.TimeoutError:
            return None, None
        else:
            try:
                await m.delete()
            except discord.NotFound:
                pass
            return matches[match][2], matches[match][3]

    def fetch_match_data(self, league, game):
        url = f"https://www.flashscore.com/match/{game.split('_')[-1]}/#match-statistics;0"
        driver = self.spawn_chrome()
        wait = 0
        driver.get(url)
        WebDriverWait(driver, wait)
        while driver.current_url != url:
            driver.get(url)
            WebDriverWait(driver, wait)
            wait += 1
            if wait > 5:
                return None

        # Statistics
        s, h, a = [], [], []

        # Attempt to grab Stats.
        tree = html.fromstring(driver.page_source)
        statlist = tree.xpath(".//div[@class='statContent']")

        try:
            for i in statlist[0]:
                new_s = "\n".join(i.xpath(".//div[contains(@class,'titleValue')]/text()")).strip()
                if new_s in s:
                    continue
                s.append(new_s)
                h.append("\n".join(i.xpath(".//div[contains(@class,'homeValue')]/text()")).strip())
                a.append("\n".join(i.xpath(".//div[contains(@class,'awayValue')]/text()")).strip())
        except IndexError:
            pass

        # Attempt to grab Formation.
        formation = ""
        try:
            z = driver.find_element_by_link_text('Lineups')
            z.click()
            WebDriverWait(driver, 3)

            x = driver.find_element_by_class_name('soccer-formation')
            im = Image.open(BytesIO(x.screenshot_as_png))
            im.save("formations.png", "PNG")

            # Send to Imgur
            res = self.bot.imgur.upload_from_path("formations.png", anon=True)
            formation = res["link"]

        except NoSuchElementException:
            pass
        except AttributeError as e:
            print(e)

        driver.quit()

        e = discord.Embed()
        home = self.bot.live_games[league][game]["home_team"]
        away = self.bot.live_games[league][game]["away_team"]
        score = self.bot.live_games[league][game]["score"]
        time = self.bot.live_games[league][game]["time"]
        e.title = f"{home} {score} {away}"

        if formation:
            e.set_image(url=formation)

        if not ":" in time and not "PP" in time:
            e.title += f" ({time})"
            e.colour = 0x448fea
        else:
            e.colour = 0xA4DD74
        e.url = url

        if a and h and s:
            e.add_field(name="Home", value="\n".join(h), inline=True)
            e.add_field(name="Stat", value="\n".join(s), inline=True)
            e.add_field(name="Away", value="\n".join(a), inline=True)
        elif "PP" in time:
            e.colour = 0xe85342
            e.description = "This match has been postponed."
        elif ":" not in time:
            e.colour = 0xe85342
            e.description = "Live data not available for this match."

        if ":" in time:
            h, m = time.split(':')
            now = datetime.datetime.now()
            when = datetime.datetime.now().replace(hour=int(h), minute=int(m))

            x = when - now

            e.set_footer(text=f"Kickoff in {x}")
            e.timestamp = when

        return e

    @commands.command()
    async def stats(self, ctx, *, qry: commands.clean_content()):
        """ Look up the stats for one of today's games """
        with ctx.typing():
            if not qry:
                return await ctx.send("Please specify a search query.")

            league, game = await self.pick_game(ctx, qry.lower())
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")

            e = await self.bot.loop.run_in_executor(None, self.fetch_match_data, league, game)

            if e is None:
                return await ctx.send("Timed out getting data.")
            await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(ScoresChannel(bot))
