from telegram.ext import ContextTypes
from utils.constants import (
    JOB_TEXT,
    JOB_CHAT_ID
)


async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data[JOB_CHAT_ID]
    text = job.data[JOB_TEXT]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ Reminder:\n{text}",
    )
