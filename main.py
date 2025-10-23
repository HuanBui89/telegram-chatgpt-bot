# main.py
import os
import asyncio
import logging
import aiosqlite
import random
from datetime import datetime, timedelta
from functools import wraps

import openai
from telegram import Update
from telegram.constants import ChatAction

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------------
# Config & Logging
# -------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "chat_history.db")
# Optional: override model names via env
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-3.5-turbo")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")

if not OPENAI_API_KEY or not TELEGRAM_TOKEN:
    logger.error("OPENAI_API_KEY and TELEGRAM_TOKEN must be set in environment.")
    raise SystemExit("Missing environment variables")

# OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Small UX texts
SUGGESTIONS = [
    "Bạn cần giúp gì? Mình có thể tìm thông tin, tạo ảnh, hoặc trò chuyện 😊",
    "Thử gõ /draw [mô tả] để mình vẽ ảnh AI cho bạn!",
    "Kể mình nghe một chuyện thú vị đi 😄",
]

STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE",
]

# Rate limiting in-memory (simple)
USER_COOLDOWN = {}  # user_id -> datetime of allowed next request
COOLDOWN_SECONDS = 1.0  # small per-message throttle

# -------------------------
# DB helpers (aiosqlite)
# -------------------------
CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_CONVERSATIONS_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS_SQL)
        await db.execute(CREATE_CONVERSATIONS_SQL)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_time ON conversations(user_id, timestamp DESC);")
        await db.commit()

asyncio.get_event_loop().run_until_complete(init_db())

async def save_message(user_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await db.commit()

async def fetch_recent_history(user_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT role, content, timestamp FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        # return oldest->newest (reverse)
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

async def clear_history(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        await db.commit()

# -------------------------
# Utility: rate limit decorator
# -------------------------
def rate_limited(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        now = datetime.utcnow()
        allowed_at = USER_COOLDOWN.get(user_id, now)
        if now < allowed_at:
            # silently drop spammy messages (or send quick hint)
            return
        USER_COOLDOWN[user_id] = now + timedelta(seconds=COOLDOWN_SECONDS)
        return await func(update, context, *args, **kwargs)
    return wrapper

# -------------------------
# Web search integration (async stub)
# -------------------------
# IMPORTANT: Replace google_search_async with your real async implementation.
async def google_search_async(query: str) -> str:
    # Example stub: in production call an async http client (aiohttp) to your search service
    await asyncio.sleep(0.01)
    return ""  # return empty string if no web result

# Heuristic to decide if web search is needed
def needs_web_search(query: str) -> bool:
    # simple heuristic: words like "mới", "tin", "giá", "bao nhiêu", "ngày hôm nay", "CEO", "giải thưởng", "lịch"
    lower = query.lower()
    triggers = ["mới", "giá", "bao nhiêu", "hôm nay", "tin", "CEO", "giải", "lịch", "điều lệ", "luật", "số liệu"]
    return any(t in lower for t in triggers)

# -------------------------
# Prompt & summarization helpers
# -------------------------
SYSTEM_PROMPT = (
    "Bạn là một trợ lý tiếng Việt thông minh, thân thiện, dí dỏm (Gen Z style) cho anh Huân. "
    "Trả lời ngắn gọn, rõ ràng, thích ứng với bối cảnh. "
    "Khi cần, hỏi thêm 1 câu để làm rõ. Dùng emoji phù hợp, nhưng không lạm dụng. "
    "Nếu trả lời liên quan đến dữ liệu hoặc tin tức có thể thay đổi theo thời gian, nói 'Mình sẽ kiểm tra' rồi thực hiện web search nếu cần."
)

# If conversation history too long by characters, ask model to summarize (keeps context)
MAX_HISTORY_CHARS = 3000

async def maybe_summarize_history(history_messages):
    # history_messages: list of {"role","content"}
    joined = "\n".join([f"{m['role']}: {m['content']}" for m in history_messages])
    if len(joined) <= MAX_HISTORY_CHARS:
        return history_messages  # no need
    # Summarize via a short GPT call to compress prior context:
    prompt = [
        {"role": "system", "content": "Bạn là một trợ lý tóm tắt hội thoại."},
        {"role": "user", "content": "Tóm tắt ngắn (3-5 dòng) nội dung chính của đoạn hội thoại sau, giữ các thông tin quan trọng: \n\n" + joined}
    ]
    try:
        resp = client.chat.completions.create(model=CHAT_MODEL, messages=prompt, temperature=0.2)
        summary = resp.choices[0].message.content.strip()
        compressed = [{"role": "system", "content": "[TÓM TẮT LỊCH SỬ] " + summary}]
        return compressed
    except Exception as e:
        logger.exception("Error summarizing history")
        # fallback: return last N messages only
        return history_messages[-10:]

# -------------------------
# Chat with OpenAI
# -------------------------
async def chat_with_gpt(user_id: int, user_message: str):
    try:
        # fetch history from DB
        raw_history = await fetch_recent_history(user_id, limit=30)  # returns list of dicts old->new
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # map DB rows to assistant/user roles (already stored)
        history_msgs = [{"role": r["role"], "content": r["content"]} for r in raw_history]
        history_msgs = await maybe_summarize_history(history_msgs)
        messages.extend(history_msgs)

        # check web needs
        web_text = ""
        if needs_web_search(user_message):
            web_text = await google_search_async(user_message)
            if web_text:
                messages.append({"role": "system", "content": f"[WEB SEARCH RESULT]\n{web_text}"})
                # log web result
                await save_message(user_id, "system", f"[WEB SEARCH]\n{web_text}")

        messages.append({"role": "user", "content": user_message})

        # Control max tokens via reasonable defaults
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=800,
        )

        reply = response.choices[0].message.content.strip()
        # Save user & assistant messages
        await save_message(user_id, "user", user_message)
        await save_message(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logger.exception("OpenAI chat error")
        return "❌ Mình bị lỗi khi xử lý. Thử lại nhé."

# -------------------------
# /draw command (image generation)
# -------------------------
async def generate_image(prompt: str):
    try:
        resp = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1024", n=1)
        # This API may return either a url or b64, adapt as needed:
        data = resp.data[0]
        # image may be 'url' or 'b64_json'
        if hasattr(data, "url") and data.url:
            return data.url
        if "b64_json" in data:
            return data["b64_json"]
        # fallback
        return None
    except Exception as e:
        logger.exception("Image generation error")
        return None

# -------------------------
# Handlers
# -------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Xin chào {user.first_name}! Mình là trợ lý ảo — gõ gì đó đi nhé. Gõ /help để xem lệnh."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Hướng dẫn:\n"
        "- Chat trực tiếp để hỏi.\n"
        "- /reset : xóa lịch sử.\n"
        "- /draw [mô tả] : tạo ảnh AI.\n"
        "- Gửi 'hi' để nhận lời chào vui vẻ.\n"
    )

async def reset_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await clear_history(user_id)
    await update.message.reply_text("🧹 Đã xóa lịch sử chat của bạn rồi. Bắt đầu lại nhé!")

@rate_limited
async def draw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("🎨 Gõ: /draw [mô tả]. Ví dụ: /draw Người phụ nữ mặc áo dài ngồi trong quán cà phê")
        return
    prompt = " ".join(context.args)
    await update.message.reply_text("🖌️ Đang tạo ảnh... (có thể mất vài giây)")
    # send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    image_ref = await generate_image(prompt)
    if not image_ref:
        await update.message.reply_text("❌ Không tạo được ảnh. Thử mô tả khác nhé.")
        return
    # If image_ref looks like base64, we could decode and send; for simplicity assume URL:
    try:
        if image_ref.startswith("http"):
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_ref, caption=f"✨ Ảnh: {prompt}")
        else:
            # assume base64
            import base64, io
            from telegram import InputFile
            img_bytes = base64.b64decode(image_ref)
            bio = io.BytesIO(img_bytes)
            bio.name = "image.png"
            bio.seek(0)
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=InputFile(bio), caption=f"✨ Ảnh: {prompt}")
    except Exception:
        await update.message.reply_text("❌ Gửi ảnh lỗi. Bạn có thể thử lại.")

@rate_limited
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = update.effective_user.id
    text = (msg.text or "").strip()
    if not text:
        return

    # Group handling: only respond when mentioned or replied
    bot_username = (await context.bot.get_me()).username
    is_group = msg.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in text
    is_reply_to_bot = msg.reply_to_message and (msg.reply_to_message.from_user and msg.reply_to_message.from_user.username == bot_username)

    if is_group and not (is_tagged or is_reply_to_bot):
        return  # ignore other group chatter

    # Basic greetings shortcut
    greetings = ["hi", "hello", "chào", "alo", "hey", "yo"]
    if text.split()[0].lower() in greetings:
        await msg.reply_text(random.choice([
            "👋 Chào bạn! Mình ở đây nè~",
            "🙋‍♀️ Xin chào! Mình có thể giúp gì?",
            "🤗 Hehe, chào cưng! Nói gì đi nào."
        ]))
        return

    # Troll reaction: send sticker
    troll_words = ["=))", "haha", ":v", "🤣", "troll", "đùa"]
    if any(t in text.lower() for t in troll_words):
        try:
            await context.bot.send_sticker(chat_id=msg.chat.id, sticker=random.choice(STICKERS), reply_to_message_id=msg.message_id)
        except Exception:
            pass

    # Show typing
    await context.bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.TYPING)
    # Query GPT
    reply = await chat_with_gpt(user_id, text)
    # Send reply
    await msg.reply_text(reply, reply_to_message_id=msg.message_id)

# -------------------------
# Main
# -------------------------
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    # Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_history))
    application.add_handler(CommandHandler("draw", draw_command))
    # Messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
