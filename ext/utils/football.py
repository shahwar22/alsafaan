from json import JSONDecodeError

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

FLASH_SCORE_ADS = [(By.XPATH, './/div[@class="seoAdWrapper"]'),
                   (By.XPATH, './/div[@class="banner--sticky"]'),
                   (By.XPATH, './/div[@class="box_over_content"]'),
                   (By.XPATH, './/div[@class="ot-sdk-container"]'),
                   (By.XPATH, './/div[@class="adsenvelope"]'),
                   (By.XPATH, './/div[@id="onetrust-consent-sdk"]'),
                   (By.XPATH, './/div[@id="lsid-window-mask"]'),
                   (By.XPATH, './/div[contains(@class, "isSticky")]'),
                   (By.XPATH, './/div[contains(@class, "rollbar")]'),
                   (By.XPATH, './/div[contains(@id,"box-over-content")]')
                   ]


class Fixture:
    def __init__(self, time: typing.Union[str, datetime.datetime], home: str, away: str, **kwargs):
        self.time = time
        self.home = home
        self.away = away
        
        # Initialise some vars...
        self.score_home = None
        self.score_away = None
        
        # Match Thread Bot specific vars
        self.kickoff = None
        self.referee = None
        self.stadium = None
        self.attendance = None
        self.country = None
        self.league = None
        self.comp_link = None
        self.events = None
        self.penalties_home = None
        self.penalties_away = None
        self.images = None
        self.__dict__.update(kwargs)
        
    def __repr__(self):
        return f"Fixture({self.__dict__})"
    
    def __str__(self):
        if hasattr(self, "url"):
            return f"`{self.formatted_time}:` [{self.bold_score}{self.tv}]({self.url})"
        else:
            return f"`{self.formatted_time}:` {self.bold_score}{self.tv}"
        
    @property
    def tv(self):
        return '📺' if hasattr(self, "is_televised") and self.is_televised else ""

    @classmethod
    def by_id(cls, match_id, driver=None):
        url = "http://www.flashscore.com/match/" + match_id
        src = selenium_driver.get_html(driver, url, xpath=".//div[@class='team spoiler-content']")
        tree = html.fromstring(src)
        
        home = "".join(tree.xpath('.//div[contains(@class, "tname-home")]//a/text()')).strip()
        away = "".join(tree.xpath('.//div[contains(@class, "tname-away")]//a/text()')).strip()
        ko = "".join(tree.xpath(".//div[@id='utime']/text()")).strip()
        ko = datetime.datetime.strptime(ko, "%d.%m.%Y %H:%M")
        
        country_league = "".join(tree.xpath('.//span[@class="description__country"]//text()'))
        comp_link_raw = "".join(tree.xpath('.//span[@class="description__country"]//a/@onclick'))
        country, competition = country_league.split(':')
        country = country.strip()
        competition = competition.strip()
        comp_link = "http://www.flashscore.com" + comp_link_raw.split("'")[1]
        
        return cls(url=url, home=home, away=away, time=ko, kickoff=ko, league=competition, comp_link=comp_link,
                   country=country)

    @property
    def formatted_time(self):
        if isinstance(self.time, datetime.datetime):
            if self.time < datetime.datetime.now():  # in the past -> result
                return self.time.strftime('%a %d %b')
            else:
                return self.time.strftime('%a %d %b %H:%M')
        else:
            return self.time
    
    @property
    def score(self) -> str:
        if self.score_home is not None:
            return f"{self.score_home} - {self.score_away}"
        return "vs"
    
    @property
    def bold_score(self) -> str:
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
    def live_score_text(self) -> str:
        if self.state == "fin":
            self.time = "FT"
        return f"`{self.state_colour[0]}` {self.time} {self.home_cards} {self.bold_score} {self.away_cards}"

    @property
    async def base_embed(self) -> discord.Embed:
        e = discord.Embed()
        # Don't use bold_score, embed author doesn't like it.
        e.title = f"≡ {self.home} {self.score} {self.away}"
        e.url = self.url
        
        e.set_author(name=f"{self.country}: {self.league}")
        if isinstance(self.time, datetime.datetime):
            e.timestamp = self.time
        elif self.time == "Postponed":
            e.description = "This match has been postponed."
    
        e.colour = self.state_colour[1]
        try:
            e.set_footer(text=f"Kickoff in {self.time - datetime.datetime.now()}")
        except (ValueError, AttributeError):
            pass
        return e

    # For discord.
    @property
    def full_league(self) -> str:
        return f"{self.country.upper()}: {self.league}"

    @property
    def state_colour(self) -> typing.Tuple:
        if isinstance(self.time, datetime.datetime):
            return "", discord.Embed.Empty  # Non-live matches
        
        if "Half Time" in self.time:
            return "🟡", 0xFFFF00  # Yellow
    
        if "+" in self.time:
            return "🟣", 0x9932CC  # Purple
        
        if not hasattr(self, "state"):
            return "🔵", 0x4285F4  # Blue
        
        if self.state == "live":
            return "🟢", 0x0F9D58  # Green
    
        if self.state == "fin":
            return "🔵", 0x4285F4  # Blue
    
        if "Postponed" in self.time or "Cancelled" in self.time:
            return "🔴", 0xFF0000  # Red
    
        return "⚫", 0x010101  # Black
    
    def get_badge(self, driver, team) -> BytesIO:
        xp = f'.//div[contains(@class, tlogo-{team})]//img'
        badge = selenium_driver.get_image(driver, self.url, xpath=xp, failure_message="Badge not found.")
        return badge
    
    def bracket(self, driver) -> BytesIO:
        xp = './/div[@class="overview"]'
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        script = "var element = document.getElementsByClassName('overview')[0];" \
                 "element.style.position = 'fixed';element.style.backgroundColor = '#ddd';" \
                 "element.style.zIndex = '999';"
        image = selenium_driver.get_image(driver, self.url + "#draw", xpath=xp, clicks=clicks, delete=FLASH_SCORE_ADS,
                                          script=script, failure_message="Unable to find bracket for that tournament.")
        return image
    
    def table(self, driver) -> BytesIO:
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        err = "No table found for this league."
        xp = './/div[contains(@class, "tableWrapper")]'
        
        image = selenium_driver.get_image(driver, self.url + "#standings;table;overall", xp, delete=FLASH_SCORE_ADS,
                                          clicks=clicks, failure_message=err)
        
        return image
    
    def stats_image(self, driver) -> BytesIO:
        xp = ".//div[@class='statBFox']"
        image = selenium_driver.get_image(driver, self.url + "#match-statistics;0", xp, delete=FLASH_SCORE_ADS,
                                          failure_message="Unable to find live stats for this match.")
        return image
    
    def formation(self, driver) -> BytesIO:
        clicks = [(By.XPATH, './/div[@id="onetrust-accept-btn-handler"]')]
        xp = './/div[@id="lineups-content"]'
        image = selenium_driver.get_image(driver, self.url + "#lineups;1", xp, delete=FLASH_SCORE_ADS, clicks=clicks,
                                          failure_message="Unable to find formations for this match")
        return image
    
    def summary(self, driver) -> BytesIO:
        xp = ".//div[@id='summary-content']"
        image = selenium_driver.get_image(driver, self.url + "#match-summary", xp, delete=FLASH_SCORE_ADS,
                                          failure_message="Unable to find summary for this match")
        return image

    def head_to_head(self, driver) -> typing.Dict:
        xp = ".//div[@id='tab-h2h-overall']"
        element = selenium_driver.get_element(driver, self.url + "#h2h;overall", xp)
        src = element.get_attribute('innerHTML')
        tree = html.fromstring(src)
        
        tables = tree.xpath('.//table')
        games = {}
        for i in tables:
            header = "".join(i.xpath('.//thead//text()')).strip()
            fixtures = i.xpath('.//tbody//tr')
            fx_list = []
            for game in fixtures[:5]:  # Last 5 only.
                game_id = game.xpath('.//@onclick')[0].split('(')[-1].split(',')[0].strip('\'').split('_')[-1]
                url = "http://www.flashscore.com/match/" + game_id
                home, away = game.xpath('.//td[contains(@class, "name")]//text()')
                time = game.xpath('.//span[@class="date"]/text()')[0]
                score_home, score_away = game.xpath('.//span[@class="score"]//text()')[0].split(':')
                country_league = game.xpath('.//td[2]/@title')[0]
                country, league = country_league.split('(')
                league = league.strip(')')
                fx = Fixture(home=home, away=away, time=time, score_home=int(score_home), score_away=int(score_away),
                             country=country, league=league, url=url)
                fx_list.append(fx)
            games.update({header: fx_list})
        return games
    
    def refresh(self, driver):  # This is a very intensive, full lookup, reserved for the match thread bot.
        xp = ".//div[@id='utime']"
        src = selenium_driver.get_html(driver, self.url, xp)
        tree = html.fromstring(src)
        
        # Some of these will only need updating once per match
        if self.kickoff is None:
            ko = "".join(tree.xpath(".//div[@id='utime']/text()"))
            ko = datetime.datetime.strptime(ko, "%d.%m.%Y %H:%M")
            self.kickoff = ko
        
        if self.referee is None:
            text = tree.xpath('.//div[@class="content"]//text()')
            ref = "".join([i for i in text if "referee" in i.lower()]).strip().replace('Referee:', '')
            venue = "".join([i for i in text if "venue" in i.lower()]).strip().replace('Venue:', '')
            
            self.referee = ref
            self.stadium = venue
            
        if self.country is None or self.league is None:
            country_league = "".join(tree.xpath('.//span[@class="description__country"]//text()'))
            comp_link_raw = "".join(tree.xpath('.//span[@class="description__country"]//a/@onclick'))
            country, competition = country_league.split(':')
            country = country.strip()
            competition = competition.strip()
            comp_link = "http://www.flashscore.com" + comp_link_raw.split("'")[1]
            self.country = country
            self.league = competition
            self.comp_link = comp_link
        
        # These must always be updated.
        scores = tree.xpath('.//div[@class="current-result"]//span[@class="scoreboard"]/text()')
        self.score_home = scores[0]
        self.score_away = scores[1]
        
        incidents = tree.xpath('.//div[@class="detailMS"]/div')
        events = []
        for i in incidents:
            if "Header" in i.attrib['class']:
                parts = [x.strip() for x in i.xpath('.//text()')]
                events.append(("header", parts))
                if "Penalties" in parts:
                    self.penalties_home = parts[1]
                    self.penalties_away = parts[3]
            else:
                team = i.attrib['class']
                team = "home" if "home" in team else "away"
                
                time = ""
                sub_on, sub_off = "", ""
                note = ""
                event_type = None
                player = ""
                event_desc = ""
                
                for node in i.xpath("./*"):
                    node_type = node.attrib['class']
                    if "empty" in node_type:
                        continue  # No events in half.
                    
                    # Time box
                    if "time-box" in node_type:
                        time = "".join(node.xpath('.//text()')).strip()
                    
                    # Substitution info
                    elif node_type == "icon-box substitution-in":
                        pass  # We handle the other two instead.
                    
                    elif node_type == "substitution-in-name":
                        sub_on = ''.join(node.xpath('.//a/text()')).strip()
                        
                    elif node_type == "substitution-out-name":
                        sub_off = ''.join(node.xpath('.//a/text()')).strip()
                    
                    # Disciplinary actions
                    elif "y-card" in node_type:
                        event_type = "booking"
                        
                    elif "yr-card" in node_type:
                        event_type = "2yellow"
                    
                    elif "r-card" in node_type:
                        event_type = "dismissal"
                        
                    elif "subincident-name" in node_type:
                        note = "".join(node.xpath('.//text()'))
                        
                    elif "note-name" in node_type:
                        note = "".join(node.xpath('.//text()'))
                        
                    # Goals & Penalties
                    elif "penalty-missed" in node_type:
                        event_desc = node.attrib['title']
                        event_type = "Penalty miss"
                        
                    elif "soccer-ball" in node_type:
                        event_desc = node.attrib['title'].replace('<br />', " ")
                        event_type = "Goal"
                    
                    # Player info
                    elif node_type == "participant-name":
                        player = ''.join(node.xpath('.//a/text()'))
                        
                    else:
                        print("unhandled node", node_type, team, time, note, event_desc)
                if sub_on:
                    events.append(("Sub", time, team, (sub_on, sub_off)))
                else:
                    events.append((event_type, time, team, player, note, event_desc))
            
        self.events = events
        
        # TODO: Fetching images'
        self.images = tree.xpath('.//div[@class="highlight-photo"]//img/@src')
        
        # TODO: Fetching players & formation'
        # TODO: fetching statistics'

        # TODO: fetching table'
        
    
class Player:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


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
            try:
                e.title = self.title.split('(')[0]
            except AttributeError:
                pass
        else:
            try:
                ctry, league = self.title.split(': ')
                e.title = f"{league} ({ctry.title()})"
            except (ValueError, AttributeError):
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

            # score
            try:
                score_home, score_away = i.xpath('.//div[contains(@class,"event__scores")]/span/text()')
            except ValueError:
                score_home, score_away = None, None
            else:
                score_home = int(score_home.strip())
                score_away = int(score_away.strip())

            home, away = i.xpath('.//div[contains(@class,"event__participant")]/text()')

            time = "".join(i.xpath('.//div[@class="event__time"]//text()'))
            
            for x in ["Pen", 'AET', 'FRO', 'WO']:
                time = time.replace(x, '')
                
            if not time:
                time = "?"
            elif "Postp" in time:  # Should be dd.mm hh:mm or dd.mm.yyyy
                time = "🚫 Postponed "
            elif "Awrd" in time:
                try:
                    time = datetime.datetime.strptime(time.strip('Awrd'), '%d.%m.%Y')
                except ValueError:
                    time = datetime.datetime.strptime(time.strip('Awrd'), '%d.%m. %H:%M')
                time = time.strftime("%d/%m/%Y")
                time = f"{time} 🚫 FF"  # Forfeit
            else:
                try:
                    time = datetime.datetime.strptime(time, '%d.%m.%Y')
                    if time.year != datetime.datetime.now().year:
                        time = time.strftime("%d/%m/%Y")
                except ValueError:
                    dtn = datetime.datetime.now()
                    try:
                        time = datetime.datetime.strptime(f"{dtn.year}.{time}", '%Y.%d.%m. %H:%M')
                    except ValueError:
                        time = datetime.datetime.strptime(f"{dtn.year}.{dtn.day}.{dtn.month}.{time}", '%Y.%d.%m.%H:%M')
            
            is_televised = True if i.xpath(".//div[contains(@class,'tv')]") else False
            fixture = Fixture(time, home.strip(), away.strip(), score_home=score_home, score_away=score_away,
                              is_televised=is_televised,
                              country=country.strip(), league=league.strip(), url=url)
            fixtures.append(fixture)

        return fixtures


class Competition(FlashScoreSearchResult):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @classmethod
    def by_id(cls, comp_id, driver=None):
        url = "http://flashscore.com/?r=2:" + comp_id
        
        src = selenium_driver.get_html(driver, url, xpath=".//div[@class='team spoiler-content']")
        url = selenium_driver.get_target_page(driver, url)
        tree = html.fromstring(src)
        
        country = tree.xpath('.//h2[@class="tournament"]/a[2]//text()')[0].strip()
        league = tree.xpath('.//div[@class="teamHeader__name"]//text()')[0].strip()
        title = country.upper() + " " + league
        
        return cls(url=url, title=title, country_name=country, league=league)

    @classmethod
    def by_link(cls, link, driver=None):
        src = selenium_driver.get_html(driver, link, xpath=".//div[@class='team spoiler-content']")
        tree = html.fromstring(src)
    
        country = tree.xpath('.//h2[@class="tournament"]/a[2]//text()')[0].strip()
        league = tree.xpath('.//div[@class="teamHeader__name"]//text()')[0].strip()
        title = country.upper() + " " + league
        return cls(url=link, title=title, country_name=country, league=league)
    
    @property
    def link(self):
        if "https://" in self.url:
            return self.url
        ctry = self.country_name.lower().replace(' ', '-')
        return f"https://www.flashscore.com/soccer/{ctry}/{self.url}"
    
    def table(self, driver) -> BytesIO:
        xp = './/div[contains(@class, "tableWrapper")]/parent::div'
        table_page = self.link + "/standings/"
        
        err = f"No table found on {table_page}"
        image = selenium_driver.get_image(driver, table_page, xp, err, delete=FLASH_SCORE_ADS)
        self.fetch_logo(driver)
        return image
    
    def bracket(self, driver) -> BytesIO:
        url = self.link + "/draw/"
        xp = './/div[@id="box-table-type--1"]'
        multi = (By.PARTIAL_LINK_TEXT, 'scroll right »')
        clicks = [(By.XPATH, ".//span[@class='button cookie-law-accept']")]
        script = "document.getElementsByClassName('playoff-scroll-button')[0].style.display = 'none';" \
                 "document.getElementsByClassName('playoff-scroll-button')[1].style.display = 'none';"
        captures = selenium_driver.get_image(driver, url, xpath=xp, clicks=clicks, delete=FLASH_SCORE_ADS,
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


class Team(FlashScoreSearchResult):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @classmethod
    def by_id(cls, team_id, driver=None):
        url = "http://flashscore.com/?r=3:" + team_id
        url = selenium_driver.get_target_page(driver, url)
        return cls(url=url, id=team_id)

    @property
    def link(self):
        if "://" in self.url:
            return self.url
        # Example Team URL: https://www.flashscore.com/team/thailand-stars/jLsL0hAF/
        return f"https://www.flashscore.com/team/{self.url}/{self.id}"
    
    def players(self, driver, tab=0) -> typing.List[Player]:
        xp = './/div[contains(@class,"playerTable")]'
        src = selenium_driver.get_html(driver, self.link + "/squad", xp)
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


class Goal:
    def __init__(self, embed, home, away, competition, title, **kwargs):
        self.embed = embed
        self.home = home
        self.away = away
        self.competition = competition
        self.title = title
        self.__dict__.update(kwargs)
    
    @property
    def fixture(self) -> str:
        return f"{self.home} vs {self.away}"
        
    @property
    def clean_link(self) -> str:
        return self.embed.split('src=\'')[1].split("?s=2")[0].replace('\\', '')
    
    @property
    def markdown_link(self) -> str:
        return f"[{self.title}]({self.clean_link})"
        

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
        
        try:
            e.add_field(name="Former home to", value=", ".join(data['old']), inline=False)
        except KeyError:
            pass
        
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
async def get_goals() -> typing.List[Goal]:
    goals = []
    async with aiohttp.ClientSession() as cs:
        async with cs.get('https://www.scorebat.com/video-api/v1/') as resp:
            data = await resp.json()
            
        for match in data:
            for video in match['videos']:
                if "highlights" not in video['title'].lower():
                    this_goal = Goal(embed=video['embed'], home=match['side1']['name'], away=match['side2']['name'],
                                     competition=match['competition']['name'], title=video['title'])
                    goals.append(this_goal)
    return goals


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
    qry_debug = query

    for r in ["'", "[", "]", "#", '<', '>']:  # Fuckin morons.
        query = query.replace(r, "")
        
    query = urllib.parse.quote(query)
    async with aiohttp.ClientSession() as cs:
        # One day we could probably expand upon this if we figure out what the other variables are.
        async with cs.get(f"https://s.flashscore.com/search/?q={query}&l=1&s=1&f=1%3B1&pid=2&sid=1") as resp:
            res = await resp.text()
            assert resp.status == 200, f"Server returned a {resp.status} error, please try again later."
    
    # Un-fuck FS JSON reply.
    res = res.lstrip('cjs.search.jsonpCallback(').rstrip(");")
    try:
        res = json.loads(res)
    except JSONDecodeError:
        print(f"Json error attempting to decode query: {query}\n", res, f"\nString that broke it: {qry_debug}")
        raise AssertionError('Something you typed broke the search query. Please only specify a team name.')
    
    filtered = [i for i in res['results'] if i['participant_type_id'] in (0, 1)]
    return [Team(**i) if i['participant_type_id'] == 1 else Competition(**i) for i in filtered]
