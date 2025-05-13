import os
import openai
import random
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

# Lấy token từ biến môi trường
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Ghi nhớ người dùng và lịch sử hội thoại
first_time_users = set()
conversation_history = {}

# Sticker vui
STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE"
]

# Trả lời bằng ChatGPT
def chat_with_gpt(user_id, message):
    base_prompt = {
        "role": "system",
        "content": (
            "Bạn là một trợ lý Gen Z siêu thân thiện, trả lời ngắn gọn, vui vẻ, đời thường. "
            "Dùng emoji khi phù hợp. Không nói chuyện kiểu máy móc hay giáo điều."
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

# Lệnh /reset
def reset_history(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    conversation_history.pop(user_id, None)
    update.message.reply_text("🧹 Đã xoá sạch lịch sử rồi nghen~ Gõ gì đó thử đi!")

# Lệnh /draw để tạo ảnh AI từ DALL·E
def draw_image(update: Update, context: CallbackContext):
    prompt = " ".join(context.args)

    if not prompt:
        update.message.reply_text("🎨 Gõ nội dung cần vẽ như `/draw mèo mặc áo mưa` nha~", quote=True)
        return

    try:
        update.message.reply_text("🖌️ Đợi xíu tui vẽ hình xịn cho nè...", quote=True)

        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="512x512"
        )

        image_url = response["data"][0]["url"]
        context.bot.send_photo(
            chat_id=update.message.chat.id,
            photo=image_url,
            reply_to_message_id=update.message.message_id
        )

    except Exception as e:
        update.message.reply_text(f"❌ Lỗi vẽ hình: {e}")

# Xử lý tin nhắn văn bản thường
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
        # Ghi nhận người dùng mới
        if user_id not in first_time_users:
            first_time_users.add(user_id)

        # 👋 Nếu là lời chào
        if user_text.lower() in ["hi", "hello", "chào", "yo", "alo", "hey", "hê"]:
            message.reply_text(
                "👋 Chào ní! Tôi là trợ lý Gen Z của anh Huân nè 👀",
                reply_to_message_id=message.message_id
            )
            return

        # 😂 Nếu là tin troll → gửi sticker
        if any(word in user_text.lower() for word in ["=))", "haha", "kkk", ":v", "🤣", "troll", "đùa"]):
            context.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=random.choice(STICKERS),
                reply_to_message_id=message.message_id
            )

        # 🤖 Trả lời bằng ChatGPT
        reply = chat_with_gpt(user_id, user_text)
        message.reply_text(reply, reply_to_message_id=message.message_id)

    except Exception as e:
        message.reply_text(f"⚠️ Lỗi rồi nè: {str(e)}", reply_to_message_id=message.message_id)

# Chạy bot
def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("reset", reset_history))
    dp.add_handler(CommandHandler("draw", draw_image))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
