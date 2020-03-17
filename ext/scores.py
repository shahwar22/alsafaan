import asyncio
from collections import defaultdict
from copy import deepcopy

import discord
from discord.ext import commands, tasks

# Web Scraping
from lxml import html

# Data manipulation
import datetime

# Utils
from importlib import reload
from ext.utils import football, embed_utils
from ext.utils.embed_utils import paginate

# Constants.
NO_GAMES_FOUND = "No games found for your tracked leagues today!" \
                 "\n\nYou can add more leagues with `.tb ls add league_name`" \
                 "\nYou can reset your leagues with `.tb ls reset" \
                 "  \nTo find out which leagues currently have games, use `.tb scores`"
NO_CLEAR_CHANNEL_PERM = "Unable to clean previous messages, please make sure I have manage_messages permissions."
NO_MANAGE_CHANNELS = "Unable to create live-scores channel. Please make sure I have the manage_channels permission."

default_leagues = [
    "WORLD: Friendly international",
    "EUROPE: Champions League",
    "EUROPE: Euro",
    "EUROPE: Europa League",
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
    "SPAIN: Copa del Rey",
    "SPAIN: LaLiga",
    "USA: MLS"
]

# TODO: https://www.scorebat.com/video-api/
# TODO: re-code vidi-printer
# TODO: Allow re-ordering of leagues, set an "index" value in db and do a .sort?


async def _search(ctx, qry) -> str or None:
    search_results = await football.get_fs_results(qry)
    item_list = [i.title for i in search_results if i.participant_type_id == 0]  # Check for specifics.
    index = await embed_utils.page_selector(ctx, item_list)

    if index is None:
        return  # Timeout or abort.
    return search_results[index]


class Scores(commands.Cog):
    """ Live Scores channel module """
    
    def __init__(self, bot):
        self.bot = bot
        
        # Reload utils
        for i in [football, embed_utils]:
            reload(i)
        
        # Data
        self.bot.games = {}
        self.msg_dict = {}
        self.cache = defaultdict(set)
        self.bot.loop.create_task(self.update_cache())
        
        # Core loop.
        self.bot.scores = self.score_loop.start()
   
    def cog_unload(self):
        self.score_loop.cancel()
    
    async def update_cache(self):
        # Grab most recent data.
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            channels = await connection.fetch("""
            SELECT guild_id, scores_channels.channel_id, league
            FROM scores_channels
            LEFT OUTER JOIN scores_leagues
            ON scores_channels.channel_id = scores_leagues.channel_id""")
        await self.bot.db.release(connection)
        
        # Clear out our cache.
        self.cache.clear()
        
        # Repopulate.
        for r in channels:
            if self.bot.get_channel(r['channel_id']) is None:
                continue
            self.cache[(r["guild_id"], r["channel_id"])].update(r["league"])
    
    # Core Loop
    @tasks.loop(minutes=1)
    async def score_loop(self):
        """ Score Checker Loop """
        games = await self.fetch_games()
        # If we have an item with new data, force a full cache clear. This is expected behaviour at midnight.
        if not {i.url for i in self.bot.games} & {x.url for x in games}:
            self.bot.games = []
            
        # If we only have a partial match returned, for whatever reason
        self.bot.games = [i for i in self.bot.games if i.url not in [x.url for x in games]] + [x for x in games]
        
        # Key games by league for intersections.
        game_dict = defaultdict(set)
        for i in self.bot.games:
            game_dict[i.full_league].update(i.live_score_text)
        
        # Iterate: Check vs each server's individual config settings
        for (guild_id, channel_id), whitelist in self.cache.items():
            
            # Does league exist in both whitelist and found games.
            channel_leagues_required = game_dict.keys() & whitelist
            
            chunks = []
            this_chunk = datetime.datetime.now().strftime("Live Scores for **%a %d %b %Y** (Local Time **%H:%M**)\n")
            if channel_leagues_required:
                # Build messages.
                for league in channel_leagues_required:
                    # Chunk-ify to max message length
                    hdr = f"\n**{league}**"
                    if len(this_chunk + hdr) > 1999:
                        chunks += [this_chunk]
                        this_chunk = ""
                    this_chunk += hdr + "\n"
                    
                    for game in game_dict[league]:
                        if len(this_chunk + game) > 1999:
                            chunks += [this_chunk]
                            this_chunk = ""
                        this_chunk += game + "\n"
            else:
                this_chunk += NO_GAMES_FOUND
                
            # Dump final_chunk.
            chunks += [this_chunk]
            
            # Check if we have some previous messages for this channel
            if channel_id not in self.msg_dict:
                self.msg_dict[channel_id] = {}

            # Expected behaviour: Edit pre-existing message with new data.
            if len(self.msg_dict[channel_id]) == len(chunks):
                for message, chunk in list(zip(self.msg_dict[channel_id], chunks)):
                    # Save API calls by only editing when a change occurs.
                    if message.content != chunk:
                        await message.edit(content=chunk)
            
            # Otherwise we build a new message list.
            else:
                channel = self.bot.get_channel(channel_id)
                try:
                    self.msg_dict[channel_id] = []
                    await channel.purge()
                except discord.Forbidden:
                    await channel.send(NO_CLEAR_CHANNEL_PERM)
                except AttributeError:  # Channel not found.
                    continue
                    
                for x in chunks:
                    # Append message ID to our list
                    try:
                        message = await channel.send(x)
                    except (discord.Forbidden, discord.NotFound):
                        continue  # These are user-problems, not mine.
                    except Exception as e:
                        # These however need to be logged.
                        print("-- error sending message to scores channel --")
                        print(channel.id)
                        print(e)
                    else:
                        self.msg_dict[channel_id].append(message)

    @score_loop.before_loop
    async def before_score_loop(self):
        await self.bot.wait_until_ready()
        await self.update_cache()

    async def fetch_games(self):
        async with self.bot.session.get("http://www.flashscore.mobi/") as resp:
            src = await resp.text()
            xml = bytes(bytearray(src, encoding='utf-8'))
        tree = html.fromstring(xml)
        elements = tree.xpath('.//div[@id="score-data"]/* | .//div[@id="score-data"]/text()')
    
        country = None
        league = None
        home_attrs = None
        away_attrs = None
        home_goals = None
        away_goals = None
        url = None
        time = None
        state = None
        capture_group = []
        games = []
        for i in elements:
            try:
                tag = i.tag
            except AttributeError:
                # Not an element. / lxml.etree._ElementUnicodeResult
                capture_group.append(i)
                continue
        
            if tag == "br":
                # End of match row.
                try:
                    home, away = "".join(capture_group).split('-', 1)  # Olympia HK can suck my fucking cock
                except ValueError:
                    print("Value error", capture_group)
                    capture_group = []
                    continue
                capture_group = []
            
                games.append(football.Fixture(time=time, home=home, away=away, url=url, country=country,
                                              league=league, score_home=home_goals, score_away=away_goals,
                                              home_attrs=home_attrs, away_attrs=away_attrs, state=state))
            
                # Clear attributes
                home_attrs = None
                away_attrs = None
                state = ""
        
            elif tag == "h4":
                country, league = i.text.split(': ')
                league = league.split(' - ')[0]
            elif tag == "span":
                # Sub-span containing postponed data.
                time = i.find('span').text if i.find('span') is not None else i.text
                try:
                    state = i.find('span').attrib['class']
                except AttributeError:
                    pass

            elif tag == "a":
                url = i.attrib['href']
                url = "http://www.flashscore.com" + url
                home_goals, away_goals = i.text.split(':')
                if not state:
                    state = i.attrib['class']
                if away_goals.endswith('aet'):
                    away_goals = away_goals.strip('aet')
                    time = "AET"
                elif away_goals.endswith('pen'):
                    away_goals = away_goals.strip('pen')
                    time = "After Pens"
                    
            elif tag == "img":
                if "rcard" in i.attrib['class']:
                    cards = "`" + "🟥" * int("".join([i for i in i.attrib['class'] if i.isdigit()])) + "`"
                    if "-" not in capture_group:
                        home_attrs = cards
                    else:
                        away_attrs = cards
                else:
                    print("Live scores loop / Unhandled class for ", i.home, "vs", i.away, i.attrib['class'])
            else:
                print(f"Live scores loop / Unhandled tag: {i.tag}")
        return games
    
    # Delete from Db on delete..
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if (channel.guild.id, channel.id) in self.cache:
            connection = await self.bot.db.acquire()
            await connection.execute(""" DELETE FROM scores_channels WHERE channel_id = $1 """, channel.id)
            await self.bot.db.release(connection)
            await self.update_cache()
            self.msg_dict.pop(channel.id)
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in [i[0] for i in self.cache]:
            await self.update_cache()
    
    async def _pick_channels(self, ctx, channels):
        # Assure guild has score channel.
        if ctx.guild.id not in [i[0] for i in self.cache]:
            await ctx.send(f'{ctx.guild.name} does not have any live scores channels set.')
            channels = []
        else:
            # Channel picker for invoker.
            def check(message):
                return ctx.author.id == message.author.id and message.channel_mentions
            
            # If no Query provided we check current whitelists.
            guild_channels = [self.bot.get_channel(i[1]) for i in self.cache if i[0] == ctx.guild.id]
            if not channels:
                channels = guild_channels
            if ctx.channel in guild_channels:
                return [ctx.channel]
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

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def ls(self, ctx):
        """ View the status of your live scores channels. """
        e = discord.Embed(color=0x2ecc71)
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = f"{ctx.guild.name} Live Scores channels"
        
        score_channels = [self.bot.get_channel(i[1]) for i in self.cache if ctx.guild.id in i]
        if not score_channels:
            return await ctx.send(f"{ctx.guild.name} has no live-scores channel set.")
    
        embeds = []
        for i in score_channels:
            e.description = f'{i.mention}'
            # Warn if they fuck up permissions.
            if not ctx.me.permissions_in(i).send_messages:
                e.description += "```css\n[WARNING]: I do not have send_messages permissions in that channel!"
            leagues = self.cache[(ctx.guild.id, i.id)]
            if leagues != [None]:
                
                leagues = "```yaml\n" + "\n".join(sorted(leagues)) + "```"
                e.add_field(name="This channel's Tracked Leagues", value=leagues)
            embeds.append(deepcopy(e))
            e.clear_fields()
        await paginate(ctx, embeds)

    @ls.command(usage="ls create (Optional: Channel-name)")
    @commands.has_permissions(manage_channels=True)
    async def create(self, ctx, *, name=None):
        """ Create a live-scores channel for your server. """
        try:
            ow = {ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                      manage_messages=True, read_message_history=True),
                  ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                      read_message_history=True)}
            reason = f'{ctx.author} (ID: {ctx.author.id}) created a Toonbot live-scores channel.'
            if name is None:
                name = "live-scores"
            ch = await ctx.guild.create_text_channel(name=name, overwrites=ow, reason=reason)
        except discord.Forbidden:
            return await ctx.send(NO_MANAGE_CHANNELS)
        except discord.HTTPException:
            return await ctx.send(
                "An unknown error occurred trying to create the live-scores channel, please try again later.")
    
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(
                """ INSERT INTO scores_channels (guild_id, channel_id) VALUES ($1, $2) """, ctx.guild.id, ch.id)
            for i in default_leagues:
                await connection.execute(
                    """ INSERT INTO scores_leagues (channel_id, league) VALUES ($1, $2) """, ch.id, i)
    
        await ctx.send(f"The {ch.mention} channel was created succesfully.")
        await self.bot.db.release(connection)
        await self.update_cache()

    @commands.has_permissions(manage_channels=True)
    @ls.command(usage="ls add <(Optional: #channel #channel2)> <search query>")
    async def add(self, ctx, channels: commands.Greedy[discord.TextChannel], *, qry: commands.clean_content = None):
        """ Add a league to your live-scores channel """
        channels = await self._pick_channels(ctx, channels)
        
        if not channels:
            return  # rip
        
        if qry is None:
            return await ctx.send("Specify a competition name to search for.")
        
        await ctx.send(f"Searching for {qry}...", delete_after=5)
        res = await _search(ctx, qry)
        
        if not res:
            return await ctx.send("Didn't find any leagues. Your channels were not modified.")
        
        connection = await self.bot.db.acquire()
        replies = []
        res = f"{res.title}"
        async with connection.transaction():
            for c in channels:
                if (ctx.guild.id, c.id) not in self.cache:
                    replies.append(f'🚫 {c.mention} is not set as a scores channel.')
                    continue
                leagues = self.cache[(ctx.guild.id, c.id)]
                leagues.update(res)
                for league in leagues:
                    await connection.execute("""
                        INSERT INTO scores_leagues (league,channel_id)
                        VALUES ($1,$2)
                        ON CONFLICT DO NOTHING
                        """, league, c.id)
                leagues = ', '.join(leagues)
                replies.append(f"✅ **{res}** added to the tracked leagues for {c.mention},"
                               f" the new tracked leagues list is: ```yaml\n{leagues}```")
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send("\n".join(replies))
    
    @ls.group(name="remove", aliases=["del", "delete"],
              usage="ls remove <Optional: #channel> <Country: League Name>",
              invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def _remove(self, ctx, channel: discord.TextChannel = None, *, target: commands.clean_content):
        """ Remove a competition from a live-scores channel
        
        Either perform ls remove <league name> in the channel you wish to delete it from, or use
        ls remove #channel <league name> to delete it from another channel."""
        # Verify we have a valid livescores channel target.
        channel = ctx.channel if channel is None else channel
        if channel.id not in {i[1] for i in self.cache}:
            return await ctx.send(f'{channel.mention} is not set as a scores channel.')

        # Verify which league the user wishes to remove.
        target = target.strip("'\",")  # Remove quotes, idiot proofing.
        leagues = self.cache[(ctx.guild.id, channel.id)]
        matches = [i for i in leagues if target.lower() in i.lower()]
        index = await embed_utils.page_selector(ctx, matches)
        if index is None:
            return  # rip.
        target = matches[index]
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" DELETE FROM scores_leagues WHERE (league,channel_id) = ($1,$2)""",
                                     target, channel.id)
        leagues.remove(target)
        leagues = ", ".join(leagues)
        await ctx.send(f"✅ **{target}** was deleted from the tracked leagues for {channel.mention},"
                       f" the new tracked leagues list is: ```yaml\n{leagues}```\n")
        await self.bot.db.release(connection)
        await self.update_cache()
    
    @_remove.command()
    @commands.has_permissions(manage_channels=True)
    async def all(self, ctx, channel: discord.TextChannel = None):
        """ Remove ALL competitions from a live-scores channel

        Either perform ls remove all in the channel you wish to delete it from, or use
        ls remove all #channel to delete it from another channel."""
        channel = ctx.channel if channel is None else channel
        if channel.id not in {i[1] for i in self.cache}:
            return await ctx.send(f'{channel.mention} is not set as a scores channel.')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            async with connection.transaction():
                await connection.execute("""DELETE FROM scores_leagues WHERE channel_id = $1""", channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(f"✅ {channel.mention} no longer tracks any leagues. Use `ls reset` or `ls add` to "
                       f"re-popultate it with new leagues or the default leagues.")
    
    @ls.command(usage="ls reset <#channel>")
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, channel: discord.TextChannel = None):
        """ Reset competitions for a live-scores channel to the defaults.

        Either perform `ls reset` in the channel you wish to reset it from, or use
        `ls reset #channel` to reset it from another channel."""
        channel = ctx.channel if channel is None else channel
        if channel.id not in {i[1] for i in self.cache}:
            return await ctx.send(f'{channel.mention} is not set as a scores channel.')

        whitelist = self.cache[(ctx.guild.id, channel.id)]
        if whitelist == default_leagues:
            return await ctx.send(f"⚠ {channel.mention} is already using the default leagues.")
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" DELETE FROM scores_leagues WHERE channel_id = $1 """, channel.id)
            for i in default_leagues:
                await connection.execute("""INSERT INTO scores_leagues (channel_id, league) VALUES ($1, $2)""",
                                         channel.id, i)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(f"✅ {channel.mention} had it's tracked leagues reset to the defaults.")
    

def setup(bot):
    bot.add_cog(Scores(bot))
