from discord.ext import commands
import traceback
import discord


class Errors(commands.Cog):
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
            return  # Fail silently.
        
        elif isinstance(error, (discord.Forbidden, commands.DisabledCommand, commands.MissingPermissions)):
            if isinstance(error, discord.Forbidden):
                print(f"Discord.Forbidden Error, check {ctx.command} bot_has_permissions  {ctx.message.content}\n"
                      f"{ctx.author}) in {ctx.channel.name} on {ctx.guild.name}")
            try:
                return await ctx.message.add_reaction('⛔')
            except discord.Forbidden:
                return
        
        # Embed errors.
        e = discord.Embed()
        e.colour = discord.Colour.red()
        e.title = f"Error: {error.__class__.__name__}"
        e.set_thumbnail(url=str(ctx.me.avatar_url))

        if ctx.command.usage is None:
            useline = f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"
        else:
            useline = f"{ctx.prefix}{ctx.command.usage}"
        e.add_field(name="Command Usage Examplee", value=useline)

        location = "a DM" if ctx.guild is None else f"{ctx.guild.name} ({ctx.guild.id})"
        context = f"({ctx.author}({ctx.author.id}) in {location}"
        if isinstance(error, (commands.NoPrivateMessage, commands.BotMissingPermissions)):
            if ctx.guild is None:
                e.title = 'NoPrivateMessage'  # Ugly override.
                e.description = '🚫 This command cannot be used in DMs'
            else:
                if len(error.missing_perms) == 1:
                    perm_string = error.missing_perms[0]
                else:
                    last_perm = error.missing_perms.pop(-1)
                    perm_string = ", ".join(error.missing_perms) + " and " + last_perm
                
                if isinstance(error, commands.BotMissingPermissions):
                    e.description = f'\🚫 I need {perm_string} permissions to do that.\n'
                    fixing = f'Use {ctx.me.mention} `disable {ctx.command}` to disable this command\n' \
                             f'Use {ctx.me.mention} `prefix remove {ctx.prefix}` ' \
                             f'to stop me using the `{ctx.prefix}` prefix\n' \
                             f'Or give me the missing permissions and I can perform this action.'
                    e.add_field(name="Fixing This", value=fixing)
        
        elif isinstance(error, commands.MissingRequiredArgument):
            e.description = f"{error.param.name} is a required argument but was not provided"
        
        elif isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
            e.description = str(error)
        
        elif isinstance(error, commands.CommandOnCooldown):
            e.description = f'⏰ On cooldown for {str(error.retry_after).split(".")[0]}s'
            return await ctx.send(embed=e, delete_after=5)
        
        elif isinstance(error, commands.NSFWChannelRequired):
            e.description = f"🚫 This command can only be used in NSFW channels."
        
        elif isinstance(error, commands.CommandInvokeError):
            cie = error.original
            if isinstance(cie, (NotImplementedError, AssertionError)):
                e.title = "Sorry."
                e.description = "".join(cie.args)
                return await ctx.send(embed=e)
                
            traceback.print_tb(cie.__traceback__)
            
            print(f'{cie.__class__.__name__}: {cie}')
            print(location)
            e.title = error.original.__class__.__name__
            tb_to_code = traceback.format_exception(type(cie), cie, cie.__traceback__)
            tb_to_code = ''.join(tb_to_code)
            e.description = f"```py\n{tb_to_code}```"
            e.add_field(name="Oops!", value="Painezor probably fucked this up. He has been notified.")
        else:
            print(f"Unhandled Error Type: {error.__class__.__name__}\n"
                  f"{context} caused the following error\n"
                  f"{error}\n"
                  f"Context: {ctx.message.content}\n")
        try:
            await ctx.send(embed=e)
        except discord.Forbidden:
            try:
                await ctx.send('An error occurred, I need embed_links permissions to send embeds.')
            except discord.Forbidden:
                return  # well fuck you too then?
        except discord.HTTPException:
            print(e.description)
            e.description = "An error occurred, error too long to output in embed."
            await ctx.send(embed=e)

            
def setup(bot):
    bot.add_cog(Errors(bot))
