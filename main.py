import os
import openai
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

# Token từ biến môi trường
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Cấu hình OpenAI
openai.api_key = OPENAI_API_KEY

# Lưu lịch sử chat (bộ nhớ RAM) theo user_id
conversation_history = {}

# Gọi API ChatGPT có lưu lịch sử đối thoại
def chat_with_gpt(user_id, user_message):
    history = conversation_history.get(user_id, [])

    # Thêm câu hỏi người dùng vào lịch sử
    history.append({"role": "user", "content": user_message})

    # Gửi toàn bộ đoạn chat lên GPT
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # hoặc gpt-4 nếu bạn có quyền
        messages=history
    )

    reply = response['choices'][0]['message']['content']

    # Ghi lại câu trả lời từ bot
    history.append({"role": "assistant", "content": reply})
    conversation_history[user_id] = history[-10:]  # Giữ tối đa 10 đoạn gần nhất

    return reply

# Hàm xử lý tin nhắn Telegram
def handle_message(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id

    # Nếu là group, chỉ phản hồi khi có tag @botname
    if message.chat.type in ['group', 'supergroup']:
        bot_username = context.bot.username
        if f"@{bot_username}" not in message.text:
            return

    # Loại bỏ @botname khỏi nội dung
    user_message = message.text.replace(f"@{context.bot.username}", "").strip()

    try:
        chatgpt_reply = chat_with_gpt(user_id, user_message)

        # Phản hồi trực tiếp vào tin nhắn đó (reply thread)
        message.reply_text(
            chatgpt_reply,
            reply_to_message_id=message.message_id
        )
    except Exception as e:
        message.reply_text("⚠️ Lỗi xử lý: " + str(e), reply_to_message_id=message.message_id)

# Khởi động bot
def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
