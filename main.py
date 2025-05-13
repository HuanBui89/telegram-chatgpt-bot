import os
import openai
from telegram import Update, Bot
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

def chat_with_gpt(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # GPT-4 nếu bạn có quyền
        messages=[
            {"role": "user", "content": text}
        ]
    )
    return response['choices'][0]['message']['content']

def handle_message(update: Update, context: CallbackContext):
    message = update.message

    # Nếu trong group hoặc supergroup mà không tag bot => bỏ qua
    if message.chat.type in ['group', 'supergroup']:
        bot_username = context.bot.username
        if f"@{bot_username}" not in message.text:
            return

    # Bỏ phần @botname trong tin nhắn (nếu có)
    user_message = message.text.replace(f"@{context.bot.username}", "").strip()
    
    try:
        chatgpt_reply = chat_with_gpt(user_message)
        message.reply_text(chatgpt_reply)
    except Exception as e:
        message.reply_text("⚠️ Lỗi xử lý: " + str(e))

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
