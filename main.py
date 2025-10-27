import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import os

# =============================
# 🔧 Cấu hình
# =============================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # đặt trong Railway hoặc .env
BOT_TOKEN = os.getenv("BOT_TOKEN")  # token Telegram bot
MODEL_NAME = "gpt-5"  # hoặc "gpt-4o-mini" nếu dùng bản tiết kiệm hơn

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =============================
# 🤖 Hàm gọi GPT
# =============================
async def chat_with_gpt(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Bạn là Huan's AI Assistant, trả lời tự nhiên, thân thiện, thông minh và luôn giúp người dùng tối ưu công việc."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Lỗi khi gọi OpenAI API: {e}")
        return "⚠️ Xin lỗi, hệ thống tạm thời gặp lỗi khi xử lý yêu cầu. Bạn thử lại sau vài giây nhé!"

# =============================
# 📩 Xử lý tin nhắn Telegram
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xin chào 👋 Mình là Huan’s AI Assistant — trợ lý ảo thông minh của bạn. Bạn cần hỗ trợ gì hôm nay?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logging.info(f"Người dùng: {user_text}")
    
    reply = await chat_with_gpt(user_text)
    await update.message.reply_text(reply)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(msg="Lỗi cập nhật:", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text("❌ Xin lỗi, mình gặp lỗi khi xử lý. Thử lại nhé!")

# =============================
# 🚀 Khởi chạy bot
# =============================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Bot đang chạy... Sẵn sàng nhận tin nhắn!")
    app.run_polling()
