import os
import openai
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Lưu lịch sử và người đã từng tương tác
conversation_history = {}
first_time_users = set()

def chat_with_gpt(user_id, user_message):
    history = conversation_history.get(user_id, [])
    history.append({"role": "user", "content": user_message})

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=history
    )

    reply = response['choices'][0]['message']['content']
    history.append({"role": "assistant", "content": reply})
    conversation_history[user_id] = history[-10:]

    return reply

def handle_message(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id
    user_message = message.text or ""
    bot_username = context.bot.username

    is_group = message.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in user_message
    is_replied_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.username == bot_username
    )

    # Chỉ phản hồi khi tag bot hoặc reply bot trong group
    if is_group and not is_tagged and not is_replied_to_bot:
        return

    if is_tagged:
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    try:
        # ✅ Nếu là lần đầu → gửi chào đặc biệt, không gọi GPT
        if user_id not in first_time_users:
            first_time_users.add(user_id)
            message.reply_text(
                "🖐️ Xin chào ní! Tôi là trợ lý của anh Huân, bạn cần hỗ trợ gì nào?",
                reply_to_message_id=message.message_id
            )
            return

        # ✅ Những lần sau → gọi GPT
        reply = chat_with_gpt(user_id, user_message)
        message.reply_text(reply, reply_to_message_id=message.message_id)

    except Exception as e:
        message.reply_text("⚠️ Lỗi: " + str(e), reply_to_message_id=message.message_id)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
