from collections import defaultdict
from copy import deepcopy
import asyncio
import datetime
import typing

# D.py
from discord.ext import commands
import discord

# Custom Utils
from ext.utils import transfer_tools, football, embed_utils
from ext.utils.selenium_driver import spawn_driver
from importlib import reload

# max_concurrency equivalent
sl_lock = asyncio.Semaphore()

# TODO: Find somewhere to get goal clips from.


class Fixtures(commands.Cog):
    """ Lookups for Past, Present and Future football matches. """
    
    def __init__(self, bot):
        self.bot = bot
        try:
            self.driver = self.bot.fixture_driver
        except AttributeError:
            self.bot.fixture_driver = spawn_driver()
            self.driver = self.bot.fixture_driver
        for package in [transfer_tools, football, embed_utils]:
            reload(package)

    # Master picker.
    async def _search(self, ctx, qry, mode=None) -> str or None:
        if qry is None:
            err = "Please specify a search query."
            if ctx.guild is not None:
                result = await self._fetch_default(ctx, mode)
                if result is not None:
                    if mode == "team":
                        sr = football.Team(override=result, title=f"{ctx.guild.name} default")
                    else:
                        sr = football.Competition(override=result, title=f"{ctx.guild.name} default")
                    return sr
            else:
                err += f"\nA default team or league can be set by moderators using {ctx.prefix}default)"
            await ctx.send(err)
            return None

        search_results = await football.get_fs_results(qry)
        pt = 0 if mode == "league" else 1 if mode == "team" else None  # Mode is a hard override.
        if pt is not None:
            item_list = [i.title for i in search_results if i.participant_type_id == pt]  # Check for specifics.
        else:  # All if no mode
            item_list = [i.title for i in search_results]
        index = await embed_utils.page_selector(ctx, item_list)

        if index is None:
            return  # Timeout or abort.

        return search_results[index]

    # Fetch from bot games.
    async def _pick_game(self, ctx, qry) -> typing.Union[football.Fixture, None]:
        q = qry.lower()
        matches = [i for i in self.bot.games if q in (i.home + i.away + i.league + i.country).lower()]
        if not matches:
            return
    
        pickers = [str(i) for i in matches]
        index = await embed_utils.page_selector(ctx, pickers)
        if index is None:
            return  # timeout or abort.
    
        return matches[index]
    
    # TODO: Rewrite to use json response
    async def _fetch_default(self, ctx, mode=None):
        connection = await self.bot.db.acquire()
        r = await connection.fetchrow("""
             SELecT * FROM scores_settings WHERE (guild_id) = $1
             AND (default_league is NOT NULL OR default_team IS NOT NULL) """, ctx.guild.id)
        await self.bot.db.release(connection)
        if r:
            team = r["default_team"]
            league = r["default_league"]
            # Decide if found, yell if not.
            if any([league, team]):
                if mode == "team":
                    return team if team else league
                return league if league else team
        return None

    # TODO: Rewrite to use json response
    @commands.has_permissions(manage_guild=True)
    @commands.command(usage="<'team' or 'league'> <(Your Search Query) or ('None' to unset.)")
    async def default(self, ctx, mode, *, qry: commands.clean_content = None):
        """ Set a default team or league for your server's lookup commands """
        # Validate
        mode = mode.lower()
        if mode not in ["league", "team"]:
            return await ctx.send(':no_entry_sign: Invalid default type specified, valid types are "league" or "team"')
        mode = "default_team" if mode == "team" else "default_league"
    
        if qry is None:
            connection = await self.bot.db.acquire()
            record = await connection.fetchrow("""
                SELecT * FROM scores_settings
                WHERE (guild_id) = $1
                AND (default_league is NOT NULL OR default_team IS NOT NULL)
            """, ctx.guild.id)
            await self.bot.db.release(connection)
            if not record:
                return await ctx.send(f"{ctx.guild.name} does not currently have a default team or league set.")
            league = record["default_league"] if record["default_league"] is not None else "not set."
            output = f"Your default league is: {league}"
            team = record["default_team"] if record["default_team"] is not None else "not set."
            output += "\n" + team
        
            return await ctx.send(output)
    
        if qry.lower() == "none":  # Intentionally set Null for DB entry
            url = None
        else:  # Find
            await ctx.send(f'Searching for {qry}...', delete_after=5)
            fsr = await self._search(ctx, qry, mode=mode)
        
            if fsr is None:
                return await ctx.send(f"Couldn't find matching {mode} for {qry}, try searching for something else.")
        
            url = fsr.link
    
        connection = await self.bot.db.acquire()
    
        async with connection.transaction():
            await connection.execute(
                f"""INSERT INTO scores_settings (guild_id,{mode})
                VALUES ($1,$2)

                ON CONFLICT (guild_id) DO UPDATE SET
                    {mode} = $2
                WHERE excluded.guild_id = $1
            """, ctx.guild.id, url)
    
        await self.bot.db.release(connection)
    
        if qry is not None:
            return await ctx.send(f'Your commands will now use <{url}> as a default {mode}')
        else:
            return await ctx.send(f'Your commands will no longer use a default {mode}')
    
    @commands.command(usage="[Optional: league or team to search for]")
    async def table(self, ctx, *, qry: commands.clean_content = None):
        """ Get table for a league """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry)
            if fsr is None:
                return  # rip.
            
            dtn = datetime.datetime.now().ctime()
            
            if isinstance(fsr, football.Competition):
                async with sl_lock:
                    image = await self.bot.loop.run_in_executor(None, fsr.table, self.driver)

                embed = await fsr.base_embed
                embed.title = fsr.title
                embed.description = f"```yaml\n[{dtn}]```"
            elif isinstance(fsr, football.Team):
                async with sl_lock:
                    choices = await self.bot.loop.run_in_executor(None, fsr.next_fixture, self.driver)
                for_picking = [i.full_league for i in choices]
                embed = await fsr.base_embed
                index = await embed_utils.page_selector(ctx, for_picking, deepcopy(embed))
                if index is None:
                    return  # rip
                embed.title = for_picking[index]
                embed.description = f"{choices[index]}"
                image = await self.bot.loop.run_in_executor(None, choices[index].table, self.driver)
            fn = f"Table-{qry}-{dtn}.png".strip()
            await embed_utils.embed_image(ctx, embed, image, filename=fn)

    @commands.command(aliases=['draw'])
    async def bracket(self, ctx, *, qry: commands.clean_content = None):
        """ Get bracket for a tournament """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry)
            if fsr is None:
                return  # rip.
            
            dtn = datetime.datetime.now().ctime()

            if isinstance(fsr, football.Competition):
                async with sl_lock:
                    image = await self.bot.loop.run_in_executor(None, fsr.bracket, self.driver)
    
                embed = await fsr.base_embed
                embed.title = fsr.title
                embed.description = f"```yaml\n[{dtn}]```"
            elif isinstance(fsr, football.Team):
                async with sl_lock:
                    choices = await self.bot.loop.run_in_executor(None, fsr.next_fixture, self.driver)
                for_picking = [i.full_league for i in choices]
                embed = await fsr.base_embed
                index = await embed_utils.page_selector(ctx, for_picking, deepcopy(embed))
                if index is None:
                    return  # rip
                embed.title = for_picking[index]
                embed.description = f"{choices[index]}"
                image = await self.bot.loop.run_in_executor(None, choices[index].bracket, self.driver)
            fn = f"Bracket-{qry}-{dtn}.png".strip()
            await embed_utils.embed_image(ctx, embed, image, filename=fn)

    @commands.command(aliases=['fx'], usage="fixtures <team or league to search for>")
    async def fixtures(self, ctx, *, qry: commands.clean_content = None):
        """ Fetch upcoming fixtures for a team or league.
        Navigate pages using reactions. """
        await ctx.send('Searching...', delete_after=5)
        fsr = await self._search(ctx, qry)
        if fsr is None:
            return  # Handled in _search.
        
        async with sl_lock:
            fixtures = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.driver, '/fixtures')
        fixtures = [str(i) for i in fixtures]
        embed = await fsr.base_embed
        embed.title = f"≡ Fixtures for {embed.title}"
        embeds = embed_utils.rows_to_embeds(embed, fixtures)
        await embed_utils.paginate(ctx, embeds)
    
    @commands.command(aliases=['rx'], usage="<team or league to search for>")
    async def results(self, ctx, *, qry: commands.clean_content = None):
        """ Get past results for a team or league.
        Navigate pages using reactions. """
        await ctx.send('Searching...', delete_after=5)
        fsr = await self._search(ctx, qry)
        if fsr is None:
            return
        
        async with sl_lock:
            results = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.driver, '/results')
        results = [str(i) for i in results]
        embed = await fsr.base_embed
        embed.title = f"≡ Results for {embed.title}"
        embeds = embed_utils.rows_to_embeds(embed, results)
        await embed_utils.paginate(ctx, embeds)
    
    @commands.command()
    async def stats(self, ctx, *, qry: commands.clean_content):
        """ Look up the stats for one of today's games """
        async with ctx.typing():
            await ctx.send('Searching...', delete_after=5)
            game = await self._pick_game(ctx, str(qry))
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")

            async with sl_lock:
                file = await self.bot.loop.run_in_executor(None, game.stats_image, self.driver)
            embed = game.base_embed
            await embed_utils.embed_image(ctx, embed, file)

    @commands.command(usage="<team to search for>", aliases=["formations", "lineup", "lineups"])
    async def formation(self, ctx, *, qry: commands.clean_content):
        """ Get the formations for the teams in one of today's games """
        async with ctx.typing():
            await ctx.send('Searching...', delete_after=5)
            game = await self._pick_game(ctx, str(qry))
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")

            async with sl_lock:
                file = await self.bot.loop.run_in_executor(None, game.formation, self.driver)
            embed = game.base_embed
            await embed_utils.embed_image(ctx, embed, file)
    
    @commands.command()
    async def summary(self, ctx, *, qry: commands.clean_content):
        """ Get a summary for one of today's games. """
        async with ctx.typing():
            await ctx.send('Searching...', delete_after=5)
            game = await self._pick_game(ctx, str(qry))
            if game is None:
                return await ctx.send(f"Unable to find a match for {qry}")

            async with sl_lock:
                file = await self.bot.loop.run_in_executor(None, game.summary, self.driver)
            embed = game.base_embed
            await embed_utils.embed_image(ctx, embed, file)

    @commands.command(aliases=["suspensions"], usage="<Team name to search for>")
    async def injuries(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's current injuries """
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry, mode="team")
        
            if fsr is None:
                return
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.driver)

            embed = await fsr.base_embed
            players = [f"{i.flag} [{i.name}]({i.link}) ({i.position}): {i.injury}" for i in players if i.injury]
            players = players if players else ['No injuries found']
            embed.title = f"Injuries for {embed.title}"
            embeds = embed_utils.rows_to_embeds(embed, players)
            await embed_utils.paginate(ctx, embeds)
    
    @commands.command(aliases=["team", "roster"], usage="<Team name to search for>")
    async def squad(self, ctx, *, qry: commands.clean_content):
        """ Lookup a team's squad members """
        
        qry = qry.strip('[]')
        
        async with ctx.typing():
            await ctx.send("Searching...", delete_after=5)
            fsr = await self._search(ctx, qry, mode="team")
            
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.driver)
            srt = sorted(players, key=lambda x: x.number)
            embed = await fsr.base_embed
            embed.title = f"Squad for {embed.title}"
            players = [f"`{str(i.number).rjust(2)}`: {i.flag} [{i.name}]({i.link}) {i.position}{i.injury}" for i in srt]
            embeds = embed_utils.rows_to_embeds(embed, players)
            await embed_utils.paginate(ctx, embeds)
    
    @commands.command(invoke_without_command=True, aliases=['sc'], usage="<team or league to search for>")
    async def scorers(self, ctx, *, qry: commands.clean_content):
        """ Get top scorers from a league, or search for a team and get their top scorers in a league. """
        await ctx.send("Searching...", delete_after=5)
        fsr = await self._search(ctx, str(qry))
        if fsr is None:
            return  # rip
        
        if isinstance(fsr, football.Competition):
            async with sl_lock:
                sc = await self.bot.loop.run_in_executor(None, fsr.scorers, self.driver)
            players = [f"{i.flag} [{i.name}]({i.link}) ({i.team}) {i.goals} Goals, {i.assists} Assists" for i in sc]
            embed = await fsr.base_embed
            embed.title = f"Top Scorers for {embed.title}"
        else:
            async with sl_lock:
                choices = await self.bot.loop.run_in_executor(None, fsr.player_competitions, self.driver)
            embed = await fsr.base_embed
            embed.set_author(name="Pick a competition")
            index = await embed_utils.page_selector(ctx, choices, base_embed=embed)
            if index is None:
                return  # rip
            
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.driver, index)
            players = sorted([i for i in players if i.goals > 0], key=lambda x: x.goals, reverse=True)
            players = [f"{i.flag} [{i.name}]({i.link}) {i.goals} in {i.apps} appearances" for i in players]
            embed = await fsr.base_embed
            embed.title = f"Top Scorers for {embed.title} in {choices[index]}"
        
        embeds = embed_utils.rows_to_embeds(embed, players)
        await embed_utils.paginate(ctx, embeds)
    
    @commands.command(usage="<league to search for>")
    async def scores(self, ctx, *, search_query: commands.clean_content = ""):
        """ Fetch current scores for a specified league """
        embeds = []
        e = discord.Embed()
        e.colour = discord.Colour.blurple()
        if search_query:
            e.set_author(name=f'Live Scores matching "{search_query}"')
        else:
            e.set_author(name="Live Scores for all known competitions")
            
        e.timestamp = datetime.datetime.now()
        dtn = datetime.datetime.now().strftime("%H:%M")
        q = search_query.lower()

        matches = [i for i in self.bot.games if q in (i.home + i.away + i.league + i.country).lower()]
        
        if not matches:
            e.description = "No results found!"
            return await embed_utils.paginate(ctx, [e])

        game_dict = defaultdict(list)
        for i in matches:
            game_dict[i.full_league].append(f"[{i.live_score_text}]({i.url})")

        for league in game_dict:
            games = game_dict[league]
            if not games:
                continue
            output = f"**{league}**\n"
            discarded = 0
            for i in games:
                if len(output + i) < 1944:
                    output += i + "\n"
                else:
                    discarded += 1
                    
            e.description = output + f"*and {discarded} more...*" if discarded else output
            e.description += f"\n*Time now: {dtn}\nPlease note this menu will NOT auto-update. It is a snapshot.*"
            embeds.append(deepcopy(e))
        await embed_utils.paginate(ctx, embeds)

    @commands.command(usage="<Team or Stadium name to search for.>")
    async def stadium(self, ctx, *, query):
        """ Lookup information about a team's stadiums """
        stadiums = await football.get_stadiums(query)
        item_list = [i.to_picker_row for i in stadiums]
    
        index = await embed_utils.page_selector(ctx, item_list)
    
        if index is None:
            return  # Timeout or abort.
    
        await ctx.send(embed=await stadiums[index].to_embed)

    @commands.command(aliases=["form"], usage="<Team name to search for>")
    async def h2h(self, ctx, *, qry: commands.clean_content):
        """ Get Head to Head data for a team's next fixture """
        fsr = await self._search(ctx, str(qry), mode="team")
        if fsr is None:
            return  # rip
        async with sl_lock:
            fx = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.bot.fixture_driver, "/fixtures")
            fx = fx[0]
            h2h = await self.bot.loop.run_in_executor(None, fx.head_to_head, self.bot.fixture_driver)
    
        e = fx.base_embed
        e.description = f"Head to Head data for {fx.home} vs {fx.away}"
        for k, v in h2h.items():

            e.add_field(name=k, value="\n".join([str(i) for i in v]), inline=False)
        await ctx.send(embed=e)

    @commands.command(usage="<Player, team, or league name to search for>")
    async def goals(self, ctx, qry: commands.clean_content):
        """ [Work in progress] Search for a goal video from today's games  """
        # Fetch JSON
        goals = await football.get_goals()
    
        # By scorer
        by_scorer = [i for i in goals if qry.lower() in i.title.lower()]
        by_team = [i for i in goals if qry.lower() in i.home.lower() or qry.lower() in i.away.lower()]
        by_league = [i for i in goals if qry.lower() in i.competition.lower()]
    
        all_goals = set(by_scorer + by_team + by_league)
    
        embeds = []
    
        unique_leagues = set([i.competition for i in all_goals])
        for league in unique_leagues:
            e = discord.Embed(description="")
            e.set_thumbnail(url='https://miro.medium.com/fit/c/210/210/1*_Qi7B6VkoF4YvhneoICulg.png')
            e.colour = discord.Color.orange()
            e.set_author(name=f"Videos for {qry}")
            e.title = f"{league}"
        
            matches = set([i.fixture for i in all_goals if i.competition == league])
            for game in matches:
                e.description += F"**{game}**\n"
                for goal in all_goals:
                    if goal.fixture == game:
                        e.description += f"{goal.markdown_link}\n"
            embeds.append(e)
        await embed_utils.paginate(ctx, embeds)


def setup(bot):
    bot.add_cog(Fixtures(bot))
