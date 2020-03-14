from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from ext.utils import embed_utils
from io import BytesIO
from lxml import html
import urllib.parse
import datetime
import aiohttp
import discord
import typing
import json

from ext.utils import selenium_driver, transfer_tools, image_utils
from importlib import reload

reload(selenium_driver)
reload(transfer_tools)
reload(image_utils)


class Fixture:
    def __init__(self, time: typing.Union[str, datetime.datetime], home: str, away: str, **kwargs):
        self.time = time
        self.home = home
        self.away = away
        self.__dict__.update(kwargs)
    
    @property
    def formatted_time(self):
        if isinstance(self.time, datetime.datetime):
            if self.time < datetime.datetime.now():  # in the past -> result
                return self.time.strftime('%a %d %b')
            else:
                return self.time.strftime('%a %d %b %H:%M')
        else:
            return self.time
    
    def get_badge(self, driver, team) -> BytesIO:
        xp = f'.//div[contains(@class, tlogo-{team})]//img'
        badge = selenium_driver.get_image(driver, self.url, xpath=xp, failure_message="Badge not found.")
        return badge
    
    def bracket(self, driver) -> BytesIO:
        xp = './/div[@class="overview"]'
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]'),
                  (By.XPATH, './/div[@class="adsenvelope"]'), (By.XPATH, './/div[contains(@class, "rollbar")]')]
        script = "var element = document.getElementsByClassName('overview')[0];" \
                 "element.style.position = 'fixed';element.style.backgroundColor = '#ddd';" \
                 "element.style.zIndex = '999';"
        image = selenium_driver.get_image(driver, self.url + "#draw", xpath=xp, clicks=clicks, delete=delete,
                                          script=script, failure_message="Unable to find bracket for that competition")
        return image
    
    def table(self, driver) -> BytesIO:
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]'),
                  (By.XPATH, './/div[@class="box_over_content"]')]
        err = "No table found for this league."
        xp = './/div[@class="table__wrapper"]'
        
        image = selenium_driver.get_image(driver, self.url + "#standings;table;overall", xp, delete=delete,
                                          failure_message=err)
        return image
    
    def stats_markdown(self, driver) -> str:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = ".//div[@class='statBox']"
        element = selenium_driver.get_element(driver, self.url + "#match-statistics;0", xp, delete=delete)
        print(element.inner_html)
        # TODO: Finish.
        markdown = "# Not implemented yet."
        return markdown
    
    def stats_image(self, driver) -> BytesIO:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = ".//div[@class='statBox']"
        image = selenium_driver.get_image(driver, self.url + "#match-statistics;0", xp, delete=delete,
                                          failure_message="Unable to find live stats for this match.")
        return image
    
    def formation(self, driver) -> BytesIO:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = './/div[@id="lineups-content"]'
        image = selenium_driver.get_image(driver, self.url + "#lineups;1", xp, delete=delete,
                                          failure_message="Unable to find formations for this match")
        return image
    
    def summary(self, driver) -> BytesIO:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = ".//div[@id='summary-content']"
        image = selenium_driver.get_image(driver, self.url + "#match-summary", xp, delete=delete,
                                          failure_message="Unable to find summary for this match")
        return image
    
    # For reddit.
    @property
    def top_bar(self):
        return f"> [{self.home}]({self.home_subreddit}) [{self.score}]({self.url}) [{self.away}]({self.away_subreddit})"
    
    @property
    def score(self):
        if self.score_home is not None:
            return f"{self.score_home} - {self.score_away}"
        return "vs"
    
    @property
    def sidebar_markdown(self):
        return f"{self.formatted_time} | " \
               f"[{self.short_home} {self.score} {self.short_away}]({self.url})\n"
    
    # For discord.
    @property
    def full_league(self) -> str:
        return f"{self.country.upper()}: {self.league}"
    
    @property
    def formatted_score(self) -> str:
        if self.score_home is not None and self.score_home != "-":
            # Embolden Winner.
            if self.score_home > self.score_away:
                return f"**{self.home} {self.score_home}** - {self.score_away} {self.away}"
            elif self.score_home < self.score_away:
                return f"{self.home} {self.score_home} - **{self.score_away} {self.away}**"
            else:
                return f"{self.home} {self.score_home} - {self.score_away} {self.away}"
        else:
            return f"{self.home} vs {self.away}"
    
    @property
    def state_colour(self) -> typing.Tuple:
        if "Half Time" in self.time:
            return "🟡", 0xFFFF00  # Yellow
        
        if "+" in self.time:
            return "🟣", 0x9932CC  # Purple
        
        if self.state == "live":
            return "🟢", 0x0F9D58  # Green
        
        if self.state == "fin":
            return "🔵", 0x4285F4  # Blue
        
        if "Postponed" in self.time or "Cancelled" in self.time:
            return "🔴", 0xFF0000  # Red
        
        return "⚫", 0x010101  # Black
    
    @property
    def emoji_time(self):
        time = "FT" if self.state == "fin" else self.time
        return f"`{self.state_colour[0]} {time}`"
    
    @property
    def live_score_text(self) -> str:
        home_cards = f"{self.home_attrs}" if self.home_attrs is not None else ""
        away_cards = f"{self.away_attrs}" if self.away_attrs is not None else ""
        return f"{self.emoji_time} {home_cards} {self.formatted_score} {away_cards}"
    
    @property
    def live_score_embed_row(self) -> str:
        return f"[{self.live_score_text}]({self.url})"
    
    @property
    def base_embed(self) -> discord.Embed:
        e = discord.Embed()
        e.set_author(name=f"≡ {self.home} {self.score} {self.away} ({self.time})")
        e.url = self.url
        e.title = f"**{self.country}**: {self.league}"
        e.timestamp = datetime.datetime.now()
        
        if self.time == "Postponed":
            e.description = "This match has been postponed."
        
        e.colour = self.state_colour[1]
        try:
            h, m = self.time.split(':')
            now = datetime.datetime.now()
            when = datetime.datetime.now().replace(hour=int(h), minute=int(m))
            x = when - now
            e.set_footer(text=f"Kickoff in {x}")
            e.timestamp = when
        except ValueError:
            pass
        return e
    
    @property
    def to_embed_row(self) -> str:
        tv = '📺' if hasattr(self, "is_televised") and self.is_televised else ""
        
        if hasattr(self, "url"):
            return f"`{self.formatted_time}:` [{self.formatted_score}{tv}]({self.url})"
        else:
            return f"`{self.formatted_time}:` {self.formatted_score} {tv}"


class Player:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
    @property
    def player_embed_row(self) -> str:
        return f"`{str(self.number).rjust(2)}`: {self.flag} [{self.name}]({self.link}) {self.position}{self.injury}"
    
    @property
    def injury_embed_row(self) -> str:
        return f"{self.flag} [{self.name}]({self.link}) ({self.position}): {self.injury}"
    
    @property
    def scorer_embed_row(self) -> str:
        return f"{self.flag} [{self.name}]({self.link}) {self.goals} in {self.apps} appearances"
    
    @property
    def scorer_embed_row_team(self) -> str:
        return f"{self.flag} [{self.name}]({self.link}) ({self.team}) {self.goals} Goals, {self.assists} Assists"


class FlashScoreSearchResult:
    def __init__(self, **kwargs):
        self.logo_url = None
        self.__dict__.update(**kwargs)
    
    def fetch_logo(self, driver):
        logo = driver.find_element_by_xpath('.//div[contains(@class,"logo")]')
        if logo != "none":
            logo = logo.value_of_css_property('background-image')
            self.logo_url = logo.strip("url(").strip(")").strip('"')
    
    @property
    async def base_embed(self) -> discord.Embed:
        e = discord.Embed()
        
        if isinstance(self, Team):
            e.title = self.title.split('(')[0]
        else:
            try:
                ctry, league = self.title.split(': ')
                e.title = f"{league} ({ctry.title()})"
            except ValueError:
                pass
        
        if self.logo_url is not None:
            logo = "http://www.flashscore.com/res/image/data/" + self.logo_url
            e.colour = await embed_utils.get_colour(logo)
            e.set_thumbnail(url=logo)
        e.url = self.link
        e.timestamp = datetime.datetime.now()
        return e
    
    def fetch_fixtures(self, driver, subpage) -> typing.List[Fixture]:
        link = self.link + subpage
        src = selenium_driver.get_html(driver, link, './/div[@class="sportName soccer"]')
        
        # Ugly, but, whatever.
        try:
            logo = driver.find_element_by_xpath('.//div[contains(@class,"logo")]')
            if logo != "none":
                logo = logo.value_of_css_property('background-image')
                self.logo_url = logo.strip("url(").strip(")").strip('"')
        except NoSuchElementException:
            pass
        
        tree = html.fromstring(src)
        fixture_rows = tree.xpath('.//div[contains(@class,"sportName soccer")]/div')
        
        league, country = None, None
        fixtures = []
        for i in fixture_rows:
            try:
                fixture_id = i.xpath("./@id")[0].split("_")[-1]
                url = "http://www.flashscore.com/match/" + fixture_id
            except IndexError:
                cls = i.xpath('./@class')
                # This (might be) a header row.
                if "event__header" in str(cls):
                    country, league = i.xpath('.//div[contains(@class, "event__title")]//text()')
                    league = league.split(' - ')[0]
                continue
            
            time = "".join(i.xpath('.//div[@class="event__time"]//text()')).strip("Pen").strip('AET')
            if not time:
                time = "?"
            elif "Postp" in time:  # Should be dd.mm hh:mm or dd.mm.yyyy
                time = "🚫 Postponed "
            else:
                try:
                    time = datetime.datetime.strptime(time, '%d.%m.%Y')
                except ValueError:
                    dtn = datetime.datetime.now()
                    try:
                        time = datetime.datetime.strptime(f"{dtn.year}.{time}", '%Y.%d.%m. %H:%M')
                    except ValueError:
                        time = datetime.datetime.strptime(f"{dtn.year}.{dtn.day}.{dtn.month}.{time}", '%Y.%d.%m.%H:%M')
            
            is_televised = True if i.xpath(".//div[contains(@class,'tv')]") else False
            
            # score
            try:
                score_home, score_away = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
            except ValueError:
                score_home, score_away = None, None
            else:
                score_home = int(score_home.strip())
                score_away = int(score_away.strip())
            
            home, away = i.xpath('.//div[contains(@class,"event__participant")]/text()')
            fixture = Fixture(time, home.strip(), away.strip(), score_home=score_home, score_away=score_away,
                              is_televised=is_televised,
                              country=country.strip(), league=league.strip(), url=url)
            fixtures.append(fixture)
        return fixtures


class Competition(FlashScoreSearchResult):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def link(self):
        if hasattr(self, 'override'):
            return self.override
        # Example league URL: https://www.flashscore.com/football/england/premier-league/
        ctry = self.country_name.lower().replace(' ', '-')
        return f"https://www.flashscore.com/soccer/{ctry}/{self.url}"
    
    def table(self, driver) -> BytesIO:
        xp = './/div[@class="table__wrapper"]'
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]'),
                  (By.XPATH, './/div[@class="box_over_content"]')]
        err = f"No table found on {self.link}"
        image = selenium_driver.get_image(driver, self.link + "/standings/", xp, err, clicks=clicks, delete=delete)
        self.fetch_logo(driver)
        return image
    
    def bracket(self, driver) -> BytesIO:
        url = self.link + "/draw/"
        xp = './/div[@id="box-table-type--1"]'
        multi = (By.PARTIAL_LINK_TEXT, 'scroll right »')
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        delete = [(By.XPATH, './/div[@class="seoAdWrapper"]'), (By.XPATH, './/div[@class="banner--sticky"]')]
        script = "document.getElementsByClassName('playoff-scroll-button')[0].style.display = 'none';" \
                 "document.getElementsByClassName('playoff-scroll-button')[1].style.display = 'none';"
        captures = selenium_driver.get_image(driver, url, xpath=xp, clicks=clicks, delete=delete,
                                             multi_capture=(multi, script),
                                             failure_message="Unable to find a bracket for that competition")
        self.fetch_logo(driver)  # For base_embed.
        
        return image_utils.stitch(captures)
    
    def scorers(self, driver) -> typing.List[Player]:
        xp = ".//div[@class='tabs__group']"
        clicks = [(By.ID, "tabitem-top_scorers")]
        src = selenium_driver.get_html(driver, self.link + "/standings", xp, clicks=clicks)
        
        tree = html.fromstring(src)
        rows = tree.xpath('.//div[@id="table-type-10"]//div[contains(@class,"table__row")]')
        
        players = []
        for i in rows:
            items = i.xpath('.//text()')
            items = [i.strip() for i in items if i.strip()]
            uri = "".join(i.xpath(".//span[@class='team_name_span']//a/@onclick")).split("'")
            
            try:
                tm_url = "http://www.flashscore.com/" + uri[3]
            except IndexError:
                tm_url = ""
            try:
                p_url = "http://www.flashscore.com/" + uri[1]
            except IndexError:
                p_url = ""
            
            rank, name, tm, goals, assists = items
            
            country = "".join(i.xpath('.//span[contains(@class,"flag")]/@title')).strip()
            flag = transfer_tools.get_flag(country)
            players.append(Player(rank=rank, flag=flag, name=name, link=p_url, team=tm, team_link=tm_url,
                                  goals=int(goals), assists=assists))
        self.fetch_logo(driver)
        return players


# TODO: Double Inheritance via DB lookup?
class Team(FlashScoreSearchResult):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @classmethod
    async def by_id(cls, qry, team_id):
        # example id: p6ahwuwJ
        # example qry: newcastle
        qry = qry.replace("'", "")  # For some reason, ' completely breaks FS search, and people keep doing it?
        qry = urllib.parse.quote(qry)
        async with aiohttp.ClientSession() as cs:
            # One day we could probably expand upon this if we figure out what the other variables are.
            async with cs.get(f"https://s.flashscore.com/search/?q={qry}&l=1&s=1&f=1%3B1&pid=2&sid=1") as resp:
                res = await resp.text()
        
        # Un-fuck FS JSON reply.
        res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
        res = json.loads(res)
        for i in res['results']:
            if i['id'] == team_id:
                return cls(**i)
    
    @property
    def link(self):
        if hasattr(self, 'override'):
            return self.override
        # Example Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
        return f"https://www.flashscore.com/team/{self.url}/{self.id}"
    
    def players(self, driver, tab=0) -> typing.List[Player]:
        delete = [(By.XPATH, './/div[@id="lsid-window-mask"]')]
        xp = './/div[contains(@class,"playerTable")]'
        
        src = selenium_driver.get_html(driver, self.link + "/squad", xp, delete=delete)
        tree = html.fromstring(src)
        tab += 1  # tab is Indexed at 0 but xpath indexes from [1]
        rows = tree.xpath(f'.//div[contains(@class, "playerTable")][{tab}]//div[contains(@class,"profileTable__row")]')
        
        players = []
        position = ""
        for i in rows:
            pos = "".join(i.xpath('./text()')).strip()
            if pos:  # The way the data is structured contains a header row with the player's position.
                try:
                    position = pos.strip('s')
                except IndexError:
                    position = pos
                continue  # There will not be additional data.
            
            name = "".join(i.xpath('.//div[contains(@class,"")]/a/text()'))
            try:  # Name comes in reverse order.
                player_split = name.split(' ', 1)
                name = f"{player_split[1]} {player_split[0]}"
            except IndexError:
                pass
            
            country = "".join(i.xpath('.//span[contains(@class,"flag")]/@title'))
            flag = transfer_tools.get_flag(country)
            number = "".join(i.xpath('.//div[@class="tableTeam__squadNumber"]/text()'))
            try:
                age, apps, g, y, r = i.xpath(
                    './/div[@class="playerTable__icons playerTable__icons--squad"]//div/text()')
            except ValueError:
                age = "".join(i.xpath('.//div[@class="playerTable__icons playerTable__icons--squad"]//div/text()'))
                apps = g = y = r = 0
            injury = "".join(i.xpath('.//span[contains(@class,"absence injury")]/@title'))
            if injury:
                injury = f"<:injury:682714608972464187> " + injury  # I really shouldn't hard code emojis.
            
            link = "".join(i.xpath('.//div[contains(@class,"")]/a/@href'))
            link = f"http://www.flashscore.com{link}" if link else ""
            
            try:
                number = int(number)
            except ValueError:
                number = 00
            
            pl = Player(name=name, number=number, country=country, link=link, position=position,
                        age=age, apps=apps, goals=int(g), yellows=y, reds=r, injury=injury, flag=flag)
            players.append(pl)
        return players
    
    def player_competitions(self, driver) -> typing.List[str]:
        xp = './/div[contains(@class, "subTabs")]'
        src = selenium_driver.get_html(driver, self.link + '/squad', xp)
        tree = html.fromstring(src)
        options = tree.xpath(xp + "/div/text()")
        options = [i.strip() for i in options]
        return options
    
    def most_recent_game(self, driver) -> Fixture:
        results = self.fetch_fixtures(driver, "/results")
        return results[0]
    
    def next_fixture(self, driver) -> typing.List[Fixture]:
        fixtures = self.fetch_fixtures(driver, "")
        competitions = []
        for i in fixtures:
            if i.score_home is not None:
                continue
            if i.full_league not in [x.full_league for x in competitions]:
                competitions.append(i)
        return competitions


class Stadium:
    def __init__(self, url, name, team, league, country, **kwargs):
        self.url = url
        self.name = name.title()
        self.team = team
        self.league = league
        self.country = country
        self.__dict__.update(kwargs)
    
    async def fetch_more(self):
        this = dict()
        async with aiohttp.ClientSession() as cs:
            async with cs.get(self.url) as resp:
                src = await resp.text()
        tree = html.fromstring(src)
        this['image'] = "".join(tree.xpath('.//div[@class="page-img"]/img/@src'))
        # Teams
        old = tree.xpath('.//tr/th[contains(text(), "Former home")]/following-sibling::td')
        home = tree.xpath('.//tr/th[contains(text(), "home to")]/following-sibling::td')
        
        for s in home:
            team_list = []
            links = s.xpath('.//a/@href')
            teams = s.xpath('.//a/text()')
            for x, y in list(zip(teams, links)):
                if "/team/" in y:
                    team_list.append(f"[{x}]({y})")
            this['home'] = team_list
        
        for s in old:
            team_list = []
            links = s.xpath('.//a/@href')
            teams = s.xpath('.//a/text()')
            for x, y in list(zip(teams, links)):
                if "/team/" in y:
                    team_list.append(f"[{x}]({y})")
            this['old'] = team_list
        
        this['map_link'] = "".join(tree.xpath('.//figure/img/@src'))
        this['address'] = "".join(tree.xpath('.//tr/th[contains(text(), "Address")]/following-sibling::td//text()'))
        this['capacity'] = "".join(tree.xpath('.//tr/th[contains(text(), "Capacity")]/following-sibling::td//text()'))
        this['cost'] = "".join(tree.xpath('.//tr/th[contains(text(), "Cost")]/following-sibling::td//text()'))
        this['website'] = "".join(tree.xpath('.//tr/th[contains(text(), "Website")]/following-sibling::td//text()'))
        this['att'] = "".join(
            tree.xpath('.//tr/th[contains(text(), "Record attendance")]/following-sibling::td//text()'))
        return this
    
    @property
    def to_picker_row(self) -> str:
        return f"**{self.name}** ({self.country}: {self.team})"
    
    @property
    async def to_embed(self) -> discord.Embed:
        e = discord.Embed()
        e.set_author(name="FootballGroundMap.com", url="http://www.footballgroundmap.com")
        e.title = self.name
        e.url = self.url
        
        data = await self.fetch_more()
        try:  # Check not ""
            e.colour = await embed_utils.get_colour(self.team_badge)
        except AttributeError:
            pass
        
        if data['image']:
            e.set_image(url=data['image'].replace(' ', '%20'))
        
        if data['home']:
            e.add_field(name="Home to", value=", ".join(data['home']), inline=False)
        
        if data['old']:
            e.add_field(name="Former home to", value=", ".join(data['old']), inline=False)
        
        # Location
        address = "Link to map" if not data['address'] else data['address']
        
        if data['map_link']:
            e.add_field(name="Location", value=f"[{address}]({data['map_link']})")
        elif data['address']:
            e.add_field(name="Location", value=address, inline=False)
        
        # Misc Data.
        e.description = ""
        if data['capacity']:
            e.description += f"Capacity: {data['capacity']}\n"
        if data['att']:
            e.description += f"Record Attendance: {data['att']}\n"
        if data['cost']:
            e.description += f"Cost: {data['cost']}\n"
        if data['website']:
            e.description += f"Website: {data['website']}\n"
        
        return e


# Factory methods.
async def get_stadiums(query) -> typing.List[Stadium]:
    qry = urllib.parse.quote_plus(query)
    async with aiohttp.ClientSession() as cs:
        async with cs.get(f'https://www.footballgroundmap.com/search/{qry}') as resp:
            src = await resp.text()
    
    tree = html.fromstring(src)
    results = tree.xpath(".//div[@class='using-grid'][1]/div[@class='grid']/div")
    stadiums = []
    for i in results:
        team = "".join(i.xpath('.//small/preceding-sibling::a//text()')).title()
        team_badge = i.xpath('.//img/@src')[0]
        ctry_league = i.xpath('.//small/a//text()')
        
        if not ctry_league:
            continue
        country = ctry_league[0]
        try:
            league = ctry_league[1]
        except IndexError:
            league = ""
        
        sub_nodes = i.xpath('.//small/following-sibling::a')
        for s in sub_nodes:
            name = "".join(s.xpath('.//text()')).title()
            link = "".join(s.xpath('./@href'))
            
            if query.lower() not in name.lower() and query.lower() not in team.lower():
                continue  # Filtering.
            
            if not any(c.name == name for c in stadiums) and not any(c.url == link for c in stadiums):
                stadiums.append(Stadium(url=link, name=name, team=team, team_badge=team_badge,
                                        country=country, league=league))
    return stadiums


async def get_fs_results(query) -> typing.List[FlashScoreSearchResult]:
    query = query.replace("'", "")  # For some reason, ' completely breaks FS search, and people keep doing it?
    query = urllib.parse.quote(query)
    async with aiohttp.ClientSession() as cs:
        # One day we could probably expand upon this if we figure out what the other variables are.
        async with cs.get(f"https://s.flashscore.com/search/?q={query}&l=1&s=1&f=1%3B1&pid=2&sid=1") as resp:
            res = await resp.text()
    
    # Un-fuck FS JSON reply.
    res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
    res = json.loads(res)
    filtered = filter(lambda i: i['participant_type_id'] in (0, 1), res['results'])  # discard players.
    return [Team(**i) if i['participant_type_id'] == 1 else Competition(**i) for i in filtered]
