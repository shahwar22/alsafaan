import discord
from discord.ext import commands


def descriptor(command):
    string = f'• `{command.name}` - {command.short_doc}'
    if isinstance(command, commands.Group):
        string += f'\n***Subcommands**:* {", ".join(f"`{sub.name}`" for sub in command.commands)}'
    return string


class Help(commands.HelpCommand):
    """ The Toonbot help command. """
    def get_command_signature(self, command):
        return f'.tb {command.qualified_name} {command.signature}'
    
    async def send_bot_help(self, mapping):
        """ WIP New Help Command. """
        # Base Embed
        e = discord.Embed()
        e.set_thumbnail(url=self.context.me.avatar_url)
        e.colour = 0x2ecc71
        e.set_author(name="Toonbot Help")
        
        e.description = f"Use {self.context.prefix}help **category name** for help on a category\n" \
                        f"*Note: This is case sensitive*\n\n"
        
        cogs = [self.context.bot.get_cog(cog) for cog in self.context.bot.cogs]
        for cog in cogs:
            if not cog.get_commands():
                continue  # Filter utility cogs.
            
            for command in cog.walk_commands():
                try:
                    if await command.can_run(self.context):
                        e.description += f"**{cog.qualified_name}**: {cog.description}\n"
                        break
                except discord.ext.commands.CommandError:
                    pass
                    
        
        invite_and_stuff = f"[Invite me to your discord]" \
                           f"(https://discordapp.com/oauth2/authorize?client_id=250051254783311873" \
                           f"&permissions=67488768&scope=bot)\n"
        invite_and_stuff += f"[Join my Support discord](http://www.discord.gg/a5NHvPx)\n"
        invite_and_stuff += f"[Toonbot on Github](https://github.com/Painezor/Toonbot)"
        e.add_field(name="Useful links", value=invite_and_stuff)
        try:
            await self.context.send(embed=e)
        except discord.Forbidden:
            await self.context.author.send("I do not have permissions to send help in the channel you requested from.",
                                           embed=e)
            
    async def send_cog_help(self, cog):
        await self.context.send(embed=await self.cog_embed(cog))
    
    async def cog_embed(self, cog):
        e = discord.Embed()
        e.title = f'{cog.qualified_name} category help'
        e.colour = 0x2ecc71
        e.set_thumbnail(url=self.context.me.avatar_url)
        e.description = cog.description + "\n\n"
        e.description += '\n'.join([descriptor(command) for command in cog.get_commands() if not command.hidden])
        e.add_field(name="More help", value='Use help **command** to view the usage of that command.\n'
                                            f'Subcommands are ran by using `{self.context.prefix}command subcommand`')
        return e
    
    async def send_group_help(self, group):
        e = discord.Embed()
        e.title = f'Help for command group: {group.name.title()}'
        e.description = f"{group.help}\n```{self.get_command_signature(group)}```"
        e.colour = 0x2ecc71
        e.set_thumbnail(url=self.context.me.avatar_url)
        
        if group.aliases:
            e.description += '*Command Aliases*: ' + ', '.join([f"`{i}`" for i in group.aliases]) + "\n\n"

        e.description += "***Subcommands**:*: "
        for command in group.commands:
            cmd_string = f"{command.help} ```{self.get_command_signature(command)}```"
            
            if isinstance(command, commands.Group):
                cmd_string += "***Subcommands**:* " + ", ".join([f"`{i.name}`" for i in command.commands])
            e.add_field(name=command.name, value=cmd_string,
                        inline=False)
            
        e.add_field(name="More help", value='Use help **command** to view the usage of that command.\n'
                                            f'Subcommands are ran by using `{self.context.prefix}command subcommand`')
        e.set_footer(text='<REQUIRED argument> | [OPTIONAL argument] | Use help <command> for further info.')
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
    
    async def command_callback(self, ctx, *, command=None):
        await self.prepare_help_command(ctx, command)
        
        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)
        
        cog = ctx.bot.get_cog(command)
        
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
                    string = await discord.utils.maybe_coroutine(self.subcommand_not_found, cmd,
                                                                 self.remove_mentions(key))
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
