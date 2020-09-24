import asyncio
import discord
from discord.ext import commands
import datetime

import json
import aiohttp
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
				
	async def _pick_team(self, ctx, team):
		em = discord.Embed()
		em.colour = 0x034f76
		em.set_author(name="LiveSoccerTV.com")
		em.description = ""
		
		if not team:
			em.url = "http://www.livesoccertv.com/schedules/"
			em.title = f"Today's Televised Matches"
		
		item_list = [i for i in self.bot.tv if team.lower() in i.lower()]
		if not item_list:
			await ctx.send(f"Could not find a matching team/league for {team}.")
			return None
		
		matching_teams = {i for i in self.bot.tv if team.lower() in i.lower()}
		
		index = await embed_utils.page_selector(ctx, matching_teams)
		team = matching_teams[index]
		em.url = self.bot.tv[team]
		em.title = f"Televised Fixtures for {team}"
		return em
	
	@commands.command()
	async def tv(self, ctx, *, team: commands.clean_content = None):
		""" Lookup next televised games for a team """
		async with ctx.typing():
			em = await self._pick_team(ctx, team)
			
			if em is None:
				return
			
			tvlist = []
			async with self.bot.session.get(em.url) as resp:
				if resp.status != 200:
					return await ctx.send(f"🚫 <{em.url}> returned {resp.status}")
				tree = html.fromstring(await resp.text())
				
				matchcol = 3 if not team else 5
				
				for i in tree.xpath(".//table[@class='schedules'][1]//tr"):
					# Discard finished games.
					isdone = "".join(i.xpath('.//td[@class="livecell"]//span/@class')).strip()
					if isdone in ["narrow ft", "narrow repeat"]:
						continue
					
					match = "".join(i.xpath(f'.//td[{matchcol}]//text()')).strip()
					if not match:
						continue
					ml = i.xpath(f'.//td[{matchcol + 1}]//text()')
					
					try:
						link = i.xpath(f'.//td[{matchcol + 1}]//a/@href')[-1]
						link = f"http://www.livesoccertv.com/{link}"
					except IndexError:
						link = ""
					
					ml = ", ".join([x.strip() for x in ml if x != "nufcTV" and x.strip() != ""])
					
					if not ml:
						continue
					
					date = "".join(i.xpath('.//td[@class="datecell"]//span/text()')).strip()
					time = "".join(i.xpath('.//td[@class="timecell"]//span/text()')).strip()
					
					if isdone != "narrow live":
						# Correct TimeZone offset.
						try:
							time = datetime.datetime.strptime(time, '%H:%M') + datetime.timedelta(hours=5)
							time = datetime.datetime.strftime(time, '%H:%M')
							dt = f"{date} {time}"
						except ValueError as e:
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
				return await ctx.send(f"Couldn't find any televised matches happening soon, check online at {em.url}")
			dtn = datetime.datetime.now().strftime("%H:%M")
			
			em.set_footer(text=f"Time now: {dtn} Your Time:")
			em.timestamp = datetime.datetime.now()
			chars = 0
			remain = len(tvlist)
			for x in tvlist:
				if len(x) + + chars < 2000:
					em.description += x + "\n"
					remain -= 1
				chars += len(x) + 5
			
			if remain:
				em.description += f"\n *and {remain} more...*"
			await ctx.send(embed=em)


def setup(bot):
	bot.add_cog(Tv(bot))
