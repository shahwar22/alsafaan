import functools
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
        if self.bot.fixture_driver is None:
            self.bot.fixture_driver = spawn_driver()
        for package in [transfer_tools, football, embed_utils]:
            reload(package)

    # Master picker.
    async def _search(self, ctx, qry, status_message: discord.Message, mode=None) -> str or None:
        # Handle stupidity
        if qry is None:
            err = "Please specify a search query."
            if ctx.guild is not None:
                default = await self._fetch_default(ctx, mode)
                if default is not None:
                    if mode == "team":
                        team_id = default.split('/')[-1]
                        ftp = functools.partial(football.Team.by_id, team_id, driver=self.bot.fixture_driver)
                    else:
                        ftp = functools.partial(football.Competition.by_link, default, driver=self.bot.fixture_driver)
                    fsr = await self.bot.loop.run_in_executor(None, ftp)
                    return fsr
            else:
                err += f"\nA default team or league can be set by moderators using {ctx.prefix}default)"
            await status_message.edit(text=err)
            return None

        search_results = await football.get_fs_results(qry)
        
        if not search_results:
            output = f'No search results found for search query: {qry}'
            if mode is not None:
                output += f" ({mode})"
            await status_message.edit(text=output)
            return None
        
        pt = 0 if mode == "league" else 1 if mode == "team" else None  # Mode is a hard override.
        if pt is not None:
            item_list = [i.title for i in search_results if i.participant_type_id == pt]  # Check for specifics.
        else:  # All if no mode
            item_list = [i.title for i in search_results]
        index = await embed_utils.page_selector(ctx, item_list)

        if index is None:
            await status_message.edit(text='Result selection timed out or cancelled.')
            return None
        return search_results[index]

    # Fetch from bot games.
    async def _pick_game(self, ctx, q: str, search_type=None) -> typing.Union[football.Fixture, None]:
        q = q.lower()
        
        if search_type == "team":
            matches = [i for i in self.bot.games if q in f"{i.home.lower()} vs {i.away.lower()}"]
        else:
            matches = [i for i in self.bot.games if q in (i.home + i.away + i.league + i.country).lower()]
        
        if not matches:
            return None
    
        base_embed = discord.Embed()
        base_embed.set_footer(text="If you did not want a live game, click the '🚫' reaction to search all teams")
        base_embed.title = "Live matches found!"
        
    
        pickers = [str(i) for i in matches]
        index = await embed_utils.page_selector(ctx, pickers, base_embed=base_embed)
        if index is None:
            return None  # timeout or abort.
    
        return matches[index]
    
    # TODO: Rewrite to use json response
    async def _fetch_default(self, ctx, mode=None):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
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
        db_mode = "default_team" if mode == "team" else "default_league"
    
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
            output = f"Your default league is: <{league}>"
            team = record["default_team"] if record["default_team"] is not None else "not set."
            output += f"\nYour default team is: <{team}>"
        
            return await ctx.send(output)
    
        if qry.lower() == "none":  # Intentionally set Null for DB entry
            url = None
        else:  # Find
            await ctx.send(f'Searching for {qry}...', delete_after=5)
            fsr = await self._search(ctx, qry, mode=mode)
        
            if fsr is None:
                return
        
            url = fsr.link
    
        connection = await self.bot.db.acquire()
    
        async with connection.transaction():
            await connection.execute(
                f"""INSERT INTO scores_settings (guild_id,{db_mode})
                VALUES ($1,$2)

                ON CONFLICT (guild_id) DO UPDATE SET
                    {db_mode} = $2
                WHERE excluded.guild_id = $1
            """, ctx.guild.id, url)
    
        await self.bot.db.release(connection)
    
        if qry is not None:
            return await ctx.send(f'Your commands will now use <{url}> as a default {mode}')
        else:
            return await ctx.send(f'Your commands will no longer use a default {mode}')
    
    # Team OR League specific
    @commands.command(usage="[league or team to search for or leave blank to use server's default setting]")
    async def table(self, ctx, *, qry: commands.clean_content = None):
        """ Get table for a league """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            fsr = None
            if qry is not None:  # Grab from live games first, but only if a query is provided.
                fsr = await self._pick_game(ctx, str(qry), search_type="team")

            if fsr is None:
                fsr = await self._search(ctx, qry, status_message=m)
            
            if fsr is None:
                return
            
            dtn = datetime.datetime.now().ctime()
            await m.edit(text="Processing...")
            if isinstance(fsr, football.Team):  # Select from team's leagues.
                async with sl_lock:
                    choices = await self.bot.loop.run_in_executor(None, fsr.next_fixture, self.bot.fixture_driver)
                for_picking = [i.full_league for i in choices]
                embed = await fsr.base_embed
                index = await embed_utils.page_selector(ctx, for_picking, deepcopy(embed))
                if index is None:
                    return  # rip
                fsr = choices[index]

            async with sl_lock:
                image = await self.bot.loop.run_in_executor(None, fsr.table, self.bot.fixture_driver)
            
            embed = await fsr.base_embed
            embed.description = f"```yaml\n[{dtn}]```"
            
            fn = f"Table-{qry}-{dtn}.png".strip()
            await m.delete()
            await embed_utils.embed_image(ctx, embed, image, filename=fn)

    @commands.command(aliases=['draw'])
    async def bracket(self, ctx, *, qry: commands.clean_content = None):
        """ Get bracket for a tournament """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            fsr = None
            if qry is not None:  # Grab from live games first, but only if a query is provided.
                fsr = await self._pick_game(ctx, str(qry), search_type="team")
    
            if fsr is None:
                fsr = await self._search(ctx, qry, status_message=m)
    
            if fsr is None:
                return
            
            await m.edit(text="Processing...")

            if isinstance(fsr, football.Team):  # Select from team's leagues.
                async with sl_lock:
                    choices = await self.bot.loop.run_in_executor(None, fsr.next_fixture, self.bot.fixture_driver)
                for_picking = [i.full_league for i in choices]

                embed = await fsr.base_embed
                index = await embed_utils.page_selector(ctx, for_picking, deepcopy(embed))
                if index is None:
                    return  # rip
                fsr = choices[index]
                
            embed = await fsr.base_embed

            async with sl_lock:
                image = await self.bot.loop.run_in_executor(None, fsr.bracket, self.bot.fixture_driver)
                
            fn = f"Bracket-{qry}-{datetime.datetime.now().ctime()}.png".strip()
            await embed_utils.embed_image(ctx, embed, image, filename=fn)

    @commands.command(aliases=['fx'], usage="<Team or league name to search for>")
    async def fixtures(self, ctx, *, qry: commands.clean_content = None):
        """ Fetch upcoming fixtures for a team or league.
        Navigate pages using reactions. """
        m = await ctx.send("Searching...")
        fsr = await self._search(ctx, qry, status_message=m)

        if fsr is None:
            return
        
        await m.edit(text="Processing...")
        async with sl_lock:
            fx = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.bot.fixture_driver, '/fixtures')
        fixtures = [str(i) for i in fx]
        embed = await fsr.base_embed
        embed.title = f"≡ Fixtures for {embed.title}" if embed.title else "≡ Fixtures "
        
        embeds = embed_utils.rows_to_embeds(embed, fixtures)
        await m.delete()
        await embed_utils.paginate(ctx, embeds)
    
    @commands.command(aliases=['rx'], usage="<Team or league name to search for>")
    async def results(self, ctx, *, qry: commands.clean_content = None):
        """ Get past results for a team or league.
        Navigate pages using reactions. """
        m = await ctx.send("Searching...")
        fsr = await self._search(ctx, qry, status_message=m)

        if fsr is None:
            return

        await m.edit(text="Processing...")
        
        async with sl_lock:
            results = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.bot.fixture_driver, '/results')
        results = [str(i) for i in results]
        embed = await fsr.base_embed
        embed.title = f"≡ Results for {embed.title}" if embed.title else "≡ Results "
        embeds = embed_utils.rows_to_embeds(embed, results)
        await m.delete()
        await embed_utils.paginate(ctx, embeds)
    
    @commands.command()
    async def stats(self, ctx, *, qry: commands.clean_content):
        """ Look up the stats for one of today's games """
        async with ctx.typing():
            m = await ctx.send('Searching...')
            game = await self._pick_game(ctx, str(qry), search_type="team")
            
            # TODO: Pick game for all previous results.
            if game is None:
                await m.edit(text=f"Unable to find a live match for {qry}")
                return
            else:
                await m.edit(text="Processing...")
            
            async with sl_lock:
                file = await self.bot.loop.run_in_executor(None, game.stats_image, self.bot.fixture_driver)
            embed = await game.base_embed
            await m.delete()
            await embed_utils.embed_image(ctx, embed, file)

    @commands.command(usage="<team to search for>", aliases=["formations", "lineup", "lineups"])
    async def formation(self, ctx, *, qry: commands.clean_content):
        """ Get the formations for the teams in one of today's games """
        async with ctx.typing():
            m = await ctx.send('Searching...')
            game = await self._pick_game(ctx, str(qry), search_type="team")
            
            # TODO: Pick game for all previous results
            if game is None:
                await m.edit(text=f"Unable to find a match for {qry}")
                return

            async with sl_lock:
                file = await self.bot.loop.run_in_executor(None, game.formation, self.bot.fixture_driver)
            embed = await game.base_embed
            await m.delete()
            await embed_utils.embed_image(ctx, embed, file)
    
    @commands.command()
    async def summary(self, ctx, *, qry: commands.clean_content):
        """ Get a summary for one of today's games. """
        async with ctx.typing():
            m = await ctx.send('Searching...')
            game = await self._pick_game(ctx, str(qry), search_type="team")
    
            # TODO: Pick game for all previous results
            if game is None:
                await m.edit(text=f"Unable to find a match for {qry}")
                return

            async with sl_lock:
                file = await self.bot.loop.run_in_executor(None, game.summary, self.bot.fixture_driver)
            embed = await game.base_embed
            await m.delete()
            await embed_utils.embed_image(ctx, embed, file)

    @commands.command(aliases=["form"], usage="<Team name to search for>")
    async def h2h(self, ctx, *, qry: commands.clean_content):
        """ Get Head to Head data for a team's next fixture """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            fsr = None
            if qry is not None:  # Grab from live games first, but only if a query is provided.
                fsr = await self._pick_game(ctx, str(qry), search_type="team")
    
            if fsr is None:
                fsr = await self._search(ctx, qry, status_message=m)
    
            if fsr is None:
                return
    
            await m.edit(text="Processing...")
            if isinstance(fsr, football.Team):  # Select from team's leagues.
                async with sl_lock:
                    choices = await self.bot.loop.run_in_executor(None, fsr.next_fixture, self.bot.fixture_driver)
                for_picking = [i.full_league for i in choices]
                embed = await fsr.base_embed
                index = await embed_utils.page_selector(ctx, for_picking, deepcopy(embed))
                if index is None:
                    return  # rip
                fsr = choices[index]
        
            async with sl_lock:
                fx = await self.bot.loop.run_in_executor(None, fsr.next_fixture, self.bot.fixture_driver, "/fixtures")
                h2h = await self.bot.loop.run_in_executor(None, fx.head_to_head, self.bot.fixture_driver)
        
            e = await fx.base_embed
            e.description = f"Head to Head data for {fx.home} vs {fx.away}"
            for k, v in h2h.items():
            
                e.add_field(name=k, value="\n".join([str(i) for i in v]), inline=False)
            await ctx.send(embed=e)

    # Team specific.
    @commands.command(aliases=["suspensions"], usage="<Team name to search for>")
    async def injuries(self, ctx, *, qry: commands.clean_content = None):
        """ Get a team's current injuries """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            fsr = await self._search(ctx, qry, status_message=m, mode="team")
        
            if fsr is None:
                return
            
            await m.edit(text="Processing...")
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.bot.fixture_driver)

            embed = await fsr.base_embed
            players = [f"{i.flag} [{i.name}]({i.link}) ({i.position}): {i.injury}" for i in players if i.injury]
            players = players if players else ['No injuries found']
            embed.title = f"≡ Injuries for {embed.title}" if embed.title else "≡ Injuries "
            embeds = embed_utils.rows_to_embeds(embed, players)
            await m.delete()
            await embed_utils.paginate(ctx, embeds)
    
    @commands.command(aliases=["team", "roster"], usage="<Team name to search for>")
    async def squad(self, ctx, *, qry: commands.clean_content = None):
        """ Lookup a team's squad members """
        async with ctx.typing():
            m = await ctx.send("Searching...")
            fsr = await self._search(ctx, qry, status_message=m, mode="team")
    
            if fsr is None:
                return
    
            await m.edit(text="Processing...")
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.bot.fixture_driver)
            srt = sorted(players, key=lambda x: x.number)
            embed = await fsr.base_embed
            embed.title = f"≡ Squad for {embed.title}" if embed.title else "≡ Squad "
            players = [f"`{str(i.number).rjust(2)}`: {i.flag} [{i.name}]({i.link}) {i.position}{i.injury}" for i in srt]
            embeds = embed_utils.rows_to_embeds(embed, players)
            await m.delete()
            await embed_utils.paginate(ctx, embeds)
    
    @commands.command(invoke_without_command=True, aliases=['sc'], usage="<team or league to search for>")
    async def scorers(self, ctx, *, qry: commands.clean_content = None):
        """ Get top scorers from a league, or search for a team and get their top scorers in a league. """
        m = await ctx.send("Searching...")
        fsr = await self._search(ctx, qry, status_message=m)

        if fsr is None:
            return

        await m.edit(text="Processing...")

        embed = await fsr.base_embed
        
        if isinstance(fsr, football.Competition):
            async with sl_lock:
                sc = await self.bot.loop.run_in_executor(None, fsr.scorers, self.bot.fixture_driver)
            players = [f"{i.flag} [{i.name}]({i.link}) ({i.team}) {i.goals} Goals, {i.assists} Assists" for i in sc]

            embed.title = f"≡ Top Scorers for {embed.title}" if embed.title else "≡ Top Scorers "
        else:
            async with sl_lock:
                choices = await self.bot.loop.run_in_executor(None, fsr.player_competitions, self.bot.fixture_driver)

            embed.set_author(name="Pick a competition")
            index = await embed_utils.page_selector(ctx, choices, base_embed=embed)
            if index is None:
                return  # rip
            
            async with sl_lock:
                players = await self.bot.loop.run_in_executor(None, fsr.players, self.bot.fixture_driver, index)
            players = sorted([i for i in players if i.goals > 0], key=lambda x: x.goals, reverse=True)
            players = [f"{i.flag} [{i.name}]({i.link}) {i.goals} in {i.apps} appearances" for i in players]

            embed.title = f"≡ Top Scorers for {embed.title} in {choices[index]}" if embed.title \
                else f"Top Scorers in {choices[index]}"
        
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

def setup(bot):
    bot.add_cog(Fixtures(bot))
