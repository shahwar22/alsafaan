from discord.ext import commands
import discord
import asyncio
from lxml import html
from ext.utils import transfer_tools
import datetime

from importlib import reload


# TODO: restructure into ext.utils.football classes.

class TransferLookup(commands.Cog):
    """ Transfer market lookups """

    def __init__(self, bot):
        self.bot = bot
        reload(transfer_tools)

        self.cats = {
            "players": {
                "cat": "players",
                "func": self._player,
                "querystr": "Spieler_page",
                "parser": transfer_tools.parse_players
            },
            "managers": {
                "cat": "Managers",
                "func": self._manager,
                "querystr": "Trainer_page",
                "parser": transfer_tools.parse_managers
            },
            "clubs": {
                "cat": "Clubs",
                "func": self._team,
                "querystr": "Verein_page",
                "parser": transfer_tools.parse_clubs
            },
            "referees": {
                "cat": "referees",
                "func": self._ref,
                "querystr": "Schiedsrichter_page",
                "parser": transfer_tools.parse_refs
            },
            "domestic competitions": {
                "cat": "to competitions",
                "func": self._cup,
                "querystr": "Wettbewerb_page",
                "parser": transfer_tools.parse_leagues
            },
            "international Competitions": {
                "cat": "International Competitions",
                "func": self._int,
                "querystr": "Wettbewerb_page",
                "parser": transfer_tools.parse_int
            },
            "agent": {
                "cat": "Agents",
                "func": self._agent,
                "querystr": "page",
                "parser": transfer_tools.parse_agent
            },
            "Transfers": {
                "cat": "Clubs",
                "func": self._team,
                "querystr": "Verein_page",
                "parser": transfer_tools.parse_clubs,
                "outfunc": self.get_transfers
            },
            "Rumours": {
                "cat": "Clubs",
                "func": self._team,
                "querystr": "Verein_page",
                "parser": transfer_tools.parse_clubs,
                "outfunc": self.get_rumours
            }
        }

    # Base lookup - No Sub-command invoked.
    @commands.group(invoke_without_command=True)
    async def lookup(self, ctx, *, target: commands.clean_content):
        """ Perform a database lookup on transfermarkt """
        p = {"query": target}  # html encode.
        async with self.bot.session.post(f"http://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche",
                                         params=p) as resp:
            if resp.status != 200:
                return await ctx.send(f"HTTP Error connecting to transfermarkt: {resp.status}")
            tree = html.fromstring(await resp.text())

        # Header names, scrape then compare (because they don't follow a pattern.)
        categories = [i.lower() for i in tree.xpath(".//div[@class='table-header']/text()")]

        results = {}
        count = 0
        for i in categories:
            # Just give us the number of matches by replacing non-digit characters.
            try:
                length = [int(n) for n in i if n.isdigit()][0]
            except IndexError:
                continue

            for j in self.cats:
                if j in i:
                    results[count] = (f"{count}: {self.cats[j]['cat'].title()} ({length} found)", self.cats[j]['func'])
                    count += 1

        if not results:
            return await ctx.send(f":no_entry_sign: No results for {target}")
        sortedlist = [i[0] for i in sorted(results.values())]

        # If only one category has results, invoke that search.
        if len(sortedlist) == 1:
            return await ctx.invoke(results[0][1], qry=target)

        e = discord.Embed(url=str(resp.url))
        e.title = "Transfermarkt lookup"
        e.description = "Please type matching ID#```"
        e.description += "\n".join(sortedlist) + "```"
        e.colour = 0x1a3151
        e.set_footer(text=ctx.author)
        e.set_thumbnail(url="http://www.australian-people-records.com/images/Search-A-Person.jpg")

        async with ctx.typing():
            m = await ctx.send(embed=e)

            def check(message):
                if message.author == ctx.author:
                    try:
                        return int(message.content) in results
                    except ValueError:
                        return False

            # Wait for appropriate reaction
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=120)
            except asyncio.TimeoutError:
                try:
                    return await m.clear_reactions()
                except discord.Forbidden:
                    return

        # invoke appropriate subcommand for category selection.
        await m.delete()
        return await ctx.invoke(results[int(msg.content)][1], qry=target)

    @lookup.command(name="player")
    async def _player(self, ctx, *, qry: commands.clean_content):
        """ Lookup a player on transfermarkt """
        await transfer_tools.search(ctx, qry, "players")

    @lookup.command(name="manager", aliases=["staff", "trainer", "trainers", "managers"])
    async def _manager(self, ctx, *, qry: commands.clean_content):
        """ Lookup a manager/trainer/club official on transfermarkt """
        await transfer_tools.search(ctx, qry, "managers")

    @lookup.command(name="team", aliases=["club"])
    async def _team(self, ctx, *, qry: commands.clean_content):
        """ Lookup a team on transfermarkt """
        await transfer_tools.search(ctx, qry, "clubs")

    @lookup.command(name="ref")
    async def _ref(self, ctx, *, qry: commands.clean_content):
        """ Lookup a referee on transfermarkt """
        await transfer_tools.search(ctx, qry, "referees")

    @lookup.command(name="cup", aliases=["domestic"])
    async def _cup(self, ctx, *, qry: commands.clean_content):
        """ Lookup a domestic competition on transfermarkt """
        await transfer_tools.search(ctx, qry, "domestic competitions")

    @lookup.command(name="international", aliases=["int"])
    async def _int(self, ctx, *, qry: commands.clean_content):
        """ Lookup an international competition on transfermarkt """
        await transfer_tools.search(ctx, qry, "International Competitions")

    @lookup.command(name="agent")
    async def _agent(self, ctx, *, qry: commands.clean_content):
        """ Lookup an agent on transfermarkt """
        await transfer_tools.search(ctx, qry, "Agents")

    @commands.command(aliases=["loans"], usage="transfers <team to search for>")
    async def transfers(self, ctx, *, qry: commands.clean_content):
        """ Get this season's transfers for a team on transfermarkt """
        await transfer_tools.search(ctx, qry, "Transfers", special=True)

    @commands.command(name="rumours", aliases=["rumors"])
    async def _rumours(self, ctx, *, qry: commands.clean_content):
        """ Get the latest transfer rumours for a team """
        await transfer_tools.search(ctx, qry, "Rumours", special=True)

    async def get_transfers(self, ctx, e, target):
        e.description = ""
        target = target.replace('startseite', 'transfers')

        # Winter window, Summer window.
        if datetime.datetime.now().month < 7:
            period = "w"
            season_id = datetime.datetime.now().year - 1
        else:
            period = "s"
            season_id = datetime.datetime.now().year
        target = f"{target}/saison_id/{season_id}/pos//detailpos/0/w_s={period}"

        p = {"w_s": period}
        async with self.bot.session.get(target, params=p) as resp:
            if resp.status != 200:
                return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
            tree = html.fromstring(await resp.text())

        e.set_author(name="".join(tree.xpath('.//head/title/text()')), url=target)
        e.set_footer(text=discord.Embed.Empty)
        ignore, intable, outtable = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')

        intable = intable.xpath('.//tbody/tr')
        outtable = outtable.xpath('.//tbody/tr')

        inlist, inloans, outlist, outloans = [], [], [], []

        for i in intable:
            pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
            player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))

            player_link = f"http://transfermarkt.co.uk{player_link}"
            age = "".join(i.xpath('.//td[3]/text()'))
            ppos = "".join(i.xpath('.//td[2]//tr[2]/td/text()'))
            try:
                flag = transfer_tools.get_flag(i.xpath('.//td[4]/img[1]/@title')[0])
            except IndexError:
                flag = ""
            fee = "".join(i.xpath('.//td[6]//text()'))
            if "loan" in fee.lower():
                inloans.append(f"{flag} [{pname}]({player_link}) {ppos}, {age}\n")
                continue
            inlist.append(f"{flag} [{pname}]({player_link}) {ppos}, {age} ({fee})\n")

        for i in outtable:
            pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
            player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
            player_link = f"http://transfermarkt.co.uk{player_link}"
            flag = transfer_tools.get_flag(i.xpath('.//td/img[1]/@title')[1])
            fee = "".join(i.xpath('.//td[6]//text()'))
            if "loan" in fee.lower():
                outloans.append(f"{flag} [{pname}]({player_link}), ")
                continue
            outlist.append(f"{flag} [{pname}]({player_link}), ")

        def write_field(title, input_list):
            output = ""
            for item in input_list:
                if len(item) + len(output) < 1009:
                    output += input_list.pop(item)
                else:
                    output += f"And {len(input_list)} more..."
                    break
            e.add_field(name=title, value=output.strip(","), inline=False)

        for x, y in [("Players in", inlist), ("Loans In", inloans), ("Players out", outlist), ("Loans Out", outloans)]:
            write_field(x, y) if y else ""

        await ctx.send(embed=e)

    async def get_rumours(self, ctx, e, target):
        e.description = ""
        target = target.replace('startseite', 'geruechte')
        async with self.bot.session.get(f"{target}") as resp:
            if resp.status != 200:
                return await ctx.send(f"Error {resp.status} connecting to {resp.url}")
            tree = html.fromstring(await resp.text())
            e.url = str(resp.url)
        e.set_author(name=tree.xpath('.//head/title[1]/text()')[0], url=str(resp.url))
        e.set_footer(text=discord.Embed.Empty)

        rumours = tree.xpath('.//div[@class="large-8 columns"]/div[@class="box"]')[0]
        rumours = rumours.xpath('.//tbody/tr')
        rumorlist = []
        for i in rumours:
            pname = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/text()'))
            if not pname:
                continue
            player_link = "".join(i.xpath('.//td[@class="hauptlink"]/a[@class="spielprofil_tooltip"]/@href'))
            player_link = f"http://transfermarkt.co.uk{player_link}"
            ppos = "".join(i.xpath('.//td[2]//tr[2]/td/text()'))
            mv = "".join(i.xpath('.//td[6]//text()')).strip()
            flag = transfer_tools.get_flag(i.xpath('.//td[3]/img/@title')[0])
            age = "".join(i.xpath('./td[4]/text()')).strip()
            team = "".join(i.xpath('.//td[5]//img/@alt'))
            tlink = "".join(i.xpath('.//td[5]//img/@href'))
            odds = "".join(i.xpath('./td[8]//text()')).strip().replace('&nbsp', '')
            source = "".join(i.xpath('./td[7]//@href'))
            odds = f"[{odds}likely]({source})" if odds != "-" else f"[rumor info]({source})"
            rumorlist.append(f"{flag} **[{pname}]({player_link})** {age}, {ppos} ({mv})\n*[{team}]({tlink})*, {odds}\n")

        output = ""
        count = 0
        if not rumorlist:
            output = "No rumours about new signings found."
        for i in rumorlist:
            if len(i) + len(output) < 1985:
                output += i
            else:
                output += f"And {len(rumorlist) - count} more..."
                break
            count += 1
        e.description = output

        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(TransferLookup(bot))
