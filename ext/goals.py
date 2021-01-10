import discord
from discord.ext import commands
import asyncio
import functools
import typing
from collections import defaultdict
from ext.utils import football, embed_utils

DEFAULT_LEAGUES = [
    "WORLD: Friendly international",
    "EUROPE: Champions League",
    "EUROPE: Euro",
    "EUROPE: Europa League",
    "EUROPE: UEFA Nations League",
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

# max_concurrency equivalent
sl_lock = asyncio.Semaphore()


async def send_leagues(ctx, channel, leagues):
    e = discord.Embed()
    embeds = embed_utils.rows_to_embeds(e, list(leagues))
    await embed_utils.paginate(ctx, embeds, header=f"Tracked leagues for {channel.mention}")


class Goals(commands.Cog):
    """ Ignore this. It's still in testing. """

    def __init__(self, bot):
        self.bot = bot
        self.cache = defaultdict(set)
        self.bot.loop.create_task(self.update_cache())

    @commands.Cog.listener()
    async def on_fixture_event(self, mode, f: football.Fixture, home=True):
        e = await f.base_embed
        e.title = None
        e.remove_author()
    
        async with sl_lock:
            ftp = functools.partial(f.refresh, driver=self.bot.fixture_driver, for_discord=True)
            await self.bot.loop.run_in_executor(None, ftp)
    
        e.set_footer(text=f"{f.country}: {f.league} | {f.time}")
    
        if mode == "goal":
            if home:
                hb, ab = '**', ''
            else:
                hb, ab = '', '**'
            e.description = f"**GOAL**: [{hb}{f.home} {f.score_home}{hb} - {ab}{f.score_away} {f.away}{ab}]({f.url})"
        elif mode == "dismissal":
            e.description = f"🟥 **RED CARD**: [{f.home} {f.score_home} - {f.score_away} {f.away}]({f.url})"
    
        event = [i for i in f.events][-1]
    
        if event.type == "goal":
            try:
                description = f"`⚽ {event.time}`: {event.player} ({event.team})"
            except AttributeError:
                description = f"`⚽ {event.time}`: Scorer info not found."
            if hasattr(event, "note"):
                if event.note == "Penalty":
                    description += " (pen.)"
        
            e.description += f"\n{description}"
    
        elif event.type == "Penalty miss":
            e.description += f"`🚫 {event.time}:` {event.type}: {event.player}"
    
        elif event.type in ["dismissal", "2yellow"]:
            e.description += f"\n`🟥 {event.time}:` {event.player} {event.team} player dismissed"
            if hasattr(event, "note"):
                e.description += f" ({event.note})"
    
        elif event.type in ["header", "substitution", "booking"]:
            return
        else:
            print("Goals - Notify - Unhandled event type", event.type)
    
        for (guild_id, channel_id) in self.cache:
            if f.league in self.cache[(guild_id, channel_id)]:
                channel = self.bot.get_channel(channel_id)
                await channel.send(embed=e)
                print("Event output success")
    
    async def update_cache(self):
        # Grab most recent data.
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            records = await connection.fetch("""
            SELECT guild_id, goals_channels.channel_id, league
            FROM goals_channels
            LEFT OUTER JOIN goals_leagues
            ON goals_channels.channel_id = goals_leagues.channel_id""")
        await self.bot.db.release(connection)
        
        # Clear out our cache.
        self.cache.clear()
        
        # Repopulate.
        for r in records:
            if self.bot.get_channel(r['channel_id']) is None:
                print(f"GOALS potentially deleted channel: {r['channel_id']}")
                continue
            
            key = (r["guild_id"], r["channel_id"])
            if r["league"] is not None:
                self.cache[key].add(r["league"])
    
    async def _pick_channels(self, ctx, channels):
        # Assure guild has score channel.
        if ctx.guild.id not in [i[0] for i in self.cache]:
            await ctx.reply(f'{ctx.guild.name} does not have any goal tickers.', mention_author=True)
            channels = []
        
        if channels:
            # Verify selected channels are actually in the database.
            checked = []
            for i in channels:
                if i.id not in [c[1] for c in self.cache]:
                    await ctx.reply(f"{i.mention} does not have any goal tickers.", mention_author=True)
                else:
                    checked.append(i)
            channels = checked
        
        if not channels:
            # Channel picker for invoker.
            def check(message):
                return ctx.author.id == message.author.id and message.channel_mentions
            
            guild_channels = [self.bot.get_channel(i[1]) for i in self.cache if i[0] == ctx.guild.id]
            guild_channels = [i for i in guild_channels if i is not None]  # fuckin deleting channel dumbfucks.
            channels = guild_channels
            if ctx.channel in guild_channels:
                return [ctx.channel]
            elif len(channels) != 1:
                async with ctx.typing():
                    mention_list = " ".join([i.mention for i in channels])
                    m = await ctx.reply(
                        f"{ctx.guild.name} has multiple goal tickers: ({mention_list}), please specify "
                        f"which one(s) to check or modify.", mention_author=False)
                    try:
                        channels = await self.bot.wait_for("message", check=check, timeout=30)
                        channels = channels.channel_mentions
                        await m.delete()
                    except asyncio.TimeoutError:
                        try:
                            await m.edit(
                                content="Timed out waiting for you to reply with a channel list. No channels were "
                                        "modified.")
                        except discord.NotFound:
                            pass
                        channels = []
        return channels
    
    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def goals(self, ctx, *, channel: typing.Optional[discord.TextChannel] = None):
        """ View the status of your goal tickers. """
        e = discord.Embed(color=0x2ecc71)
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = f"{ctx.guild.name} Goal Tickers"
        
        if channel is None:
            goal_ids = [i[1] for i in self.cache if ctx.guild.id in i]
            if not goal_ids:
                return await ctx.reply(f"{ctx.guild.name} has no goal tickers set.", mention_author=True)
        else:
            goal_ids = [channel.id]
        
        for i in goal_ids:
            ch = self.bot.get_channel(i)
            if ch is None:
                continue
            
            e.title = f'{ch.name} tracked leagues '
            # Warn if they fuck up permissions.
            if not ctx.me.permissions_in(ch).send_messages:
                e.description = "```css\n[WARNING]: I do not have send_messages permissions in that channel!"
            if not ctx.me.permissions_in(ch).embed_links:
                e.description = "```css\n[WARNING]: I do not have embed_link permissions in that channel!"
            leagues = self.cache[(ctx.guild.id, i)]
            await send_leagues(ctx, ch, leagues)
    
    @goals.command(usage="[#channel-Name]")
    @commands.has_permissions(manage_channels=True)
    async def create(self, ctx, ch: discord.TextChannel = None):
        """ Add a goal ticker to one of your server's channels. """
        if ch is None:
            ch = ctx.channel
        connection = await self.bot.db.acquire()
        
        async with connection.transaction():
            await connection.execute(
                """ INSERT INTO goals_channels (guild_id, channel_id) VALUES ($1, $2) """, ctx.guild.id, ch.id)
            for i in DEFAULT_LEAGUES:
                await connection.execute(
                    """ INSERT INTO goals_leagues (channel_id, league) VALUES ($1, $2) """, ch.id, i)
        
        await self.bot.db.release(connection)
        await ctx.reply(f"A goal ticker was added to {ch.mention}", mention_author=False)
        await self.update_cache()
    
    @commands.has_permissions(manage_channels=True)
    @goals.command(usage="[#channel #channel2] <search query or flashscore link>")
    @commands.is_owner()
    async def add(self, ctx, channels: commands.Greedy[discord.TextChannel], *, qry: commands.clean_content = None):
        """ Add a league to a goal ticker for a channel """
        channels = await self._pick_channels(ctx, channels)
        
        if not channels:
            return  # rip
            
        if qry is None:
            return await ctx.reply("Specify a competition name to search for, example usage:\n"
                                   f"{ctx.prefix}{ctx.command} #live-scores Premier League", metion_author=True)
        
        if "http" not in qry:
            await ctx.reply(f"Searching for {qry}...", delete_after=5, mention_author=False)
            res = await football.fs_search(ctx, qry)
        else:
            res = football.Competition().by_link(qry, driver=self.bot.fixture_driver)
        
        if res is None:
            return
        
        res = f"{res.title}"
        
        for c in channels:
            if (ctx.guild.id, c.id) not in self.cache:
                await ctx.reply(f'🚫 {c.mention} does not have a goal ticker.', mention_author=True)
                continue
            
            leagues = self.cache[(ctx.guild.id, c.id)]
            leagues.add(res)
            for league in leagues:
                connection = await self.bot.db.acquire()
                async with connection.transaction():
                    await connection.execute("""
                        INSERT INTO goals_leagues (league,channel_id)
                        VALUES ($1,$2)
                        ON CONFLICT DO NOTHING
                    """, league, c.id)
                await self.bot.db.release(connection)
            
            await ctx.reply(f"✅ **{res}** added to the tracked leagues for {c.mention}", mention_author=False)
            await send_leagues(ctx, c, leagues)
        
        await self.update_cache()
    
    @goals.group(name="remove", aliases=["del", "delete"], usage="[#channel, #channel2] <Country: League Name>",
                 invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def _remove(self, ctx, channels: commands.Greedy[discord.TextChannel], *, target: commands.clean_content):
        """ Remove a competition from a channel's goal ticker """
        # Verify we have a valid live-scores channel target.
        channels = await self._pick_channels(ctx, channels)
        
        if not channels:
            return  # rip
        
        all_leagues = set()
        target = target.strip("'\",")  # Remove quotes, idiot proofing.
        
        for c in channels:  # Fetch All
            leagues = self.cache[(ctx.guild.id, c.id)]
            all_leagues |= set([i for i in leagues if target.lower() in i.lower()])
        
        # Verify which league the user wishes to remove.
        all_leagues = list(all_leagues)
        index = await embed_utils.page_selector(ctx, all_leagues)
        if index is None:
            return  # rip.
        
        target = all_leagues[index]
        
        for c in channels:
            if c.id not in {i[1] for i in self.cache}:
                await ctx.reply(f'{c.mention} does not have a goal ticker.', mention_author=True)
                continue
            
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute(""" DELETE FROM goals_leagues WHERE (league,channel_id) = ($1,$2)""",
                                         target, c.id)
            await self.bot.db.release(connection)
            leagues = self.cache[(ctx.guild.id, c.id)]
            leagues.remove(target)
            await ctx.reply(f"✅ **{target}** deleted from {c.mention} tracked leagues ", mention_author=False)
            await send_leagues(ctx, c, leagues)
        
        await self.update_cache()
    
    @_remove.command(usage="<channel_id>")
    @commands.is_owner()
    async def admin(self, ctx, channel_id: int):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" DELETE FROM goals_channels WHERE channel_id = $1""", channel_id)
        await self.bot.db.release(connection)
        await ctx.reply(f"✅ **{channel_id}** was deleted from the scores database", mention_author=False)
        await self.update_cache()
    
    @_remove.command(usage="[#channel-name]")
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def all(self, ctx, channel: discord.TextChannel = None):
        """ Remove ALL competitions from a live-scores channel """
        channel = ctx.channel if channel is None else channel
        if channel.id not in {i[1] for i in self.cache}:
            return await ctx.reply(f'{channel.mention} does not have a goal ticker.')
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            async with connection.transaction():
                await connection.execute("""DELETE FROM goals_leagues WHERE channel_id = $1""", channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.reply(f"✅ {channel.mention} no longer tracks any leagues. Use `ls add` or `ls reset` to "
                        f"re-populate it with new leagues or the default leagues.", mention_author=False)
    
    @goals.command(usage="[#channel-name]")
    @commands.has_permissions(manage_channels=True)
    @commands.is_owner()
    async def reset(self, ctx, channel: discord.TextChannel = None):
        """ Reset competitions for a live-scores channel to the defaults. """
        channel = ctx.channel if channel is None else channel
        if channel.id not in {i[1] for i in self.cache}:
            return await ctx.reply(f'{channel.mention} does not have a goal ticker', mention_author=True)
        
        whitelist = self.cache[(ctx.guild.id, channel.id)]
        if whitelist == DEFAULT_LEAGUES:
            return await ctx.reply(f"⚠ {channel.mention} is already using the default leagues.", mention_author=False)
        
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" DELETE FROM goals_leagues WHERE channel_id = $1 """, channel.id)
            for i in DEFAULT_LEAGUES:
                await connection.execute("""INSERT INTO goals_leagues (channel_id, league) VALUES ($1, $2)""",
                                         channel.id, i)
        await self.bot.db.release(connection)
        await ctx.reply(f"✅ {channel.mention} had it's tracked leagues reset to the defaults.", mention_author=False)
        await self.update_cache()
    
    # Event listeners for channel deletion or guild removal.
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if (channel.guild.id, channel.id) in self.cache:
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute(""" DELETE FROM goals_channels WHERE channel_id = $1 """, channel.id)
            await self.bot.db.release(connection)
            await self.update_cache()
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in [i[0] for i in self.cache]:
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute(""" DELETE FROM goals_channels WHERE guild_id = $1 """, guild.id)
            await self.bot.db.release(connection)
            await self.update_cache()


def setup(bot):
    bot.add_cog(Goals(bot))
