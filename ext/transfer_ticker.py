from collections import defaultdict

import typing
from discord.ext import commands, tasks
from ext.utils import transfer_tools
from lxml import html
import asyncio
import discord


class TransferTicker(commands.Cog):
    """ Create and configure Transfer-Ticker channels"""

    async def imgurify(self, img_url):
        # upload image to imgur
        d = {"image": img_url}
        h = {'Authorization': f'Client-ID {self.bot.credentials["Imgur"]["Authorization"]}'}
        async with self.bot.session.post("https://api.imgur.com/3/image", data=d, headers=h) as resp:
            res = await resp.json()
        return res['data']['link']

    def __init__(self, bot):
        self.bot = bot
        self.parsed = []
        self.bot.transfer_ticker = self.transfer_ticker.start()
        self.whitelist_cache = defaultdict(list)
        self.channel_cache = defaultdict(dict)

    def cog_unload(self):
        self.transfer_ticker.cancel()

    async def update_cache(self):
        # Get our new data.
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            channels = await connection.fetch("""SELECT * FROM transfers_channels""")
            whitelists = await connection.fetch("""SELECT * FROM transfers_whitelists""")
        await self.bot.db.release(connection)
        
        # TODO: Make a better SQL statement to extract this and merge into a single cache.
        # Clear our cache
        self.channel_cache.clear()
        self.whitelist_cache.clear()
        
        # Repopulate them.
        for r in channels:
            this_item = {r["channel_id"]: {"short_mode": r["short_mode"]}}
            self.channel_cache[r["guild_id"]].update(this_item)
        for r in whitelists:
            this_item = {"item": r["item"], "details": {"type": r["type"], "alias": r["alias"]}}
            print(this_item)
            self.whitelist_cache[r["channel_id"]].append(this_item)

    @tasks.loop(minutes=1)
    async def transfer_ticker(self):
        try:
            async with self.bot.session.get('https://www.transfermarkt.co.uk/statistik/neuestetransfers') as resp:
                if resp.status != 200:
                    return
                tree = html.fromstring(await resp.text())
        except Exception as e:
            print("Error fetching transfermarkt data.")
            print(e)  # Find out what this error is and narrow the exception down.
            return
        
        skip_output = True if not self.parsed else False
        
        for i in tree.xpath('.//div[@class="responsive-table"]/div/table/tbody/tr'):
            player_name = "".join(i.xpath('.//td[1]//tr[1]/td[2]/a/text()')).strip()
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
            new_team = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/text()'))
            new_team_link = "".join(i.xpath('.//td[5]/table//tr[1]/td/a/@href'))
            new_league = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/text()'))
            new_league_link = "".join(i.xpath('.//td[5]/table//tr[2]/td/a/@href'))
            new_league_link = f"https://www.transfermarkt.co.uk{new_league_link}" if new_league_link else ""
            new_league_flag = transfer_tools.get_flag("".join(i.xpath('.//td[5]/table//tr[2]/td//img/@alt')))

            old_team = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/text()'))
            old_team_link = "".join(i.xpath('.//td[4]/table//tr[1]/td/a/@href'))
            old_league = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/text()'))
            old_league_link = "".join(i.xpath('.//td[4]/table//tr[2]/td/a/@href'))
            old_league_link = f"https://www.transfermarkt.co.uk{new_league_link}" if old_league_link else ""
            old_league_flag = transfer_tools.get_flag("".join(i.xpath('.//td[4]/table//tr[2]/td//img/@alt')))

            # Markdown.
            new_league_markdown = f"{new_league_flag} [{new_league}]({new_league_link})" if new_league != "None" \
                else ""
            new_team_markdown = f"[{new_team}]({new_team_link})"
            old_league_markdown = f"{old_league_flag} [{old_league}]({old_league_link})" if old_league != "None" \
                else ""
            old_team_markdown = f"[{old_team}]({old_team_link})"

            if new_league == old_league:
                move_info = f"{old_team} to {new_team} ({new_league_flag} {new_league})"
            else:
                move_info = f"{old_team} ({old_league_flag} {old_league}) to {new_team} ({new_league_flag} " \
                            f"{new_league})"

            move_info = move_info.replace(" (None )", "")

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
            e.set_thumbnail(url=th)

            shortstring = f"{player_name} | {fee} | <{fee_link}>\n{move_info}"

            for g, cl in self.channel_cache.items():
                for c, k in cl.items():
                    ch = self.bot.get_channel(c)
                    whitelisted = self.whitelist_cache[c]
                    if whitelisted:
                        this_whitelist = whitelisted[i]
                        values = [i['item'] for i in this_whitelist]
                        if not any([new_team_link, old_team_link, new_league_link, old_league_link]) in values:
                            continue
                    short_mode = self.channel_cache[g][c]["short_mode"]

                    try:
                        if short_mode:
                            await ch.send(shortstring)
                        else:
                            await ch.send(embed=e)
                    except discord.Forbidden:
                        print(f"Discord.Forbidden while trying to send new transfer to {c}")
                    except AttributeError:
                        print(
                            f"AttributeError while trying to send new transfer to {c} - Check for channel "
                            f"deletion.")
    
    @transfer_ticker.before_loop
    async def before_tf_loop(self):
        await self.bot.wait_until_ready()
        await self.update_cache()

    async def _pick_channels(self, ctx, channels: typing.List[discord.TextChannel]):
        # Assure guild has transfer channel.
        guild_cache = self.channel_cache[ctx.guild.id]
        
        if isinstance(channels, discord.TextChannel):
            channels = [channels]
        
        if not guild_cache:
            await ctx.send(f'{ctx.guild.name} does not have any transfers channels set.')
            channels = []
        else:
            # Channel picker for invoker.
            def check(message):
                return ctx.author.id == message.author.id and message.channel_mentions

            # If no Query provided we check current whitelists.
            if not channels:
                if ctx.channel.id in guild_cache:
                    channels = [ctx.channel]
                else:
                    channels = [self.bot.get_channel(i) for i in list(guild_cache)]

            if len(channels) != 1:
                async with ctx.typing():
                    mention_list = " ".join([i.mention for i in channels])
                    m = await ctx.send(
                        f"{ctx.guild.name} has multiple transfer channels set: ({mention_list}), please specify which "
                        f"one(s) to check or modify.")

                    try:
                        channels = await self.bot.wait_for("message", check=check, timeout=30)
                        channels = channels.channel_mentions[0]
                        await m.delete()
                    except asyncio.TimeoutError:
                        await m.edit(
                            content="Timed out waiting for you to reply with a channel list. No channels were "
                                    "modified.")
                        channels = []

        return channels

    @commands.group(invoke_without_command=True, aliases=["ticker"], usage="tf (#channel)")
    @commands.has_permissions(manage_channels=True)
    async def tf(self, ctx, *, channels: commands.Greedy[discord.TextChannel]):
        """ Get info on your server's transfer tickers. """
        channels = await self._pick_channels(ctx, channels)
        guild_cache = self.channel_cache[ctx.guild.id]
        if not guild_cache:
            return await ctx.send(f"Your server does not have any transfer ticket channels set. Use `{ctx.prefix}tf "
                                  f"set #channel` to create one.")

        replies = []
        for i in channels:
            if i.id not in guild_cache:
                replies.append(f"{i.mention} is not set as one of {ctx.guild.name}'s transfer tickers.")

            mode = guild_cache[i.id]["short_mode"]
            mode = "short" if mode is True else "Embed"

            whitelist = self.whitelist_cache[i.id]
            if whitelist:
                wl = []
                print(whitelist)
                for x in whitelist:
                    print(x)
                    wl.append(f"{whitelist[x]['alias']} ({whitelist[x]['type']})")
                wl = ", ".join(wl)
                replies.append(
                    f'Transfers are being output to {i.mention} in **{mode}** mode for your whitelist of `{wl}`')
            else:
                replies.append(
                    f'**All** Transfers are being output to {i.mention} in **{mode}** mode. You can create a '
                    f'whitelist with {ctx.prefix}tf whitelist add')

        await ctx.send("\n".join(replies))

    @tf.command(
        usage="tf mode <Optional: #channel1, #channel2> <'Embed','Short', or leave blank to see current setting.>")
    @commands.has_permissions(manage_channels=True)
    async def mode(self, ctx, channels: commands.Greedy[discord.TextChannel], toggle: commands.clean_content = ""):
        """ Toggle Short mode or Embed mode for transfer data """
        channels = await self._pick_channels(ctx, channels)

        guild_cache = self.channel_cache[ctx.guild.id]

        if not toggle:
            replies = []
            for c in channels:
                mode = "Short" if guild_cache[c.id]["short_mode"] else "Embed"
                replies.append(f"{c.mention} is set to {mode} mode.")
            return await ctx.send("\n".join(replies))

        if toggle.lower() not in ["embed", "short"]:
            return await ctx.send(f'🚫 Invalid mode "{toggle}" specified, mode can either be "embed" or "short"')

        update_toggle = True if toggle == "short" else False

        replies = []
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            for c in channels:
                if c.id not in guild_cache:
                    replies.append(f"🚫 {c.mention} is not a transfers channel.")
                    continue

                await connection.execute("""UPDATE transfers_channels (mode) VALUES ($1) WHERE (channel_id) = $2""",
                                         update_toggle, c.id)
                replies.append(f"✅ {c.mention} was set to {toggle} mode")

        await ctx.send("\n".join(replies))
        await self.bot.db.release(connection)
        await self.update_cache()

    @tf.group(usage="tf whitelist <Optional: #channel>", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def whitelist(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        """ Check the whitelist of specified channels """
        channels = await self._pick_channels(ctx, channels)
        replies = []
        for i in channels:
            whitelist = self.whitelist_cache[i.id]
            if not whitelist:
                replies.append(f'The whitelist for {i.mention} is currently empty, all transfers are being output.')
                continue

            wl = []
            for item in whitelist:
                wl.append(f"{item['details']['alias']} ({item['item']})")
            wl = "```" + "\n".join(wl) + "```"
            replies.append(f'The whitelist for {i.mention} is: `{wl}`')
        await ctx.send("\n".join(replies))

    @commands.has_permissions(manage_channels=True)
    @whitelist.command(name="add",
                       usage="tf whitelist add <Optional: #Channel1, #Channel2, #Channel3> <'team' or 'league'> "
                             "<Search query>")
    async def _add(self, ctx, channels: commands.Greedy[discord.TextChannel], mode, *, qry: commands.clean_content):
        """ Add a league or team to your transfer ticker channel(s)"""
        channels = await self._pick_channels(ctx, channels)

        if not channels:
            return

        if mode.lower() == "team":
            targets, links = await transfer_tools.search(ctx, qry, "clubs", whitelist_fetch=True)
        elif mode.lower() == "league":
            targets, links = await transfer_tools.search(ctx, qry, "domestic competitions", whitelist_fetch=True)
        else:
            return await ctx.send("Invalid mode specified. Mode must be either 'team' or 'league'")
        e = discord.Embed(description="")
        e.title = "Please type matching ID#"
        values = {}
        count = 1
        for (i, j) in zip(targets, links):
            print("i", i)
            print("j", j)
            link = "http://www.transfermarkt.com" + j
            print("link", link)
            this_value = {str(count): {"alias": i, "link": link}}
            values.update(this_value)
            e.description += f"[{count}] [{i}]({link})\n"
            count += 1

        m = await ctx.send(embed=e)

        def check(msg):
            if msg.author.id == ctx.author.id and msg.content in values:
                return True

        try:
            message = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("⚠ Item selection timed out, your whitelisted items were not updated.")
            return await m.delete()

        match = message.content
        result = values[match]['link']
        alias = values[match]['alias']

        connection = await self.bot.db.acquire()
        replies = []
        for c in channels:
            whitelist = self.whitelist_cache[c.id]
            print(result, whitelist)
            if result in whitelist:
                replies.append(f"🚫 {c.mention} whitelist already contains <{result}>.")
                continue

            await connection.execute("""INSERT INTO transfers_whitelists (channel_id, item, type, alias)
                                    VALUES ($1, $2, $3, $4)""",  c.id, result, mode, alias)
            replies.append(f"✅ Whitelist for {c.mention} updated, current whitelist: ```{whitelist}```")

        replies = "\n".join(replies)
        await self.bot.db.release(connection)
        await self.update_cache()
        await ctx.send(replies)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in self.channel_cache:
            connection = await self.bot.db.acquire()
            await connection.execute("""DELETE FROM transfers_channels WHERE guild_id = $1""", guild.id)
            await self.bot.db.release(connection)
            await self.update_cache()
            
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if channel.id in self.channel_cache[channel.guild.id]:
            connection = await self.bot.db.acquire()
            await connection.execute("""DELETE FROM transfers_channels WHERE channel_id = $1""", channel.id)
            await self.bot.db.release(connection)
            await self.update_cache()

    @commands.has_permissions(manage_channels=True)
    @whitelist.command(name="remove", usage="tf whitelist remove will display a list of items for you to select from.")
    async def _remove(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        channels = await self._pick_channels(ctx, channels)
        guild_cache = self.channel_cache[ctx.guild.id]

        combined_whitelist = []
        
        if isinstance(channels, discord.TextChannel):
            channels = [channels]
        
        for i in channels:
            combined_whitelist += [y["alias"] for y in self.whitelist_cache[i] if y["alias"] not in combined_whitelist]
        e = discord.Embed()
        count = 0
        id_whitelist = {}
        for i in combined_whitelist:
            id_whitelist.update({str(count): i})
            e.description += f"{count} {i}"

        e.title = "Please type matching ID#"

        def check(msg):
            return ctx.author.id == msg.author.id and msg.content in id_whitelist

        m = await ctx.send(embed=e)
        try:
            message = await self.bot.wait_for("message", check=check, timeout=30)
            target = message.content
        except asyncio.TimeoutError:
            await m.delete()
            return await ctx.send("Timed out waiting for response. No whitelist items were deleted.")

        alias = id_whitelist[target]["alias"]

        replies = []
        connection = await self.bot.db.acquire()
        for c in channels:
            if c.id not in guild_cache:
                replies.append(f"🚫 {c.mention} was not set as a transfer tracker channel.")
                continue
            await connection.execute(""" 
                DELETE FROM transfers_whitelist WHERE (channel_id,alias) == ($1,$2)
                """, c.id, alias)
        await self.bot.db.release(connection)
        await self.update_cache()

    @tf.command(name="set", aliases=["add"],
                usage="tf set (Optional: #channel #channel2) (Optional argument: 'short' - use short mode for "
                      "output.)- will use current channel if not provided.)")
    @commands.has_permissions(manage_channels=True)
    async def _set(self, ctx, channels: commands.Greedy[discord.TextChannel], short_mode=""):
        """ Set channel(s) as a transfer ticker for this server """
        if not channels:
            channels = [ctx.channel]

        if short_mode is not False:
            if short_mode.lower() != "short":
                await ctx.send("Invalid mode provided, using Embed mode.")
                short_mode = False
            else:
                short_mode = True
        connection = await self.bot.db.acquire()
        replies = []
        for c in channels:
            if c.id in self.channel_cache:
                replies.append(f"🚫 {c.mention} already set as transfer ticker(s)")
                continue

            await connection.execute(
                """INSERT INTO transfers_channels (guild_id,channel_id,short_mode) VALUES ($1,$2,$3)""", ctx.guild.id,
                c.id, short_mode)
            mode = "short mode" if short_mode else "embed mode"
            replies.append(
                f"✅ Set {c.mention} as transfer ticker channel(s) using {mode} mode. ALL transfers will be output "
                f"there. Please create a whitelist if this gets spammy.")
        await self.bot.db.release(connection)
        await self.update_cache()
        replies = "\n".join(replies)
        await ctx.send(replies)

    @tf.command(name="unset", aliases=["remove", "delete"])
    @commands.has_permissions(manage_channels=True)
    async def _unset(self, ctx, channels: commands.Greedy[discord.TextChannel]):
        channels = await self._pick_channels(ctx, channels)
        
        connection = await self.bot.db.acquire()
        replies = []
        async with connection.transaction():
            for c in channels:
                if c.id not in self.channel_cache[ctx.guild.id]:
                    replies.append(f"🚫 {c.mention} was not set as transfer ticker channels..")
                    continue

                await connection.execute("""DELETE FROM transfers_channels WHERE channel_id = $1""", c.id)
                replies.append(f"✅ Deleted transfer ticker from {c.mention}")
        await self.bot.db.release(connection)
        await self.update_cache()
        if replies:
            await ctx.send("\n".join(replies))


def setup(bot):
    bot.add_cog(TransferTicker(bot))
