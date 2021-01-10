import discord
from discord.ext import commands
import datetime

import json
from lxml import html

from ext.utils import embed_utils


class Tv(commands.Cog):
	""" Search for live TV matches """
	
	def __init__(self, bot):
		self.bot = bot
		with open('tv.json') as f:
			bot.tv = json.load(f)
	
	async def save_tv(self):
		with await self.bot.configlock:
			with open('tv.json', "w", encoding='utf-8') as f:
				json.dump(self.bot.tv, f, ensure_ascii=True, sort_keys=True, indent=4, separators=(',', ':'))
				
	@commands.command()
	async def tv(self, ctx, *, team: commands.clean_content = None):
		""" Lookup next televised games for a team """
		async with ctx.typing():
			
			em = discord.Embed()
			em.colour = 0x034f76
			em.set_author(name="LiveSoccerTV.com")
			em.description = ""
			
			if team is not None:
				item_list = [i for i in self.bot.tv if team in i.lower()]
				if not item_list:
					return await ctx.reply(f"Could not find a matching team/league for {team}.", mention_author=False)
				matching_teams = [i for i in self.bot.tv if team in i.lower()]
				index = await embed_utils.page_selector(ctx, matching_teams)
				if index is False:
					return
				team = matching_teams[index]
				em.url = self.bot.tv[team]
				em.title = f"Televised Fixtures for {team}"
			else:
				em.url = "http://www.livesoccertv.com/schedules/"
				em.title = f"Today's Televised Matches"		

			tvlist = []
			async with self.bot.session.get(em.url) as resp:
				if resp.status != 200:
					return await ctx.reply(f"🚫 <{em.url}> returned a HTTP {resp.status} error.", mention_author=False)
				tree = html.fromstring(await resp.text())
				
				match_column = 3 if not team else 5
				
				for i in tree.xpath(".//table[@class='schedules'][1]//tr"):
					# Discard finished games.
					complete = "".join(i.xpath('.//td[@class="livecell"]//span/@class')).strip()
					if complete in ["narrow ft", "narrow repeat"]:
						continue
					
					match = "".join(i.xpath(f'.//td[{match_column}]//text()')).strip()
					if not match:
						continue
					ml = i.xpath(f'.//td[{match_column + 1}]//text()')
					
					try:
						link = i.xpath(f'.//td[{match_column + 1}]//a/@href')[-1]
						link = f"http://www.livesoccertv.com/{link}"
					except IndexError:
						link = ""
					
					ml = ", ".join([x.strip() for x in ml if x != "nufcTV" and x.strip() != ""])
					
					if not ml:
						continue
					
					date = "".join(i.xpath('.//td[@class="datecell"]//span/text()')).strip()
					time = "".join(i.xpath('.//td[@class="timecell"]//span/text()')).strip()
					
					if complete != "narrow live":
						# Correct TimeZone offset.
						try:
							time = datetime.datetime.strptime(time, '%H:%M') + datetime.timedelta(hours=5)
							time = datetime.datetime.strftime(time, '%H:%M')
							dt = f"{date} {time}"
						except ValueError as e:
							print("ValueError in tv", e)
							dt = ""
								
					elif not team:
						dt = i.xpath('.//td[@class="timecell"]//span/text()')[-1].strip()
						if dt == "FT":
							continue
						if dt != "HT" and ":" not in dt:
							dt = f"LIVE {dt}'"
					else:
						if date == datetime.datetime.now().strftime("%b %d"):
							dt = time
						else:
							dt = date
					
					tvlist.append(f'`{dt}` [{match}]({link})')
			
			if not tvlist:
				return await ctx.reply(f"No televised matches found, check online at {em.url}", mention_author=False)
			dtn = datetime.datetime.now().strftime("%H:%M")
			
			em.set_footer(text=f"Time now: {dtn} Your Time:")
			em.timestamp = datetime.datetime.now()
			embeds = embed_utils.rows_to_embeds(em, tvlist)
			await embed_utils.paginate(ctx, embeds)


def setup(bot):
	bot.add_cog(Tv(bot))
