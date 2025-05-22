import os
import openai
import random
import logging
import sqlite3
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from datetime import datetime
from google_search import google_search, needs_web_search

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# OpenAI client
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Constants
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE"
]
SUGGESTIONS = [
    "Bạn cần giúp gì không? Mình có thể tìm thông tin, tạo ảnh, hay chỉ đơn giản là trò chuyện 😊",
    "Bạn muốn mình vẽ gì không? Thử /draw [ý tưởng của bạn]",
    "Kể cho mình nghe về một ngày của bạn đi!"
]

# Database setup
def init_db():
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def save_message(user_id, role, content):
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    c.execute("INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
              (user_id, role, content))
    conn.commit()
    conn.close()

# GPT + Google
async def chat_with_gpt(user_id, message):
    try:
        base_prompt = {
            "role": "system",
            "content": (
                "Bạn là trợ lý Gen Z thân thiện của anh Huân Cute Phô Mai Que. "
                "Trả lời ngắn gọn, vui vẻ, dùng emoji. Nếu có thông tin từ internet thì dùng."
            )
        }

        conn = sqlite3.connect('chat_history.db')
        c = conn.cursor()
        c.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
        history = [dict(zip(['role', 'content'], row)) for row in c.fetchall()]
        conn.close()

        web_result = ""
        if needs_web_search(message):
            web_result = google_search(message)
            message = f"📡 Tìm được từ Google:\n{web_result}\n\n👉 Câu hỏi: {message}"
            save_message(user_id, "system", f"[WEB SEARCH]\n{web_result}")

        messages = [base_prompt] + history
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )

        reply = response.choices[0].message.content
        save_message(user_id, "user", message)
        save_message(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logger.exception("GPT error")
        return "❌ Bot bị lỗi khi xử lý. Thử lại sau nha."

# Commands
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 Hướng dẫn sử dụng:
- Chat để trò chuyện
- /reset – Xóa lịch sử chat
- /help – Xem hướng dẫn
- /draw [mô tả] – Tạo ảnh AI
""")

async def reset_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        conn = sqlite3.connect('chat_history.db')
        c = conn.cursor()
        c.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("🧹 Đã xóa sạch lịch sử rồi nghen~ Gõ gì đó thử đi!")
    except Exception as e:
        logger.error(f"Reset error: {str(e)}")
        await update.message.reply_text("❌ Lỗi khi reset lịch sử")

# Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    user_text = message.text.strip()
    bot_username = (await context.bot.get_me()).username

    is_group = message.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in message.text
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.username == bot_username

    if is_group and not is_tagged and not is_reply_to_bot:
        return

    if is_tagged:
        user_text = user_text.replace(f"@{bot_username}", "").strip()

    try:
        if len(user_text) < 2:
            await message.reply_text(random.choice(SUGGESTIONS))
            return

        greetings = ["hi", "hello", "chào", "yo", "alo", "hey"]
        if user_text.lower().split()[0] in greetings:
            await message.reply_text(random.choice([
                "👋 Chào bạn! Mình là trợ lý ảo Gen Z nè~",
                "🙋‍♀️ Xin chào! Mình có thể giúp gì cho bạn?",
                "🤗 Chào bạn! Mình đang nghe đây!"
            ]))
            return

        troll_words = ["=))", "haha", ":v", "🤣", "troll", "đùa"]
        if any(word in user_text.lower() for word in troll_words):
            await context.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=random.choice(STICKERS),
                reply_to_message_id=message.message_id
            )

        reply = await chat_with_gpt(user_id, user_text)
        await message.reply_text(reply, reply_to_message_id=message.message_id)

    except Exception as e:
        logger.exception("Message error")
        await message.reply_text("⚠️ Bot bị lỗi, thử lại sau nha!")

# Main runner
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
