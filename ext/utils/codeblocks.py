import datetime
import traceback


def time_to_colour(timestamp: datetime.datetime) -> str:
    time_delta = datetime.datetime.now() - timestamp
    if time_delta.total_seconds() < 600:  # 10 minutes
        coloured_time = f"```css\n[{timestamp}]```"  # red
    elif time_delta.total_seconds() < 1440:  # 1 day
        coloured_time = f"```fix\n[{timestamp}]```"  # yellow
    elif time_delta.total_seconds() < 604800:  # 1 week
        coloured_time = f"```glsl\n[{timestamp}]```"  # grey
    elif time_delta.total_seconds() < 2419200:  # 1 month
        coloured_time = f"```yaml\n[{timestamp}]```"  # cyan
    elif time_delta.total_seconds() < 15780000:  # 6 months
        coloured_time = f"```CSS\n{timestamp}```"  # green
    else:
        coloured_time = f"```ini\n[{timestamp}]```"  # blue
    return coloured_time


def error_to_codeblock(error):
    return f':no_entry_sign: {type(error).__name__}: {error}```py\n' \
           f'{"".join(traceback.format_exception(type(error), error, error.__traceback__))}```'
    pass
