# main.py
import os
import asyncio
import logging
import aiosqlite
import random
from datetime import datetime, timedelta
from functools import wraps
import base64
import io

import openai
from telegram import Update, InputFile
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

# Model names (you can change)
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4o")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")

if not OPENAI_API_KEY or not TELEGRAM_TOKEN:
    logger.error("OPENAI_API_KEY and TELEGRAM_TOKEN must be set in environment.")
    raise SystemExit("Missing environment variables")

# Create OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# -------------------------
# Global Natural Mode
# -------------------------
# Set to True to force the assistant to answer in a natural, conversational, human-like style,
# proactively continue previous topics, and avoid canned "Do you need anything else?" patterns.
GLOBAL_NATURAL_MODE = True

# -------------------------
# UX texts / stickers
# -------------------------
SUGGESTIONS = [
    "Bạn cần gì cứ nói, mình sẽ trả lời thoải mái, tự nhiên như người thật nhé 😊",
    "Muốn vẽ gì thì /draw [mô tả] — mình vẽ luôn cho!",
    "Bạn muốn mình tra cứu giá, tin tức, hay làm thơ? Gõ luôn đi."
]

STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE",
]

# Rate limiting
USER_COOLDOWN = {}
COOLDOWN_SECONDS = 0.6

# -------------------------
# Database (aiosqlite)
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

# initialize DB
asyncio.get_event_loop().run_until_complete(init_db())

async def save_message(user_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await db.commit()

async def fetch_recent_history(user_id: int, limit: int = 25):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT role, content, timestamp FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

async def clear_history(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        await db.commit()

# -------------------------
# Rate-limit decorator
# -------------------------
def rate_limited(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        now = datetime.utcnow()
        allowed_at = USER_COOLDOWN.get(user_id, now)
        if now < allowed_at:
            return
        USER_COOLDOWN[user_id] = now + timedelta(seconds=COOLDOWN_SECONDS)
        return await func(update, context, *args, **kwargs)
    return wrapper

# -------------------------
# Web search (async stub)
# -------------------------
# You should implement this function to actually query a web search API (SerpAPI, Google Custom, Bing, etc.)
# Return a short aggregated text (string) summarizing top findings (title + 1-2 lines each), or "" if none.
async def google_search_async(query: str) -> str:
    # Example placeholder: Implement using aiohttp + your preferred search API
    # For example, call SerpAPI or a cached endpoint and return concise summary string.
    await asyncio.sleep(0.01)
    return ""  # default: no web result

# Heuristic to decide whether to perform web search
def needs_web_search(query: str) -> bool:
    lower = (query or "").lower()
    triggers = ["hôm nay", "giá", "bao nhiêu", "mấy giờ", "tin", "giá vàng", "lăn bánh", "giá xe", "giá xăng", "tỷ giá", "CEO", "luật", "điều", "biểu giá"]
    return any(t in lower for t in triggers)

# -------------------------
# Prompt design (Natural mode)
# -------------------------
SYSTEM_PROMPT = (
    "Bạn là một trợ lý siêu thông minh, tự nhiên, trò chuyện như người thật, "
    "nhạy bén trong ngữ cảnh, biết gợi mở và nối chủ đề cũ khi phù hợp. "
    "Trả lời bằng tiếng Việt trôi chảy, có thể dùng emoji, không lặp câu hỏi 'Bạn cần gì nữa?' trừ khi thật sự cần làm rõ. "
    "Nếu cần thông tin thời sự hoặc dữ liệu có thể thay đổi, thực hiện web search và trích nguồn ngắn gọn. "
    "Khi người dùng hỏi về giá/ dữ liệu cần xác thực (ví dụ: 'giá vàng hôm nay'), hãy nói bạn sẽ kiểm tra và sau đó trả lời cập nhật."
)

# If history too long, compress it
MAX_HISTORY_CHARS = 3000

async def maybe_summarize_history(history_messages):
    joined = "\n".join([f"{m['role']}: {m['content']}" for m in history_messages])
    if len(joined) <= MAX_HISTORY_CHARS:
        return history_messages
    # Ask model to summarize (sync openai call used here — it's fine but keep tokens controlled)
    prompt = [
        {"role": "system", "content": "Bạn là 1 trợ lý tóm tắt hội thoại. Tóm tắt ngắn gọn 3-6 dòng, giữ các điểm quan trọng."},
        {"role": "user", "content": "Hội thoại cần tóm tắt:\n\n" + joined}
    ]
    try:
        resp = client.chat.completions.create(model=CHAT_MODEL, messages=prompt, temperature=0.2, max_tokens=200)
        summary = resp.choices[0].message.content.strip()
        return [{"role": "system", "content": "[TÓM TẮT LỊCH SỬ] " + summary}]
    except Exception:
        # fallback: last 12 messages
        return history_messages[-12:]

# -------------------------
# Chat with OpenAI (main)
# -------------------------
async def chat_with_gpt(user_id: int, user_message: str):
    try:
        raw_history = await fetch_recent_history(user_id, limit=30)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        history_msgs = [{"role": r["role"], "content": r["content"]} for r in raw_history]
        history_msgs = await maybe_summarize_history(history_msgs)
        messages.extend(history_msgs)

        # Web search if heuristic triggered
        web_text = ""
        if needs_web_search(user_message):
            web_text = await google_search_async(user_message)
            if web_text:
                messages.append({"role": "system", "content": f"[WEB SEARCH RESULT]\n{web_text}"})
                await save_message(user_id, "system", f"[WEB SEARCH]\n{web_text}")

        # If global natural mode, inform model to continue thread if possible
        if GLOBAL_NATURAL_MODE:
            # an instruction to keep thread continuity and be proactive
            messages.append({"role": "system", "content": "[NATURAL_MODE_ON] Hãy trả lời tự nhiên, gợi mở tiếp chủ đề nếu phù hợp."})

        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=900,
        )

        reply = response.choices[0].message.content.strip()
        # Save conversation
        await save_message(user_id, "user", user_message)
        await save_message(user_id, "assistant", reply)
        return reply
    except Exception as e:
        logger.exception("OpenAI chat error")
        return "Xin lỗi, mình gặp lỗi khi xử lý. Thử lại nhé."

# -------------------------
# Image generation
# -------------------------
async def generate_image(prompt: str):
    try:
        resp = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1024", n=1)
        data = resp.data[0]
        # try url
        if hasattr(data, "url") and data.url:
            return {"type": "url", "data": data.url}
        if "b64_json" in data:
            return {"type": "b64", "data": data["b64_json"]}
        # fallback
        return None
    except Exception:
        logger.exception("Image generation error")
        return None

# -------------------------
# Handlers
# -------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = (
        f"Xin chào {user.first_name}! Mình đang chạy ở chế độ tự nhiên — trả lời tự nhiên, "
        "liên kết chủ đề cũ, có thể tra web khi cần. Gõ /help để xem lệnh."
    )
    await update.message.reply_text(txt)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Các lệnh:\n"
        "/start - bắt đầu\n"
        "/help - trợ giúp\n"
        "/reset - xóa lịch sử\n"
        "/draw [mô tả] - tạo ảnh AI\n\n"
        "Mình trả lời tự nhiên và chủ động nối chủ đề. Hỏi thoải mái nhé!"
    )

async def reset_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await clear_history(user_id)
    await update.message.reply_text("🧹 Đã xóa lịch sử của bạn. Bắt đầu lại nhé!")

@rate_limited
async def draw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gõ: /draw [mô tả]. Ví dụ: /draw người phụ nữ mặc áo dài uống cà phê ở sân vườn")
        return
    prompt = " ".join(context.args)
    await update.message.reply_text("Đang tạo ảnh... ⏳")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    res = await generate_image(prompt)
    if not res:
        await update.message.reply_text("Không tạo được ảnh, thử mô tả khác nhé.")
        return
    try:
        if res["type"] == "url":
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=res["data"], caption=f"✨ {prompt}")
        else:
            img_bytes = base64.b64decode(res["data"])
            bio = io.BytesIO(img_bytes)
            bio.name = "image.png"
            bio.seek(0)
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=InputFile(bio), caption=f"✨ {prompt}")
    except Exception:
        await update.message.reply_text("Gửi ảnh lỗi. Bạn có thể thử lại sau.")

@rate_limited
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = update.effective_user.id
    text = (msg.text or "").strip()
    if not text:
        return

    # Group logic: respond only if mentioned or replied-to
    bot_username = (await context.bot.get_me()).username
    is_group = msg.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in text
    is_reply_to_bot = msg.reply_to_message and (msg.reply_to_message.from_user and msg.reply_to_message.from_user.username == bot_username)
    if is_group and not (is_tagged or is_reply_to_bot):
        return

    # greetings shortcuts
    greetings = ["hi", "hello", "chào", "alo", "hey", "yo"]
    if text.split()[0].lower() in greetings:
        await msg.reply_text(random.choice([
            "👋 Chào! Mình đang ở đây, muốn bắt đầu bằng chủ đề nào?",
            "Xin chào! Kể mình nghe bạn đang làm gì hôm nay nhé.",
            "Chào bạn! Muốn hỏi gì thì cứ nói thôi."
        ]))
        return

    # playful sticker on troll words
    troll_words = ["=))", "haha", ":v", "🤣", "troll", "đùa"]
    if any(t in text.lower() for t in troll_words):
        try:
            await context.bot.send_sticker(chat_id=msg.chat.id, sticker=random.choice(STICKERS), reply_to_message_id=msg.message_id)
        except Exception:
            pass

    # typing indicator
    await context.bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.TYPING)

    # Compose reply
    reply = await chat_with_gpt(user_id, text)

    # Send reply (use reply_to)
    await msg.reply_text(reply, reply_to_message_id=msg.message_id)

# -------------------------
# Run bot
# -------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_history))
    app.add_handler(CommandHandler("draw", draw_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting (Natural Mode=%s) ..." % GLOBAL_NATURAL_MODE)
    app.run_polling()

if __name__ == "__main__":
    main()
