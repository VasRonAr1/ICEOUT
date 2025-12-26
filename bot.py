

import logging
import os
import json
import asyncio
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ChatMemberHandler
)
from telegram.error import RetryAfter, Forbidden, BadRequest

BOT_TOKEN = '7890125145:AAErI0CeqVg_5YwDxrGfMJ_0PgnANtGj20U'
DATA_FILE = 'registered_chats.json'

ALLOWED_USERNAMES = {'Kekdkddkfk', 'SpammBotsss', 'Ujuvd', 'evenyqlp'}
BLOCKED_USER_IDS = {6681493700}

# ---------- STORAGE ----------

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        registered_chats = set(tuple(x) for x in json.load(f))
else:
    registered_chats = set()

user_data = {}
active_sessions = {i: False for i in range(1, 11)}
scheduled_jobs = {i: None for i in range(1, 11)}

# ---------- LOGGING ----------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ---------- ACCESS ----------

def access_denied(user_id, username):
    return user_id in BLOCKED_USER_IDS or (username and username not in ALLOWED_USERNAMES)

# ---------- UI ----------

async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for i in range(1, 11, 2):
        row = []
        for j in (i, i + 1):
            if j <= 10:
                label = f"Spam {j} {'✅' if active_sessions[j] else ''}"
                row.append(InlineKeyboardButton(label, callback_data=f"spam_{j}"))
                if active_sessions[j]:
                    row.append(InlineKeyboardButton(f"Stop {j}", callback_data=f"stop_{j}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("📂 Chats ansehen", callback_data='view_chats')])
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text("📋 Aktion wählen:", reply_markup=markup)
    else:
        await update.message.reply_text("📋 Aktion wählen:", reply_markup=markup)

# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return

    u = update.effective_user
    if access_denied(u.id, u.username):
        await update.message.reply_text("Zugriff verweigert.")
        return

    await send_menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot zum geplanten Posten in Gruppen.")

# ---------- BUTTONS ----------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    u = q.from_user
    if access_denied(u.id, u.username):
        await q.message.reply_text("Zugriff verweigert.")
        return

    if q.data.startswith("spam_"):
        session = int(q.data.split("_")[1])
        if active_sessions[session]:
            await q.message.reply_text("Dieser Spam läuft bereits.")
        else:
            user_data[u.id] = {'state': 'awaiting_message', 'session': session}
            await q.message.reply_text(f"Nachricht für Spam {session} senden.")
        await send_menu(update, context)

    elif q.data.startswith("stop_"):
        session = int(q.data.split("_")[1])
        if scheduled_jobs[session]:
            scheduled_jobs[session].schedule_removal()
            scheduled_jobs[session] = None
        active_sessions[session] = False
        await q.message.reply_text(f"Spam {session} gestoppt.")
        await send_menu(update, context)

    elif q.data == "view_chats":
        if not registered_chats:
            await q.message.reply_text("Keine Chats.")
        else:
            txt = "\n".join(f"{t} ({i})" for i, t in registered_chats)
            await q.message.reply_text(txt)

# ---------- MESSAGE INPUT ----------

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if access_denied(u.id, u.username):
        return

    if u.id not in user_data or user_data[u.id]['state'] != 'awaiting_message':
        return

    session = user_data[u.id]['session']
    message = update.message

    job = context.job_queue.run_repeating(
        send_scheduled_message,
        interval=10 * 60,
        first=(session - 1) * 60,
        data={
            'message': message,
            'session': session
        }
    )

    scheduled_jobs[session] = job
    active_sessions[session] = True
    user_data[u.id]['state'] = None

    await update.message.reply_text(f"Spam {session} gestartet.")
    await send_menu(update, context)

# ---------- SPAM CORE ----------

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    message = data['message']
    session = data['session']

    chats = list(registered_chats)
    logging.info(f"Spam {session}: {len(chats)} chats")

    for chat_id, title in chats:
        try:
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            logging.info(f"OK → {title}")
            await asyncio.sleep(random.uniform(3, 5))

        except RetryAfter as e:
            wait = int(e.retry_after) + 5
            logging.warning(f"FloodWait {wait}s")
            await asyncio.sleep(wait)

        except Forbidden:
            logging.error(f"Forbidden → {title}")

        except BadRequest as e:
            logging.error(f"BadRequest → {title}: {e}")

        except Exception as e:
            logging.error(f"Error → {title}: {e}")

# ---------- CHAT TRACKING ----------

async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.my_chat_member
    chat = m.chat
    cid = chat.id
    title = chat.title or str(cid)

    if m.new_chat_member.status in ('member', 'administrator'):
        registered_chats.add((cid, title))
    elif m.new_chat_member.status in ('left', 'kicked'):
        registered_chats.discard((cid, title))

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(registered_chats), f, ensure_ascii=False)

# ---------- MAIN ----------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), receive_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
