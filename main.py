import os
import openai
import random
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

first_time_users = set()
conversation_history = {}

STICKERS = [
    "CAACAgUAAxkBAAEKoHhlg1I4Q2w4o0zMSrcjC3fycqQZlwACRQEAApbW6FYttxIfTrbN6jQE",
    "CAACAgUAAxkBAAEKoH1lg1JY1LtONXyA-VOFe4LEBd6gxgACawEAApbW6FYP4EL9Hx_aVjQE"
]

def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            ["📦 Còn hàng không?", "🧾 Hướng dẫn mua"],
            ["📍 Địa chỉ cửa hàng", "🎨 Vẽ hình"]
        ],
        resize_keyboard=True
    )

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

def reset_history(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    conversation_history.pop(user_id, None)
    update.message.reply_text("🧹 Đã xoá lịch sử. Mình bắt đầu lại từ đầu nha~", reply_markup=get_main_menu())

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

        # Phản hồi chào nếu user nói hi/hello/chào...
        greeting_keywords = ["hi", "hello", "chào", "yo", "hê", "hey", "alo"]
        if user_text.lower() in greeting_keywords:
            message.reply_text(
                "👋 Chào ní! Tôi là trợ lý Gen Z của anh Huân nè 👀",
                reply_to_message_id=message.message_id,
                reply_markup=get_main_menu()
            )
            return

        # Gửi ảnh nếu có từ khóa "vẽ", "hình ảnh", "minh hoạ"
        if any(kw in user_text.lower() for kw in ["vẽ", "hình ảnh", "minh họa", "minh hoạ"]):
            message.reply_text("🎨 Đây nè, hình minh họa sương sương cho bạn~", reply_to_message_id=message.message_id)
            context.bot.send_photo(
                chat_id=message.chat.id,
                photo="https://i.imgur.com/uX5BHoV.jpg",  # ảnh mèo thật
                reply_to_message_id=message.message_id
            )
            return

        # Gửi sticker nếu người dùng nói đùa
        if any(word in user_text.lower() for word in ["=))", "haha", "kkk", ":v", "🤣", "troll", "đùa"]):
            context.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=random.choice(STICKERS),
                reply_to_message_id=message.message_id
            )

        # Nếu nhấn nút menu → xử lý đặc biệt
        if user_text == "📦 Tác vụ nhanh":
            message.reply_text("Tính năng mới sẽ update sau", reply_to_message_id=message.message_id)
            return
      
        elif user_text == "🎨 Vẽ hình":
            message.reply_text("Bạn muốn vẽ gì nè? Gõ thêm ví dụ: 'vẽ con mèo' nha~", reply_to_message_id=message.message_id)
            return

        # Trả lời bằng GPT
        reply = chat_with_gpt(user_id, user_text)
        message.reply_text(reply, reply_to_message_id=message.message_id, reply_markup=get_main_menu())

    except Exception as e:
        message.reply_text(f"⚠️ Lỗi rồi nè: {str(e)}", reply_to_message_id=message.message_id)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("reset", reset_history))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
