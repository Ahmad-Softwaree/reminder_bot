from datetime import datetime, timedelta
import logging
from telegram.error import TelegramError, TimedOut, NetworkError

logger = logging.getLogger(__name__)


def parse_time_today(time_str: str):
    try:
        hour, minute = map(int, time_str.split(":"))
        now = datetime.now()
        remind_at = now.replace(hour=hour, minute=minute, second=0)

        if remind_at < now:
            remind_at += timedelta(days=1)

        return remind_at
    except:
        return None


async def safe_reply(update, text: str, **kwargs):
    """
    Safely reply to a user without crashing the bot
    """
    try:
        if not update.message:
            return
        await update.message.reply_text(text, **kwargs)

    except TimedOut:
        logger.warning("Telegram timeout while sending message")

    except NetworkError:
        logger.warning("Network error while sending message")

    except TelegramError as e:
        logger.error(f"Telegram API error: {e}")

    except Exception as e:
        logger.exception("Unexpected error while sending message")


async def global_error_handler(update, context):
    err = context.error
    logger.error(f"Update error: {err}")

    if isinstance(err, TimedOut):
        return  # Ignore silently

    if isinstance(err, NetworkError):
        return


async def check_is_digit_input(update, msg):
    if not msg.isdigit():
        await safe_reply(update, "Please enter a number")
        return False
    return True
