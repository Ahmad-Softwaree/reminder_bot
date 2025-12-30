import logging
import os
from datetime import timedelta

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import re
from datetime import datetime, timedelta
from database.db import get_connection
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---- STATES ----
WAITING_FOR_TEXT = "WAITING_FOR_TEXT"
WAITING_FOR_MINUTES = "WAITING_FOR_MINUTES"
ADD_REMINDER_BTN_TEXT = 'Add a reminder'
CANCEL_BTN_TEXT = 'Cancel'
USER_STATE = "state"
USER_REMINDER_TEXT = 'reminder_text'
JOB_NAME= 'reminder_'


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            remind_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
    )
    print('Tables Initialized')

    conn.commit()
    cur.close()
    conn.close()


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


def get_user_reminders(user_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, text, remind_at
        FROM reminders
        WHERE user_id = %s AND remind_at > NOW()
        ORDER BY remind_at
        """,
        (user_id,)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = get_user_reminders(update.effective_user.id)

    if not reminders:
        await update.message.reply_text("You have no upcoming reminders.")
        return

    msg = "⏰ Your upcoming reminders:\n\n"
    for i, (_, text, time) in enumerate(reminders, start=1):
        msg += f"{i}. {text} — {time.strftime('%H:%M')}\n"

    await update.message.reply_text(msg)




async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start - show menu\n"
        "/help - help\n\n"
        "/cancel - cancel\n\n"
        "/list - show list\n\n"
        "Use: Add a reminder → type text → type minutes"
    )



# QUEUE JOBS

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data['chat_id']
    text = job.data["text"]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ Reminder:\n{text}",
    )

# QUEUE JOBS




# DATABASE FUNCTIONS
def save_reminder(user_id, chat_id, text, remind_at):
    conn = get_connection()
    # Cursor is the object that let you exicute mysql commands
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO reminders (user_id, chat_id, text, remind_at)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,

        (user_id, chat_id, text, remind_at)
    )
    reminder_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()


def delete_reminder(reminder_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
    conn.commit()
    cur.close()
    conn.close()


# DATABASE FUNCTIONS



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Canceled ✅", reply_markup=main_menu())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").strip()

    # Cancel from keyboard
    if msg.lower() == CANCEL_BTN_TEXT.lower().strip():
        return await cancel(update, context)

    state = context.user_data.get(USER_STATE)

    # 1) User pressed "Add a reminder"
    if msg == ADD_REMINDER_BTN_TEXT.lower().strip() and not state:
        context.user_data[USER_STATE] = WAITING_FOR_TEXT
        await update.message.reply_text(
            "Cool ✅\nWhat should I remind you about?",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # 2) Waiting for reminder text
    if state == WAITING_FOR_TEXT:
        context.user_data[USER_REMINDER_TEXT] = msg
        context.user_data[USER_STATE] = WAITING_FOR_MINUTES
        await update.message.reply_text(
            "Nice. In how many minutes? (example: 5)",
        )
        return

    # 3) Waiting for minutes
    if state == WAITING_FOR_MINUTES:
        if not msg.isdigit():
            await update.message.reply_text("Please enter a number like 5 🙂")
            return

        minutes = int(msg)
        if minutes <= 0 or minutes > 24 * 60:
            await update.message.reply_text("Enter minutes between 1 and 1440 (24h).")
            return

        reminder_text = context.user_data.get(USER_REMINDER_TEXT)
        remind_at = datetime.now() + timedelta(minutes=minutes)
        save_reminder(update.effective_user.id, update.effective_chat.id, reminder_text, remind_at)

        # Schedule job
        context.job_queue.run_once(
            reminder_job,
            when=timedelta(minutes=minutes),
            data={"chat_id": update.effective_chat.id, "text": reminder_text},
            name=f"{JOB_NAME}{update.effective_chat.id}",
        )

        context.user_data.clear()
        await update.message.reply_text(
            f"✅ Done! I’ll remind you in {minutes} minute(s).",
            reply_markup=main_menu(),
        )
        return

    # Default (no state) -> show menu
    await update.message.reply_text(
        "Choose an option:",
        reply_markup=main_menu(),
    )


def main_menu():
    keyboard = [[KeyboardButton(ADD_REMINDER_BTN_TEXT)], [KeyboardButton(CANCEL_BTN_TEXT)],[KeyboardButton('/help')],[KeyboardButton('/cancel')],[KeyboardButton('/list')]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()
    await update.message.reply_text(
        f"Hi {user.first_name}! 🤖\nI can remind you of something.",
        reply_markup=main_menu(),
    )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN is missing. Set it as an environment variable.")

    app = Application.builder().token(TOKEN).build()

    init_db()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Optional: /cancel command
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("list", list_reminders))
    # All text goes here (instead of echo)
    # So this only accept TEXT and not COMMANDS
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


# __name__ in python is the file name
if __name__ == "__main__":
    main()