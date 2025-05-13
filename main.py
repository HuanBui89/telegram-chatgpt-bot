import os
from telegram import Update, Bot
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
from openai import OpenAI

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def chat_with_gpt(text):
    chat = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": text}
        ]
    )
    return chat.choices[0].message.content

def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text
    chatgpt_reply = chat_with_gpt(user_message)
    update.message.reply_text(chatgpt_reply)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
