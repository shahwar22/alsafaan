from ext.utils import transfer_tools, embed_utils
from discord.ext import commands, tasks
from collections import defaultdict
from importlib import reload
from lxml import html
import typing
import discord

from ext.utils.embed_utils import paginate


class Transfers(commands.Cog):
    """ Create and configure Transfer Ticker channels"""
    
    async def imgurify(self, img_url):
        # upload image to imgur
        d = {"image": img_url}
        h = {'Authorization': f'Client-ID {self.bot.credentials["Imgur"]["Authorization"]}'}
        async with self.bot.session.post("https://api.imgur.com/3/image", data=d, headers=h) as resp:
            res = await resp.json()
        try:
            return res['data']['link']
        except KeyError:
            return None
    
    def __init__(self, bot):
        self.bot = bot
        self.parsed = []
        self.bot.transfer_ticker = self.transfer_ticker.start()
        self.cache = defaultdict(set)
        for i in [embed_utils, transfer_tools]:
            reload(i)
    
    def cog_unload(self):
        self.transfer_ticker.cancel()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute("""DELETE FROM transfers_channels WHERE guild_id = $1""", guild.id)
        await self.bot.db.release(connection)
        await self.update_cache()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute("""DELETE FROM transfers_channels WHERE channel_id = $1""", channel.id)
        await self.bot.db.release(connection)
        await self.update_cache()
    
    async def update_cache(self):
        # Grab most recent data.
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            records = await connection.fetch("""
            SELECT guild_id, transfers_channels.channel_id, short_mode, item, type, alias
            FROM transfers_channels
            LEFT OUTER JOIN transfers_whitelists
            ON transfers_channels.channel_id = transfers_whitelists.channel_id""")
        await self.bot.db.release(connection)
        
        # Clear out our cache.
        self.cache.clear()
        
        # Repopulate.
        for r in records:
            if self.bot.get_channel(r['channel_id']) is None:
                print("Transfers Warning on:", r["channel_id"])
                continue
            
            key = (r["guild_id"], r["channel_id"], r["short_mode"])
            
            if r["item"] is None:  # Assure addition.
                self.cache[key] = set()
                continue
            self.cache[key].add((r["item"], r["type"], r["alias"]))
    
    @tasks.loop(seconds=15)
    async def transfer_ticker(self):
        src = 'https://www.transfermarkt.co.uk/transfers/neuestetransfers/statistik'
        flags = "?minMarktwert=1"
        async with self.bot.session.get(src + flags) as resp:
            if resp.status != 200:
                return
            tree = html.fromstring(await resp.text())
        
        skip_output = True if not self.parsed else False
        # skip_output = False   
        for i in tree.xpath('.//div[@class="responsive-table"]/div/table/tbody/tr'):
            player_name = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/text()')).strip()
            
            # DEBUG_RESTART
            # if "Hashimoto" in player_name:
            #    skip_output = True
            
            if not player_name or player_name in self.parsed:
                continue  # skip when duplicate / void.
            else:
                self.parsed.append(player_name)
            
            # We don't need to output when populating after a restart.
            if skip_output:
                continue
            
            # Player Info
            player_link = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/@href'))
            age = "".join(i.xpath('./td[2]//text()')).strip()
            pos = "".join(i.xpath('./td[1]//tr[2]/td/text()'))
            nat = i.xpath('.//td[3]/img/@title')
            flags = []
            for j in nat:
                flags.append(transfer_tools.get_flag(j))
            # nationality = ", ".join([f'{j[0]} {j[1]}' for j in list(zip(flags,nat))])
            nationality = "".join(flags)
            
            # Leagues & Fee
            new_team = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/text()')).strip()
            new_team_link = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/@href')).strip()
            new_league = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/text()')).strip()
            new_league_link = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/@href')).strip()
            new_league_flag = transfer_tools.get_flag("".join(i.xpath('.//td[5]/table//tr[2]/td//img/@alt')))
            
            old_team = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/text()')).strip()
            old_team_link = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/@href')).strip()
            old_league = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/text()')).strip()
            old_league_link = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/@href')).strip()
            old_league_flag = transfer_tools.get_flag("".join(i.xpath('.//td[4]/table//tr[2]/td//img/@alt')))
            
            # Fix Links
            if "transfermarkt" not in new_team_link:
                new_team_link = "https://www.transfermarkt.co.uk" + new_team_link if new_team_link else ""
            if "transfermarkt" not in new_league_link:
                new_league_link = f"https://www.transfermarkt.co.uk" + new_league_link if new_league_link else ""
            if "transfermarkt" not in old_team_link:
                old_team_link = "https://www.transfermarkt.co.uk" + old_team_link if old_team_link else ""
            if "transfermarkt" not in old_league_link:
                old_league_link = "https://www.transfermarkt.co.uk" + old_league_link if old_league_link else ""
            
            # Markdown.
            new_league_markdown = "" if "None" in new_league else f"{new_league_flag} [{new_league}]({new_league_link})"
            new_team_markdown = f"[{new_team}]({new_team_link})"
            old_league_markdown = "" if "None" in old_league else f"{old_league_flag} [{old_league}]({old_league_link})"
            old_team_markdown = f"[{old_team}]({old_team_link})"
            
            if new_league == old_league:
                move = f"{old_team} to {new_team} ({new_league_flag} {new_league})"
            else:
                move = f"{old_team} ({old_league_flag} {old_league}) to {new_team} ({new_league_flag} {new_league})"
            
            move_info = move.replace(" (None )", "")
            
            fee = "".join(i.xpath('.//td[6]//a/text()'))
            fee_link = "https://www.transfermarkt.co.uk" + "".join(i.xpath('.//td[6]//a/@href'))
            fee_markdown = f"[{fee}]({fee_link})"
            
            e = discord.Embed()
            e.description = ""
            e.colour = 0x1a3151
            e.title = f"{nationality} {player_name} | {age}"
            e.url = f"https://www.transfermarkt.co.uk{player_link}"
            
            e.description = f"{pos}\n"
            e.description += f"**To**: {new_team_markdown} {new_league_markdown}\n"
            e.description += f"**From**: {old_team_markdown} {old_league_markdown}"
            
            if fee:
                e.add_field(name="Reported Fee", value=fee_markdown, inline=False)
            
            # Get picture and re-host on imgur.
            th = "".join(i.xpath('.//td[1]//tr[1]/td[1]/img/@src'))
            th = await self.imgurify(th)
            if th is not None:
                e.set_thumbnail(url=th)
            
            shortstring = f"{player_name} | {fee} | <{fee_link}>\n{move_info}"
            for (guild_id, channel_id, mode), whitelist in self.cache.copy().items():
                ch = self.bot.get_channel(channel_id)
                if ch is None:
                    continue  # rip.
                
                if whitelist:
                    # Iterate through every whitelist item, if there is not a match, we iterate to the next channel.
                    for (item, item_type, alias) in whitelist:
                        if item_type == "league":
                            item = item.replace('startseite', 'transfers').strip()  # Fix for link.
                            if item in new_league_link or item in old_league_link:
                                break
                        else:
                            if item in new_team_link or item in old_team_link:
                                break
                    else:
                        continue
                try:
                    if mode:
                        await ch.send(shortstring)
                    else:
                        await ch.send(embed=e)
                except (discord.Forbidden, discord.HTTPException):
                    pass  # dumb fucks can't set a channel right, server issues.
                except AttributeError:
                    print(f"AttributeError transfer-ticker {channel_id} check for channel deletion.")
    
    @transfer_ticker.before_loop
    async def before_tf_loop(self):
        await self.bot.wait_until_ready()
        await self.update_cache()
    
    async def _pick_channels(self, ctx, channels: typing.List[discord.TextChannel]):
        # Assure guild has transfer channel.
        guild_cache = [i[1] for i in self.cache if ctx.guild.id in i]
        
        if not guild_cache:
            await ctx.reply(f'{ctx.guild.name} does not have any transfers channels set.', mention_author=True)
            channels = []
        else:
            # If no Query provided we check current whitelists.
            if not channels:
                if ctx.channel.id in guild_cache:
                    channels = [ctx.channel]
                else:
                    channels = [self.bot.get_channel(i) for i in guild_cache]
            
            if not isinstance(channels, discord.TextChannel) and len(channels) != 1:
                async with ctx.typing():
                    mention_list = [i.mention for i in channels]
                    index = await embed_utils.page_selector(ctx, mention_list)
                    if index is None:
                        return None
                    channels = [channels[index]]
        
        if isinstance(channels, discord.TextChannel):
            channels = [channels]  # always return a list
            
        return channels
    
    @commands.group(invoke_without_command=True, aliases=["tf"], usage="<#channel>")
    @commands.has_permissions(manage_channels=True)
    async def ticker(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Get info on your server's transfer tickers. """
        channels = await self._pick_channels(ctx, channels)
        # (guild_id, channel_id, mode)
        guild_cache = {i[1] for i in self.cache if ctx.guild.id in i}
        if not guild_cache:
            return await ctx.reply(f"{ctx.guild.name} has no transfer ticket channels set. Use `{ctx.prefix}tf "
                                   f"set #channel` to create one.", mention_author=True)

        e = discord.Embed()
        e.colour = ctx.me.color
        
        for c in channels:
            e.title = f"Transfer ticker for {c.name}"
            if c.id not in guild_cache:
                e.colour = discord.Colour.red()
                e.description = "⛔ This channel is not set as a transfer ticker channel."
                await ctx.reply(embed=e, mention_author=True)
                continue
            
            wl_key = [i for i in self.cache if c.id in i][0]
            mode = wl_key[2]
            mode = "short" if mode is True else "Embed"
            whitelist = self.cache[wl_key]
            
            e.set_footer(text=f"New transfers are being output in {mode} mode.")
            
            if whitelist:
                wl = []
                for x in whitelist:
                    wl.append(f"{x[2]} ({x[1]})")  # Alias, type.
                    
                embeds = embed_utils.rows_to_embeds(e, wl)
                if embeds:
                    self.bot.loop.create_task(paginate(ctx, embeds))
                continue
            else:
                e.colour = discord.Colour.dark_orange()
                e.description = f'⚠ **All** Transfers are being output to this channel in **{mode}** mode.\n' \
                                f'You can create a whitelist with {ctx.prefix}tf whitelist add'
                await ctx.reply(embed=e, mention_author=False)
                continue
    
    @ticker.command(usage="<#channel1[, #channel2]> <'Embed', 'Short', or leave blank to see current setting.>")
    @commands.has_permissions(manage_channels=True)
    async def mode(self, ctx, channels: commands.Greedy[discord.TextChannel], toggle: commands.clean_content = ""):
        """ Toggle Short mode or Embed mode for transfer data """
        channels = await self._pick_channels(ctx, channels)
        guild_cache = [i for i in self.cache if ctx.guild.id in i]

        if not toggle:
            if not channels:
                return await ctx.reply('This server has no transfer ticker channels set.', message_author=True)
            for c in channels:
                mode = "Short" if [i[2] for i in self.cache if c.id in i][0] else "Embed"
                await ctx.reply(f"{c.mention} is set to {mode} mode.", mention_author=False)
            return
        
        if toggle.lower() not in ["embed", "short"]:
            return await ctx.reply(f'🚫 Invalid mode "{toggle}", use either "embed" or "short"', mention_author=True)
        
        update_toggle = True if toggle == "short" else False
        
        for c in channels:
            if c.id not in [i[1] for i in guild_cache]:
                await ctx.reply(f"🚫 {c.mention} is not set as a transfer channel.", mentiion_author=True)
                continue
                
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute("""UPDATE transfers_channels SET short_mode = $1 WHERE (channel_id) = $2""",
                                         update_toggle, c.id)
            await self.bot.db.release(connection)
            await ctx.reply(f"✅ {c.mention} was set to {toggle} mode", mention_author=False)

        await self.update_cache()
    
    @ticker.group(usage="[#channel]", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def whitelist(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Check the whitelist of specified channels """
        channels = await self._pick_channels(ctx, channels)
        
        for c in channels:
            try:
                key = [i for i in self.cache if c.id in i][0]
            except IndexError:
                print("Warning:", c.id, "not found in transfers cache.")
                await ctx.reply(f'No transfer ticker found for {c.mention}.', mention_author=True)
                continue
            whitelist = self.cache[key]
            if not whitelist:
                await ctx.reply(f"{c.mention} is tracking all transfers", mention_author=False)
                continue
            embed = discord.Embed(title=f"Whitelist items for {c.name}")
            embeds = embed_utils.rows_to_embeds(embed, [i[2] for i in whitelist])
            await embed_utils.paginate(ctx, embeds)

    @commands.has_permissions(manage_channels=True)
    @ticker.command(usage="<#Channel[, #Channel2, #Channel3]> <'team' or 'league'> <Search query>")
    async def add(self, ctx, channels: commands.Greedy[discord.TextChannel], mode, *, qry: commands.clean_content):
        """ Add a league or team to your transfer ticker channel(s)"""
        channels = await self._pick_channels(ctx, channels)
    
        if not channels:
            return
    
        if mode.lower() == "team":
            targets, links = await transfer_tools.search(ctx, qry, "clubs", whitelist_fetch=True)
        elif mode.lower() == "league":
            targets, links = await transfer_tools.search(ctx, qry, "domestic competitions", whitelist_fetch=True)
        else:
            return await ctx.reply("Invalid mode specified. Mode must be either `team` or `league`")
    
        index = await embed_utils.page_selector(ctx, targets)
        if index is None:
            return await ctx.reply('No selection provided, channel not edited.')
    
        result = links[index]
        alias = targets[index]
    
        result = result.replace('http://transfermarkt.co.uk', "")  # Trim this down.
    
        for c in channels:
            try:
                key = [i for i in self.cache if c.id in i][0]
                whitelist = self.cache[key]
            
                if result in [i[0] for i in whitelist]:
                    await ctx.reply(f"🚫 {c.mention} whitelist already contains {alias}.", mention_author=False)
                    continue
            except IndexError:
                pass
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute("""INSERT INTO transfers_whitelists (channel_id, item, type, alias)
                                            VALUES ($1, $2, $3, $4)""", c.id, result, mode, alias)
            await self.bot.db.release(connection)
            await ctx.reply(f"✅ Item <{result}> added to {c.mention} whitelist", mention_author=True)
        await self.update_cache()
    
    @commands.has_permissions(manage_channels=True)
    @ticker.command(usage="<name of country and league to remove>")
    async def remove(self, ctx, channels: commands.Greedy[discord.TextChannel], *, qry):
        """ Remove a whitelisted item from your transfer channel ticker """
        channels = await self._pick_channels(ctx, channels)
        guild_cache = {i[1] for i in self.cache if ctx.guild.id in i}
        combined_whitelist = []
        
        for c in channels:
            wl_key = [i for i in self.cache if c.id in i][0]
            channel_whitelist = self.cache[wl_key]
            for item in channel_whitelist:
                if qry.lower() in item[2].lower():
                    combined_whitelist.append(item[2])  # 2 is alias.
        
        index = await embed_utils.page_selector(ctx, combined_whitelist)
        
        if index is None:
            return await ctx.reply('No selection provided, channel not edited.', mention_author=True)
        item = combined_whitelist[index]
        
        for c in channels:
            if c.id not in guild_cache:
                await ctx.reply(f"🚫 {c.mention} is not set as a transfer tracker channel.", mention_author=False)
                continue
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute(""" DELETE FROM transfers_whitelists WHERE
                     channel_id = $1 AND alias = $2 """, c.id, item)
            await self.bot.db.release(connection)
            await ctx.reply('✅ {item} was removed from the {c.mention} whitelist.', mention_author=False)

        await self.update_cache()
    
    @ticker.command(name="set", aliases=["create"], usage="<#channel [, #channel2]> ['short' or 'full']")
    @commands.has_permissions(manage_channels=True)
    async def _set(self, ctx, channels: commands.Greedy[discord.TextChannel], short_mode=""):
        """ Set channel(s) as a transfer ticker for this server """
        if not channels:
            channels = [ctx.channel]
        
        if short_mode is not False:
            if short_mode.lower() != "short":
                short_mode = False
            else:
                short_mode = True

        for c in channels:
            if c.id in [i[1] for i in self.cache]:
                await ctx.reply(f"🚫 {c.mention} already set as transfer ticker(s)", mention_author=False)
                continue
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute(
                    """INSERT INTO transfers_channels (guild_id,channel_id,short_mode) VALUES ($1,$2,$3)""",
                    ctx.guild.id, c.id, short_mode)
            await self.bot.db.release(connection)
            
            mode = "short mode" if short_mode else "embed mode"
            await ctx.reply(
                f"✅ Set {c.mention} as transfer ticker channel(s) using {mode} mode. ALL transfers will be output "
                f"there. Please create a whitelist if this gets spammy.", mention_author=False)

        await self.update_cache()
    
    @ticker.command(name="unset", aliases=["delete"], usage="<#channel-to-unset>")
    @commands.has_permissions(manage_channels=True)
    async def _unset(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Remove a channel's transfer ticker """
        channels = await self._pick_channels(ctx, channels)
        
        for c in channels:
            if c.id not in [i[1] for i in self.cache]:
                await ctx.reply(f"🚫 {c.mention} was not set as a transfer ticker channel.", mention_author=False)
                continue
            connection = await self.bot.db.acquire()
            async with connection.transaction():
                await connection.execute("""DELETE FROM transfers_channels WHERE channel_id = $1""", c.id)
            await self.bot.db.release(connection)
            await ctx.reply(f"✅ Removed transfer ticker from {c.mention}", mention_author=False)
        await self.update_cache()

    @ticker.command(usage="<channel_id>", hidden=True)
    @commands.is_owner()
    async def admin(self, ctx, channel_id: int):
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            await connection.execute(""" DELETE FROM transfers_channels WHERE channel_id = $1""", channel_id)
        await self.bot.db.release(connection)
        await ctx.reply(f"✅ **{channel_id}** was deleted from the transfers database", mention_author=False)
        await self.update_cache()
        
        
def setup(bot):
    bot.add_cog(Transfers(bot))
