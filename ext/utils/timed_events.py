import datetime
import discord
from discord.utils import sleep_until


async def parse_time(time):
	delta = datetime.timedelta()
	if "d" in time:
		d, time = time.split("d")
		delta += datetime.timedelta(days=int(d))
	if "h" in time:
		h, time = time.split("h")
		delta += datetime.timedelta(hours=int(h))
	if "m" in time:
		m, time = time.split("m")
		delta += datetime.timedelta(minutes=int(m))
	if "s" in time:
		s = time.split("s")[0]
		delta += datetime.timedelta(seconds=int(s))
	return delta


async def spool_reminder(bot, record):
	# Get data from records
	channel = bot.get_channel(record['channel_id'])
	msg = await channel.fetch_message(record['message_id'])
	user_id = record["user_id"]
	try:
		mention = channel.guild.get_member(user_id).mention
	except AttributeError:  # no guild
		mention = channel.recipient.mention
	
	await sleep_until(record["target_time"])
	
	e = discord.Embed()
	e.timestamp = record['created_time']
	e.colour = 0x00ff00
	
	e.title = "⏰ Reminder"
	
	if record['reminder_content'] is not None:
		e.description = "> " + record['reminder_content']
	
	if record['mod_action'] is not None:
		if record['mod_action'] == "unban":
			try:
				await bot.http.unban(record["mod_target"], channel.guild)
				e.description = f'\n\nUser id {record["mod_target"]} was unbanned'
			except discord.NotFound:
				e.description = f"  \n\nFailed to unban user id {record['mod_target']} - are they already unbanned?"
				e.colour = 0xFF0000
			else:
				e.title = "Member unbanned"
		elif record['mod_action'] == "unmute":
			muted_role = discord.utils.get(channel.guild.roles, name="Muted")
			target = channel.guild.get_member(record["mod_target"])
			try:
				await target.remove_roles(muted_role, reason="Unmuted")
			except discord.Forbidden:
				e.description = f"Unable to unmute {target.mention}"
				e.colour = 0xFF0000
			else:
				e.title = "Member un-muted"
				e.description = f"{target.mention}"
		elif record['mod_action'] == "unblock":
			target = channel.guild.get_member(record["mod_target"])
			await channel.set_permissions(target, overwrite=None)
			e.title = "Member un-blocked"
			e.description = f"Unblocked {target.mention} from {channel.mention}"
	
	try:
		e.description += f"\n[Jump to reminder]({msg.jump_url})"
	except AttributeError:
		pass
	
	if record['mod_action']:
		await channel.send(embed=e)
	else:
		try:
			await channel.send(mention, embed=e)
		except discord.NotFound:
			try:
				await bot.get_user(user_id).send(mention, embed=e)
			except discord.Forbidden:
				pass
	
	connection = await bot.db.acquire()
	await connection.execute("""DELETE FROM reminders WHERE message_id = $1""", record['message_id'])
	await bot.db.release(connection)
