import logging
import os
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.error import TimedOut, NetworkError

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from utils.job import (reminder_job)
from utils.constants import (
    ADD_REMINDER,
    WAITING_FOR_MINUTES,
    USER_STATE,
    USER_REMINDER_TEXT,
    REMINDER_JOB_QUEUE,
    ADD_REMINDER_BTN_TEXT,
    CANCEL_BTN_TEXT,
    HELP_BTN_TEXT,
    LIST_BTN_TEXT,
    DELETE_BTN_TEXT,
    START_BTN_TEXT,
    RETURN_BTN_TEXT, DELETE_REMINDER, SHOW_STATUS_BTN_TEXT, START_CMD, ADD_REMINDER_CMD, LIST_CMD, DELETE_CMD,
    SHOW_STATUS_CMD, HELP_CMD, CANCEL_CMD, RETURN_CMD
)
from datetime import datetime, timedelta
from telegram.request import HTTPXRequest
from database.actions import (
    init_db,
    db_insert_reminder,
    db_get_user_reminders, db_delete_reminder, db_find_reminder_by_id, db_get_status_counts
)
from utils.helpers import (safe_reply, global_error_handler, check_is_digit_input)

request = HTTPXRequest(
    connect_timeout=10,
    read_timeout=10,
    write_timeout=10,
    pool_timeout=10,
)

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = db_get_user_reminders(update.effective_user.id)

    if not reminders:
        await safe_reply(update, "You have no upcoming reminders.")
        return
    now = datetime.now()
    msg = "⏰ Your upcoming reminders:\n\n"
    for i, (_, text, remind_at) in enumerate(reminders, start=1):
        remaining = remind_at - now
        minutes_left = max(0, int(remaining.total_seconds() // 60))

        formatted_time = remind_at.strftime("%I:%M %p")  # AM / PM

        msg += f"📝 {i}. {text}\n"
        msg += f"⏱ {formatted_time} — ⏳ {minutes_left} min left\n\n"

    await safe_reply(update, msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update,
        "📖 *Commands*\n\n"
        f"/{START_CMD} – Show menu\n"
        f"/{LIST_CMD} – List reminders\n"
        f"/{ADD_REMINDER_CMD} – Add reminder\n"
        f"/{DELETE_CMD} – Delete reminder\n"
        f"/{SHOW_STATUS_CMD} – Show stats\n"
        f"/{HELP_CMD} – Help\n"
        f"/{CANCEL_CMD} – Cancel\n",
        parse_mode="Markdown"
    )


async def cancel_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await safe_reply(update, "Canceled ✅", reply_markup=main_menu(context))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").strip().lower()
    state = context.user_data.get(USER_STATE)
    if state == ADD_REMINDER:
        context.user_data[USER_REMINDER_TEXT] = msg
        context.user_data.__setitem__(USER_STATE, WAITING_FOR_MINUTES)
        await safe_reply(update,
                         "Nice. In how many minutes? (example: 5)",
                         )
        return

    # 2) Waiting for minutes
    if state == WAITING_FOR_MINUTES:
        if not await check_is_digit_input(update, msg):
            return
        minutes = int(msg)
        if minutes <= 0 or minutes > 24 * 60:
            await safe_reply(update, "Enter minutes between 1 and 1440 (24h).")
            return

        reminder_text = context.user_data.get(USER_REMINDER_TEXT)
        remind_at = datetime.now() + timedelta(minutes=minutes)
        db_insert_reminder(update.effective_user.id, update.effective_chat.id, reminder_text, remind_at)

        # Schedule job
        context.job_queue.run_once(
            reminder_job,
            when=timedelta(minutes=minutes),
            data={"chat_id": update.effective_chat.id, "text": reminder_text},
            name=f"{REMINDER_JOB_QUEUE}{update.effective_chat.id}",
        )

        context.user_data.clear()
        await safe_reply(update,
                         f"✅ Done! I’ll remind you in {minutes} minute(s).",
                         reply_markup=main_menu(context),
                         )
        return

    # 3 Delete a reminder
    if state == DELETE_REMINDER:
        if not await check_is_digit_input(update, msg):
            return
        reminder = db_find_reminder_by_id(msg)
        if not reminder:
            await safe_reply(update, "There is no reminder with that id.")
        else:
            db_delete_reminder(msg, update.effective_user.id)
        context.user_data.clear()

    # Default (no state) -> show menu
    await safe_reply(update,
                     "Choose an option:",
                     reply_markup=main_menu(context),
                     )


async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[USER_STATE] = DELETE_REMINDER
    reminders = db_get_user_reminders(update.effective_user.id)

    if not reminders:
        context.user_data[USER_STATE] = ""
        await safe_reply(update, "You have no reminders to delete.")

    msg = "⏰ Your reminders:\n\n"
    for i, (_, text, time) in enumerate(reminders, start=1):
        msg += f"{i}. {text} — {time.strftime('%H:%M')}\n"

    await safe_reply(update,
                     "Cool ✅\nWhich Reminder Should i delete? (Id)\n" + msg,
                     reply_markup=main_menu(context),
                     )

    return


async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[USER_STATE] = ADD_REMINDER
    await safe_reply(update,
                     "Cool ✅\nWhat should I remind you about?",
                     reply_markup=main_menu(context),
                     )
    return


async def return_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[USER_STATE] = ""
    await safe_reply(update, "Returned", reply_markup=main_menu(context))


async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active, completed, total = db_get_status_counts(update.effective_user.id)

    msg = (
        "📊 *Your Reminder Status*\n\n"
        f"🟢 Active: {active}\n"
        f"✅ Completed: {completed}\n"
        f"📦 Total: {total}\n"
    )

    await safe_reply(update, msg, parse_mode="Markdown")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()
    await safe_reply(
        update,
        f"Hi {user.first_name}! 🤖\nI can remind you of something.",
        reply_markup=main_menu(context),
    )


def main_menu(context: ContextTypes.DEFAULT_TYPE):
    startBtn = [KeyboardButton(f"/{START_CMD} {START_BTN_TEXT}")]
    addReminderBtn = [KeyboardButton(f"/{ADD_REMINDER_CMD} {ADD_REMINDER_BTN_TEXT}")]
    showListBtn = [KeyboardButton(f"/{LIST_CMD} {LIST_BTN_TEXT}")]
    deleteReminderBtn = [KeyboardButton(f"/{DELETE_CMD} {DELETE_BTN_TEXT}")]
    showStatusBtn = [KeyboardButton(f"/{SHOW_STATUS_CMD} {SHOW_STATUS_BTN_TEXT}")]
    cancelBtn = [KeyboardButton(f"/{CANCEL_CMD} {CANCEL_BTN_TEXT}")]
    helpListBtn = [KeyboardButton(f"/{HELP_CMD} {HELP_BTN_TEXT}")]
    returnBtn = [KeyboardButton(f"/{RETURN_CMD} {RETURN_BTN_TEXT}")]

    normalKeyboard = [
        startBtn,
        showStatusBtn,
        showListBtn,
        addReminderBtn,
        deleteReminderBtn,
        cancelBtn,
        helpListBtn,
    ]
    dbOperationKeyboadrd = [
        returnBtn,
        cancelBtn
    ]

    state = context.user_data.get(USER_STATE)
    if state == ADD_REMINDER or state == DELETE_REMINDER:
        keyboard = dbOperationKeyboadrd
    else:
        keyboard = normalKeyboard

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN is missing. Set it as an environment variable.")

    app = Application.builder().token(TOKEN).request(request).build()

    init_db()

    app.add_handler(CommandHandler(START_CMD, start))
    app.add_handler(CommandHandler(HELP_CMD, help_command))
    app.add_handler(CommandHandler(CANCEL_CMD, cancel_bot))
    app.add_handler(CommandHandler(LIST_CMD, list_reminders))
    app.add_handler(CommandHandler(DELETE_CMD, delete_reminder))
    app.add_handler(CommandHandler(ADD_REMINDER_CMD, add_reminder))
    app.add_handler(CommandHandler(RETURN_CMD, return_btn))
    app.add_handler(CommandHandler(SHOW_STATUS_CMD, show_status))
    app.add_error_handler(global_error_handler)

    # All text goes here (instead of echo)
    # So this only accept TEXT and not COMMANDS
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


# __name__ in python is the file name
if __name__ == "__main__":
    main()
