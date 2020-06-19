import discord
from discord.ext import commands


class Help(commands.HelpCommand):
    def get_command_signature(self, command):
        return '{0.clean_prefix}{1.qualified_name} {1.signature}'.format(self, command)
    
    async def send_bot_help(self, mapping):
        """ WIP New Help Command. """
        # Base Embed
        e = discord.Embed()
        e.set_thumbnail(url=self.context.me.avatar_url)
        e.colour = 0x2ecc71
        e.set_author(name="Toonbot Help")
        
        e.description = f"Use {self.context.prefix}help **category name** for help on a category\n\n"
        
        cogs = [self.context.bot.get_cog(cog) for cog in self.context.bot.cogs]
        for cog in cogs:
            if not cog.get_commands():
                continue  # Filter utility cogs.
            
            if any([i.can_run(self.context) for i in cog.walk_commands()]):
                e.description += f"**{cog.qualified_name}**: {cog.description}\n"
        
        invite_and_stuff = f"[Invite me to your discord]" \
                           f"(https://discordapp.com/oauth2/authorize?client_id=250051254783311873" \
                           f"&permissions=67488768&scope=bot)\n"
        invite_and_stuff += f"[Join my Support discord](http://www.discord.gg/a5NHvPx)\n"
        invite_and_stuff += f"[Toonbot on Github](https://github.com/Painezor/Toonbot)"
        e.add_field(name="Useful links", value=invite_and_stuff)
        
        await self.context.send(embed=e)
    
    async def send_cog_help(self, cog):
        await self.context.send(embed=await self.cog_embed(cog))
    
    async def cog_embed(self, cog):
        def descriptor(command):
            string = f'`{command.name}` - {command.short_doc}'
            if isinstance(command, commands.Group):
                string += f'\n*Subcommands*: ┗ {", ".join(f"`{sub.name}`" for sub in command.commands)}'
            return string
        
        e = discord.Embed()
        e.title = f'{cog.qualified_name} help'
        e.colour = 0x2ecc71
        e.set_thumbnail(url=self.context.me.avatar_url)
        e.description = cog.description + "\n"
        e.description += '\n'.join([descriptor(command) for command in cog.get_commands() if not command.hidden])
        e.add_field(name="More help", value='Use help **command** to view the usage of that command.\n'
                                            f'Subcommands are ran by using `{self.context.prefix}command subcommand`')
        return e
    
    async def send_group_help(self, group):
        e = discord.Embed()
        e.title = f'{group.name} help'
        e.description = group.help
        e.colour = 0x2ecc71
        e.set_thumbnail(url=self.context.me.avatar_url)
        
        if group.aliases:
            e.add_field(name='Aliases', value=', '.join(group.aliases), inline=False)
        for command in group.commands:
            e.add_field(name=command.name, value=f'{command.help} ```{self.get_command_signature(command)}```',
                        inline=False)
        e.set_footer(text='<REQUIRED argument> | [OPTIONAL argument]')
        await self.context.send(embed=e)
    
    async def send_command_help(self, command):
        e = discord.Embed()
        e.title =f'{command.name} help'
        e.description = command.help
        e.set_thumbnail(url=self.context.me.avatar_url)
        e.colour = 0x2ecc71
        
        if command.aliases:
            e.add_field(name='Aliases', value=', '.join(f'`{alias}`' for alias in command.aliases), inline=False)
        
        e.add_field(name='Usage', value=self.get_command_signature(command))
        e.set_footer(text='<REQUIRED argument> | [OPTIONAL argument]')
        await self.context.send(embed=e)
    
    # Override to make cogs not case-sensitive
    async def command_callback(self, ctx, *, command=None):
        await self.prepare_help_command(ctx, command)
        
        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)
        
        cog = ctx.bot.get_cog(command.title())
        if cog is not None:
            return await self.send_cog_help(cog)
        
        keys = command.split(' ')
        cmd = ctx.bot.all_commands.get(keys[0])
        if cmd is None:
            string = await discord.utils.maybe_coroutine(self.command_not_found, self.remove_mentions(keys[0]))
            return await self.send_error_message(string)
        
        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                string = await discord.utils.maybe_coroutine(self.subcommand_not_found, cmd, self.remove_mentions(key))
                return await self.send_error_message(string)
            else:
                if found is None:
                    string = await discord.utils.maybe_coroutine(self.subcommand_not_found, cmd, self.remove_mentions(key))
                    return await self.send_error_message(string)
                cmd = found
        
        if isinstance(cmd, commands.Group):
            return await self.send_group_help(cmd)
        else:
            return await self.send_command_help(cmd)


class HelpCog(commands.Cog):
    """ If you need help for help, you're beyond help """
    def __init__(self, bot):
        self._original_help_command = bot.help_command
        bot.help_command = Help()
        bot.help_command.cog = self
        self.bot = bot

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    bot.add_cog(HelpCog(bot))
