from collections import defaultdict

from discord.ext import commands
import discord
import typing

# TODO: Bad words filters


class AutoMod(commands.Cog):
    """ Set up automated moderation tools """
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.update_cache())
        self.cache = defaultdict()

    async def update_cache(self):
        self.cache.clear()
        connection = await self.bot.db.acquire()
        async with connection.transaction():
            records = await connection.fetch("""SELECT * FROM mention_spam""")
        await self.bot.db.release(connection)

        for r in records:
            r = {r['guild_id']:
                     {"mention_threshold": r["mention_threshold"],
                      "mention_action": r['mention_action']}}
            self.cache.update(r)

    @commands.has_permissions(kick_members=True, ban_members=True)
    @commands.command(usage="mentionspam <number of pings> <'kick', 'mute' or 'ban'>", aliases=["pingspam"])
    async def mentionspam(self, ctx, threshold: typing.Optional[int] = None, action=None):
        """ Automatically kick or ban a member for pinging more than x users in a message. Use '0' for threshold to 
        turn off."""
        if threshold is None:
            # Get current data.
            try:
                guild_cache = self.cache[ctx.guild.id]
                return await ctx.send(
                    f"I will {guild_cache['mention_action']} members who ping {guild_cache['mention_threshold']} or "
                    f"more other users in a message.")
            except KeyError:
                return await ctx.send(
                    f"No action is currently being taken against users who spam mentions. Use {ctx.prefix}mentionspam "
                    f"<number> <action ('kick', 'ban' or 'mute')> to change this")
        elif threshold < 4:
            return await ctx.send("Please set a limit higher than 3.")

        if action is None or action.lower() not in ['kick', 'ban', 'mute']:
            return await ctx.send("🚫 Invalid action specified, valid actions are 'kick', 'ban', or 'mute'.")

        action = action.lower()
        if action == "kick":
            if not ctx.me.permissions_in(ctx.channel).kick_members:
                return await ctx.send("🚫 I need the 'kick_members' permission to do that.")
            if not ctx.author.permissions_in(ctx.channel).kick_members:
                return await ctx.send("🚫 You need the 'kick_members' permission to do that.")
        elif action == "ban":
            if not ctx.me.permissions_in(ctx.channel).ban_members:
                return await ctx.send("🚫 I need the 'ban_members' permission to do that.")
            if not ctx.author.permissions_in(ctx.channel).ban_members:
                return await ctx.send("🚫 You need the 'ban_members' permission to do that.")

        connection = await self.bot.db.acquire()
        await connection.execute("""
        INSERT INTO mention_spam (guild_id,mention_threshold, mention_action)
    	VALUES ($1, $2, $3)
        ON CONFLICT (guild_id) DO UPDATE SET
             (mention_threshold, mention_action) = ($2,$3)
        WHERE
             EXCLUDED.guild_id = $1
        """, ctx.guild.id, threshold, action)
        await self.update_cache()
        return await ctx.send(f"✅ I will {action} users who ping {threshold} other users in a message.")

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            guild_cache = self.cache[message.guild.id]
        except (KeyError, AttributeError):
            return
        if guild_cache["mention_threshold"] > len(message.mentions):
            return
        if guild_cache["mention_action"] == "kick":
            await message.author.kick(reason=f"Mentioning {guild_cache['mention_threshold']} members in a message.")
            return await message.channel.send(f"{message.author.mention} was kicked for mention spamming.")
        elif guild_cache["mention_action"] == "ban":
            await message.author.ban(reason=f"Mentioning {guild_cache['mention_threshold']} members in a message.")
            return await message.channel.send(f"☠️ {message.author.mention} was banned for mention spamming.")
        elif guild_cache["mention_action"] == "mute":
            muted_role = discord.utils.get(message.guild.roles, name='Muted')
            if not muted_role:
                muted_role = await message.guild.create_role(name="Muted")
                pos = message.guild.me.top_role.position - 1
                await muted_role.edit(position=pos)
                ow = discord.PermissionOverwrite(add_reactions=False,send_messages=False)
                for i in message.guild.text_channels:
                    await i.set_permissions(muted_role, overwrite=ow)

                await message.author.add_roles(*[muted_role])
                await message.channel.send(f"{message.author.mention} was muted for mention spam.")


def setup(bot):
    bot.add_cog(AutoMod(bot))
