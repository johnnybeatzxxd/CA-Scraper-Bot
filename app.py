from flask import Flask, request, jsonify
import json
import telebot
import os
import asyncio
from dotenv import load_dotenv
from utils import start_script, stop_script
from send_message import send_message_to_bot

load_dotenv()

app = Flask(__name__)

# Telegram Bot Setup
bot = telebot.TeleBot(os.environ.get("TelegramBotToken"))

def markups():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True,row_width=2)   
    start = telebot.types.KeyboardButton('⚡ Start hunting')   
    stop = telebot.types.KeyboardButton('🛑 Stop hunting')   
    add_workers = telebot.types.KeyboardButton('👥 Add workers')
    config = telebot.types.KeyboardButton('⚙️ Config')
    markup.add(start,stop,add_workers,config)
    return markup

@app.route('/')
def hello():
    return f"Hello, World!"

@app.route('/bot', methods=['POST'])
def telegram_bot():
    try:
        update = telebot.types.Update.de_json(request.get_json(force=True))
        bot.process_new_updates([update])
        return "!", 200
    except Exception as e:
        print(f"Error processing Telegram update: {e}")
        return "Error", 500

@bot.message_handler(func=lambda message: True)
def chat(message):

    if message.text == "⚡ Start hunting":
        asyncio.run(send_message_to_bot(your_message="starting the script"))
        response = start_script()
        bot.reply_to(message, f"{response}",reply_markup=markups())

    elif message.text == "🛑 Stop hunting":
        response = stop_script()
        bot.reply_to(message, f"{response}",reply_markup=markups())

    else:
        bot.reply_to(message, "I don't understand you 😢",reply_markup=markups())

if __name__ == "__main__":
    app.run(debug=True)
