from ext.utils import football
from importlib import reload
from discord.ext import commands, tasks
from PIL import Image
from lxml import html
import datetime
import discord
import math
import praw
import re

NUFC_DISCORD_LINK = "\n\n[](https://discord.gg/TuuJgrA)"  # NUFC.


def rows_to_md_table(header, strings, per=20, reverse=True, max_length=10220):
    rows = []
    for num, obj in enumerate(strings):
        # Every row we buffer the length of the new result.
        max_length -= len(obj)
        # Every 20 rows we buffer the length of  another header.
        if num % 20 == 0:
            max_length -= len(header)
        if max_length < 0:
            break
        else:
            rows.append(obj)
    
    if not rows:
        return ""
    
    columns = (len(rows) // per) + 1
    height = math.ceil(len(rows) / columns)
    
    chunks = [''.join(rows[i:i + height]) for i in range(0, len(rows), height)]
    
    if reverse:
        chunks.reverse()
    
    return header + header.join(chunks)


class Sidebar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.reddit = praw.Reddit(**bot.credentials["Reddit"])
        self.driver = None
        self.bot.teams = None
        self.bot.sidebar = self.sidebar_loop.start()
        reload(football)
    
    def cog_unload(self):
        self.sidebar_loop.cancel()
        if self.driver is not None:
            self.driver.quit()
    
    async def cog_check(self, ctx):
        if ctx.guild is not None:
            return ctx.guild.id in [332159889587699712, 250252535699341312]
    
    @tasks.loop(hours=6)
    async def sidebar_loop(self):
        markdown = await self.make_sidebar()
        await self.bot.loop.run_in_executor(None, self.post_sidebar, markdown)

    @sidebar_loop.before_loop
    async def fetch_team_data(self):
        await self.bot.wait_until_ready()
        connection = await self.bot.db.acquire()
        self.bot.teams = await connection.fetch("""SELECT * FROM team_data""")
        await self.bot.db.release(connection)

    async def edit_caption(self, new_caption, subreddit="NUFC"):
        # The 'sidebar' wiki page has two blocks of --- surrounding the "caption"
        # We get the old caption, then replace it with the new one, then re-upload the data.
        old = await self.bot.loop.run_in_executor(None, self.get_header)
        markdown = re.sub(r'---.*?---', f"---\n\n> {new_caption}\n\n---", old, flags=re.DOTALL)
        await self.bot.loop.run_in_executor(None, self.bot.reddit.subreddit(subreddit).wiki['sidebar'].edit(markdown))
    
    def get_header(self, subreddit="NUFC"):
        return self.bot.reddit.subreddit(subreddit).wiki['sidebar'].content_md
        
    def post_sidebar(self, markdown, subreddit="NUFC"):
        self.bot.reddit.subreddit(subreddit).mod.update(description=markdown)
    
    def get_match_threads(self, last_opponent, subreddit="NUFC"):
        last_opponent = last_opponent.split(" ")[0]
        for i in self.bot.reddit.subreddit(subreddit).search('flair:"Pre-match thread"', sort="new", syntax="lucene"):
            if last_opponent in i.title:
                pre = f"[Pre]({i.url.split('?ref=')[0]})"
                break
        else:
            pre = "Pre"
        for i in self.bot.reddit.subreddit(subreddit).search('flair:"Match thread"', sort="new", syntax="lucene"):
            if not i.title.startswith("Match"):
                continue
            if last_opponent in i.title:
                match = f"[Match]({i.url.split('?ref=')[0]})"
                break
        else:
            match = "Match"
        
        for i in self.bot.reddit.subreddit(subreddit).search('flair:"Post-match thread"', sort="new", syntax="lucene"):
            if last_opponent in i.title:
                post = f"[Post]({i.url.split('?ref=')[0]})"
                break
        else:
            post = "Post"
        
        return f"\n\n### {pre} - {match} - {post}"
    
    async def table(self, qry):
        async with self.bot.session.get('http://www.bbc.co.uk/sport/football/premier-league/table') as resp:
            if resp.status != 200:
                return "Retry"
            tree = html.fromstring(await resp.text())
        
        table_data = ("\n\n* Table"
                      "\n\n Pos.|Team|P|W|D|L|GD|Pts"
                      "\n--:|:--|:--:|:--:|:--:|:--:|:--:|:--:\n")
        for i in tree.xpath('.//table[contains(@class,"gs-o-table")]//tbody/tr')[:20]:
            p = i.xpath('.//td//text()')
            rank = p[0].strip()  # Ranking
            movement = p[1].strip()
            if "hasn't" in movement:
                movement = ''
            elif "up" in movement:
                movement = '🔺'
            elif "down" in movement:
                movement = '🔻'
            else:
                movement = "?"
            team = p[2]
            try:
                # Insert subreddit link from db
                team = [i for i in self.bot.teams if i['name'] == team][0]
                team = f"[{team['name']}]({team['subreddit']})"
            except IndexError:
                print(team, "Not found in", [i['name'] for i in self.bot.teams])
            played, won, drew, lost = p[3:7]
            goal_diff, points = p[8:10]
            
            if qry.lower() in team.lower():
                table_data += f"{movement} {rank} | **{team}** | **{played}** | **{won}** | **{drew}** | **{lost}** | "\
                              f"**{goal_diff}** | **{points}**\n"
            else:
                table_data += f"{movement} {rank} | {team} | {played} | {won} | {drew} | {lost} | " \
                              f"{goal_diff} | {points}\n"
        return table_data

    async def make_sidebar(self, subreddit="NUFC", qry="newcastle", team_id="p6ahwuwJ"):
        # Fetch all data
        top = await self.bot.loop.run_in_executor(None, self.get_header)
        fsr = await football.Team.by_id(qry=qry, team_id=team_id)
        fixtures = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.bot.fixture_driver, "/fixtures")
        results = await self.bot.loop.run_in_executor(None, fsr.fetch_fixtures, self.bot.fixture_driver, "/results")
        table = await self.table(qry)

        # Get match threads
        match_threads = await self.bot.loop.run_in_executor(None, self.get_match_threads, subreddit, qry)
        
        # Insert team badges
        for x in fixtures + results:
            try:
                r = [i for i in self.bot.teams if i['name'] == x.home][0]
                x.home_icon =r['icon']
                x.home_subreddit = r['subreddit']
                x.short_home = r['short_name']
            except IndexError:
                x.home_icon = ""
                x.home_subreddit = "#temp"
                x.short_home = x.home
            try:
                r = [i for i in self.bot.teams if i['name'] == x.away][0]
                x.away_icon =r['icon']
                x.away_subreddit = r['subreddit']
                x.short_away = r['short_name']
            except IndexError:
                x.away_icon = ""
                x.away_subreddit = "#temp/"
                x.short_away = x.away
        
        # Build data with passed icons.
        last_match = results[0]
        
        # CHeck if we need to upload a temporary badge.
        if not last_match.home_icon:
            badge = await self.bot.loop.run_in_executor(None, last_match.get_badge, self.bot.fixture_driver, "home")
            await self.bot.loop.run_in_executor(None, self.upload_badge, badge)
        elif not last_match.away_icon:
            badge = await self.bot.loop.run_in_executor(None, last_match.get_badge, self.bot.fixture_driver, "away")
            await self.bot.loop.run_in_executor(None, self.upload_badge, badge)
            
        top_bar = last_match.top_bar
        if fixtures:
            header = "\n* Upcoming fixtures"
            th = "\n\n Date & Time | Match\n--:|:--\n"
            fx_markdown = header + rows_to_md_table(th, [i.sidebar_markdown for i in fixtures])  # Show all fixtures.
        else:
            fx_markdown = ""
        
        # After fetching everything, begin construction.
        timestamp = f"\n#####Sidebar updated {datetime.datetime.now().ctime()}\n"
        footer = timestamp + top_bar + match_threads
        
        if subreddit == "NUFC":
            footer += NUFC_DISCORD_LINK
        
        markdown = top + table + fx_markdown
        if results:
            header = "* Previous Results\n"
            markdown += header
            th = "\n Date | Result\n--:|:--\n"
            rx_markdown = rows_to_md_table(th, [i.sidebar_markdown for i in results], max_length=len(markdown + footer))
            markdown += rx_markdown
            
        markdown += footer
        return markdown
    
    def upload_badge(self, image):
        im = Image.open(image)
        im.save("temporary_badge.png", "PNG")
        s = self.bot.reddit.subreddit("NUFC")
        s.stylesheet.upload('temp', "temporary_badge.png")
        s.stylesheet.update(s.stylesheet().stylesheet, reason="Update temporary badge image")

    @commands.command(invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def sidebar(self, ctx, *, caption=None):
        """ Force a sidebar update, or use sidebar manual """
        if caption == "manual":  # Obsolete method.
            caption = ""
    
        async with ctx.typing():
            # Check if message has an attachment, for the new sidebar image.
            if caption is not None:
                await self.bot.loop.run_in_executor(None, self.edit_caption, caption)
        
            if ctx.message.attachments:
                s = self.bot.reddit.subreddit("NUFC")
                await ctx.message.attachments[0].save("sidebar.png")
                await self.bot.loop.run_in_executor(s.stylesheet.upload('sidebar', "sidebar.png"))
                style = s.stylesheet().stylesheet
                s.stylesheet.update(style, reason=f"{ctx.author.name} Updated sidebar image via discord.")
        
            # Build
            markdown = await self.make_sidebar()

            # Post
            await self.bot.loop.run_in_executor(None, self.post_sidebar, markdown, 'NUFC')
            
            # Embed.
            e = discord.Embed(color=0xff4500)
            th = "http://vignette2.wikia.nocookie.net/valkyriecrusade/images/b/b5/Reddit-The-Official-App-Icon.png"
            e.set_author(icon_url=th, name="Sidebar updater")
            e.description = f"Sidebar for http://www.reddit.com/r/NUFC updated."
            e.timestamp = datetime.datetime.now()
            await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(Sidebar(bot))
