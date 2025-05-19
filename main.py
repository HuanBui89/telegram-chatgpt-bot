import os
import openai
import random
import logging
import sqlite3
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)
from datetime import datetime

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Khởi tạo OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Các hằng số
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE"
]
SUGGESTIONS = [
    "Kể cho mình nghe về một ngày của bạn đi!",
    "Bạn cần giúp gì không? Mình có thể tìm thông tin, tạo ảnh, hay chỉ đơn giản là trò chuyện 😊",
    "Bạn muốn mình vẽ gì không? Thử /draw [ý tưởng của bạn]"
]

# Khởi tạo database
def init_db():
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  first_seen DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  role TEXT,
                  content TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()
await application.bot.send_message(chat_id=SOME_CHAT_ID, text="...", reply_markup=ReplyKeyboardRemove())

def save_message(user_id, role, content):
    conn = sqlite3.connect('chat_history.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    c.execute("INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
              (user_id, role, content))
    conn.commit()
    conn.close()

async def chat_with_gpt(user_id, message):
    try:
        base_prompt = {
            "role": "system",
            "content": (
                "Bạn là trợ lý Gen Z thân thiện của anh Huân Cute Phô Mai Que. Trả lời ngắn gọn, vui vẻ, dùng emoji. "
                "Không máy móc."
            )
        }

        conn = sqlite3.connect('chat_history.db')
        c = conn.cursor()
        c.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
        history = [dict(zip(['role', 'content'], row)) for row in c.fetchall()]
        conn.close()

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
        logger.error(f"GPT error: {str(e)}")
        return f"❌ Lỗi chatbot: {str(e)}"

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 Bot Help Guide:
- Chat bình thường để trò chuyện
- /reset - Xóa lịch sử chat
- /draw [mô tả] - Tạo ảnh AI
- /help - Xem hướng dẫn
- Gửi sticker để nhận sticker vui
"""
    await update.message.reply_text(help_text)

async def reset_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        conn = sqlite3.connect('chat_history.db')
        c = conn.cursor()
        c.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("🧹 Đã xoá sạch lịch sử rồi nghen~ Gõ gì đó thử đi!")
    except Exception as e:
        logger.error(f"Reset error: {str(e)}")
        await update.message.reply_text("❌ Lỗi khi reset lịch sử")

async def draw_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 Gõ nội dung cần vẽ như `/draw mèo mặc áo mưa` nha~", quote=True)
        return

    try:
        await update.message.reply_text("🖌️ Đợi xíu tui vẽ hình xịn cho nè...", quote=True)
        save_message(update.message.from_user.id, "user", f"/draw {prompt}")

        response = client.images.generate(
            prompt=f"{prompt}, anime style, colorful",
            n=1,
            size="512x512"
        )

        image_url = response.data[0].url
        await context.bot.send_photo(
            chat_id=update.message.chat.id,
            photo=image_url,
            reply_to_message_id=update.message.message_id,
            caption=f'🎨 "{prompt}"'
        )
        save_message(update.message.from_user.id, "assistant", f"[IMAGE] {prompt}")

    except Exception as e:
        logger.error(f"Draw error: {str(e)}")
        await update.message.reply_text(f"❌ Lỗi khi tạo ảnh: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    user_text = message.text.strip()
    bot_username = (await context.bot.get_me()).username

    is_group = message.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in message.text
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.username == bot_username
    )

    if is_group and not is_tagged and not is_reply_to_bot:
        return

    if is_tagged:
        user_text = user_text.replace(f"@{bot_username}", "").strip()

    try:
        if len(user_text) < 2:
            await message.reply_text(random.choice(SUGGESTIONS))
            return

        greetings = ["hi", "hello", "chào", "yo", "alo", "hey", "hê"]
        if user_text.lower().split()[0] in greetings:
            await message.reply_text(random.choice([
                "👋 Chào bạn! Mình là trợ lý ảo Gen Z nè~",
                "🙋‍♀️ Xin chào! Mình có thể giúp gì cho bạn?",
                "🤗 Chào bạn! Mình đang nghe đây!"
            ]))
            return

        troll_words = ["=))", "haha", "kkk", ":v", "🤣", "troll", "đùa"]
        if any(word in user_text.lower() for word in troll_words):
            await context.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=random.choice(STICKERS),
                reply_to_message_id=message.message_id
            )

        reply = await chat_with_gpt(user_id, user_text)
        await message.reply_text(reply, reply_to_message_id=message.message_id)

    except Exception as e:
        logger.error(f"Message error: {str(e)}")
        await message.reply_text("⚠️ Bot bị lỗi, thử lại sau nha!", reply_to_message_id=message.message_id)

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_history))
    application.add_handler(CommandHandler("draw", draw_image))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
