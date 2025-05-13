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
    user_message = message.text or ""

    bot_username = context.bot.username

    is_group = message.chat.type in ['group', 'supergroup']
    is_tagged = f"@{bot_username}" in user_message
    is_replied_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user.username == bot_username
    )

    # 👉 Nếu ở group mà không tag và không reply bot → bỏ qua
    if is_group and not is_tagged and not is_replied_to_bot:
        return

    # Nếu có tag thì xoá phần @bot để lấy nội dung sạch
    if is_tagged:
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    try:
        # ✅ Trả lời riêng nếu đây là lần đầu người này tag bot
        if user_id not in first_time_users:
            first_time_users.add(user_id)
            message.reply_text(
                "🖐️ Xin chào ní! Tôi là trợ lý của anh Huân, bạn cần hỗ trợ gì nào?",
                reply_to_message_id=message.message_id
            )
            return  # Không gọi ChatGPT trong lần đầu

        # Các lần sau thì gọi ChatGPT như bình thường
        chatgpt_reply = chat_with_gpt(user_id, user_message)
        message.reply_text(
            chatgpt_reply,
            reply_to_message_id=message.message_id
        )

    except Exception as e:
        message.reply_text("⚠️ Lỗi: " + str(e), reply_to_message_id=message.message_id)


# Khởi động bot
def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
