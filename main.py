import os
import openai
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Lưu người dùng đã từng tag bot
first_time_users = set()
# Lưu lịch sử chat theo user
conversation_history = {}

def chat_with_gpt(user_id, message):
    history = conversation_history.get(user_id, [])
    history.append({"role": "user", "content": message})

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=history
    )
    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    conversation_history[user_id] = history[-10:]
    return reply

def handle_message(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id
    user_text = message.text or ""
    bot_username = context.bot.username

    is_group = message.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in user_text
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.username == bot_username
    )

    # Trong nhóm, nếu không tag hoặc không reply bot thì bỏ qua
    if is_group and not is_tagged and not is_reply_to_bot:
        return

    # Nếu có tag thì loại bỏ để giữ nội dung gốc
    if is_tagged:
        user_text = user_text.replace(f"@{bot_username}", "").strip()

    try:
        # Nếu là lần đầu → chỉ gửi câu chào
        if user_id not in first_time_users:
            first_time_users.add(user_id)
            message.reply_text(
                "🖐️ Xin chào ní! Tôi là trợ lý của anh Huân, bạn cần hỗ trợ gì nào?",
                reply_to_message_id=message.message_id
            )
            return

        # Nếu không phải lần đầu → gọi GPT
        reply = chat_with_gpt(user_id, user_text)
        message.reply_text(
            reply,
            reply_to_message_id=message.message_id
        )

    except Exception as e:
        message.reply_text("⚠️ Đã có lỗi xảy ra: " + str(e))

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
