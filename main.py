import os
import openai
import random
from telegram import Update, Sticker
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

first_time_users = set()
conversation_history = {}

# Một số sticker hài để gửi ngẫu nhiên
STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",  # mặt troll
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE",  # dơ tay
]

# Prompt định hướng phong cách trả lời
def chat_with_gpt(user_id, message):
    base_prompt = {
        "role": "system",
        "content": (
            "Bạn là một trợ lý Gen Z, trả lời ngắn gọn, vui vẻ, hài hước, đời thường. "
            "Thỉnh thoảng dùng emoji, không máy móc, không sách vở."
        )
    }

    history = conversation_history.get(user_id, [])
    history = [base_prompt] + history
    history.append({"role": "user", "content": message})

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=history
    )

    reply = response.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    conversation_history[user_id] = history[-50:]
    return reply

# /reset lệnh để xóa lịch sử
def reset_history(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    conversation_history.pop(user_id, None)
    update.message.reply_text("🧹 Okie, đã xoá lịch sử hội thoại. Bắt đầu lại nha~")

# Xử lý text
def handle_message(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id
    user_text = message.text.strip()
    bot_username = context.bot.username

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
        if user_id not in first_time_users:
            first_time_users.add(user_id)

        greeting_keywords = ["hi", "hello", "chào", "yo", "hê", "hey", "alo"]
        if user_text.lower() in greeting_keywords:
            message.reply_text(
                "👋 Chào ní! Tôi là trợ lý Gen Z của anh Huân nè 👀",
                reply_to_message_id=message.message_id
            )
            return

        # 🎨 Nếu có yêu cầu "vẽ", gửi hình minh hoạ (dùng ảnh mẫu cho đơn giản)
        if any(kw in user_text.lower() for kw in ["vẽ", "hình ảnh", "minh họa"]):
            message.reply_text("🎨 Đây nè, hình minh họa sương sương cho bạn~", reply_to_message_id=message.message_id)
            context.bot.send_photo(
                chat_id=message.chat.id,
                photo="https://placekitten.com/400/300",  # Ảnh mẫu ngẫu nhiên (có thể thay bằng API Image)
                reply_to_message_id=message.message_id
            )
            return

        # 😂 Nếu người dùng gửi gì vui → gửi sticker ngẫu nhiên
        if any(word in user_text.lower() for word in ["=))", "haha", "kkk", ":v", "🤣", "đùa", "troll"]):
            context.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=random.choice(STICKERS),
                reply_to_message_id=message.message_id
            )

        # 🤖 Gửi phản hồi GPT
        reply = chat_with_gpt(user_id, user_text)
        message.reply_text(reply, reply_to_message_id=message.message_id)

    except Exception as e:
        message.reply_text("⚠️ Lỗi rồi nè: " + str(e), reply_to_message_id=message.message_id)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Thêm lệnh reset
    dp.add_handler(CommandHandler("reset", reset_history))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
