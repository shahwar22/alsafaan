from discord.ext import commands
from collections import Counter
import ext.utils.codeblocks as codeblocks
from importlib import reload
import datetime
import discord
import typing

from ext.utils.embed_utils import get_colour


class Info(commands.Cog):
    """ Get information about users or servers. """
    
    def __init__(self, bot):
        self.bot = bot
        reload(codeblocks)
        if not hasattr(self.bot, "commands_used"):
            self.bot.commands_used = Counter()
    
    @commands.command(aliases=['botstats', "uptime", "hello", "inviteme", "invite"])
    async def about(self, ctx):
        """Tells you information about the bot itself."""
        e = discord.Embed(colour=0x2ecc71, timestamp=self.bot.user.created_at)
        owner = await self.bot.fetch_user(self.bot.owner_id)
        e.set_footer(text=f"Toonbot is coded (badly) by {owner} and was created on ")
        e.set_thumbnail(url=ctx.me.avatar_url)
        e.title = f"{ctx.me.display_name} ({ctx.me})" if not ctx.me.display_name == "ToonBot" else "Toonbot"
        
        # statistics
        total_members = sum(len(s.members) for s in self.bot.guilds)
        members = f"{total_members} Members across {len(self.bot.guilds)} servers."
        
        prefixes = f"\nYou can use `.tb help` to see my commands."
        
        e.description = f"I do football lookup related things.\n I have {members}"
        e.description += prefixes
        
        technical_stats = f"{datetime.datetime.now() - self.bot.initialised_at}\n"
        technical_stats += f"{sum(self.bot.commands_used.values())} commands ran this session."
        e.add_field(name="Uptime", value=technical_stats, inline=False)
        
        invite_and_stuff = f"[Invite me to your server]" \
                           f"(https://discordapp.com/oauth2/authorize?client_id=250051254783311873" \
                           f"&permissions=67488768&scope=bot)\n"
        invite_and_stuff += f"[Join my Support Server](http://www.discord.gg/a5NHvPx)\n"
        invite_and_stuff += f"[Toonbot on Github](https://github.com/Painezor/Toonbot)"
        e.add_field(name="Using me", value=invite_and_stuff, inline=False)
        await ctx.reply(embed=e, mention_author=False)
    
    @commands.command(aliases=["perms"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def permissions(self, ctx, *, member: discord.Member = None):
        """Shows a member's permissions."""
        if member is None:
            member = ctx.author
        permissions = ctx.channel.permissions_for(member)
        permissions = "\n".join([f"{i[0]} : {i[1]}" for i in permissions])
        await ctx.reply(f"```py\n{permissions}```", mention_author=False)
    
    @commands.command(aliases=["lastmsg", "lastonline", "lastseen"], usage="seen @user")
    async def seen(self, ctx, target: discord.Member):
        """ Find the last message from a user in this channel """
        m = await ctx.reply("Searching...", mention_author=False)
        with ctx.typing():
            if ctx.author == target:
                return await ctx.reply("Last seen right now, being an idiot.", mention_author=True)
            
            async for msg in ctx.channel.history(limit=1000):
                if msg.author.id == target.id:
                    if target.id == 178631560650686465:
                        c = (f"{target.mention} last seen being a spacker in "
                             f" {ctx.channel.mention} at {msg.created_at} "
                             f"saying '{msg.content}'")
                        await m.edit(content=c)
                    else:
                        c = (f"{target.mention} last seen in {ctx.channel.mention} "
                             f"at {msg.created_at} saying '{msg.content}'")
                        await m.edit(content=c)
                    return
            await m.edit(content="Couldn't find a recent message from that user.")
    
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def info(self, ctx, *, member: typing.Union[discord.Member, discord.User] = None):
        """Shows info about a member.
        This cannot be used in private messages. If you don't specify
        a member then the info returned will be yours.
        """
        if member is None:
            member = ctx.author
        
        e = discord.Embed()
        e.description = member.mention
        e.set_footer(text='Account created').timestamp = member.created_at
        
        try:
            roles = [role.mention for role in member.roles]
            e.add_field(name='Roles', value=', '.join(roles), inline=False)
            voice = member.voice
            if voice is not None:
                voice = voice.channel
                other_people = len(voice.members) - 1
                voice_fmt = f'{voice.name} with {other_people} others' if other_people else f'{voice.name} alone'
                e.add_field(name='Voice Chat', value=voice_fmt, inline=False)
            # status = str(member.status).title()
            #
            # if status == "Online":
            #     status = "🟢 Online\n"
            # elif status == "Offline":
            #     status = "🔴 Offline\n"
            # else:
            #     status = f"🟡 {status}\n"
            #
            activity = member.activity
            try:
                activity = f"{discord.ActivityType[activity.type]} {activity.name}\n"
            except KeyError:  # Fix on custom status update.
                activity = ""
            
            coloured_time = codeblocks.time_to_colour(member.joined_at)
            e.add_field(name=f'Joined {ctx.guild.name}', value=coloured_time, inline=False)
            e.colour = member.colour
        except AttributeError:
            # status = ""
            activity = ""
            pass
        
        shared = sum(1 for m in self.bot.get_all_members() if m.id == member.id)
        # field_1_text = f"{status}ID: {member.id}\n{activity}"
        field_1_text = f"ID: {member.id}\n{activity}"
        if shared - 1:
            field_1_text += f"Seen in {shared} other discords."
        e.add_field(name="User info", value=field_1_text)
        e.set_author(name=str(member), icon_url=member.avatar_url or member.default_avatar_url)
        
        if member.bot:
            e.description += "\n**🤖 This user is a bot**"
        
        try:
            if member.is_on_mobile():
                e.description += "\n📱 Using mobile app."
        except AttributeError:  # User.
            pass
        
        if member.avatar:
            e.set_thumbnail(url=member.avatar_url)
        await ctx.reply(embed=e, mention_author=False)
    
    @info.command(name='guild', aliases=["server"])
    @commands.guild_only()
    async def server_info(self, ctx):
        """ Shows information about the server """
        guild = ctx.guild
        
        # figure out what channels are 'secret'
        text_channels = 0
        for channel in guild.channels:
            text_channels += isinstance(channel, discord.TextChannel)
        
        regular_channels = len(guild.channels)
        voice_channels = len(guild.channels) - text_channels
        
        e = discord.Embed()
        e.title = guild.name
        try:
            e.description = f"Owner: {guild.owner.mention}\nGuild ID: {guild.id}"
        except AttributeError:
            e.description = f"Guild ID: {guild.id}"
        e.description += f'\n\n{guild.member_count} Members' \
                         f"\n{regular_channels} text channels "
        if voice_channels:
            e.description += f"and {voice_channels} Voice channels"
            
        if guild.premium_subscription_count:
            e.description += f"\n{guild.premium_subscription_count} Nitro Boosts"
        
        if guild.discovery_splash:
            e.set_image(url=guild.discovery_splash)

        if guild.icon:
            e.set_thumbnail(url=guild.icon_url)
            e.colour = await get_colour(str(guild.icon_url))

        emojis = ""
        for emoji in guild.emojis:
            if len(emojis) + len(str(emoji)) < 1024:
                emojis += str(emoji)
        if emojis:
            e.add_field(name="Custom Emojis", value=emojis, inline=False)
        
        roles = [role.mention for role in guild.roles]
        e.add_field(name='Roles', value=', '.join(roles) if len(roles) < 20 else f'{len(roles)} roles', inline=False)
        e.add_field(name="Creation Date", value=codeblocks.time_to_colour(guild.created_at))
        e.set_footer(text=f"\nRegion: {str(guild.region).title()}")
        await ctx.reply(embed=e, mention_author=False)
    
    @commands.command()
    async def avatar(self, ctx, user: typing.Union[discord.User, discord.Member] = None):
        """ Shows a member's avatar """
        if user is None:
            user = ctx.author
        e = discord.Embed()
        e.colour = user.color
        e.set_footer(text=user.avatar_url)
        e.timestamp = datetime.datetime.now()
        e.description = f"{user.mention}'s avatar"
        e.set_image(url=str(user.avatar_url))
        await ctx.reply(embed=e, mention_author=False)


def setup(bot):
    bot.add_cog(Info(bot))
