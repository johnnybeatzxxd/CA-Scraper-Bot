from flask import Flask, request, jsonify
import json
import telebot
import os
import asyncio
from dotenv import load_dotenv
from pymongo import MongoClient
from utils import start_script, stop_script, change_config
from send_message import send_message_to_bot

load_dotenv()

app = Flask(__name__)

# MongoDB Setup
MONGO_URL = os.getenv('MONGO_URL')
client = MongoClient(MONGO_URL)
db = client['CA-Hunter']  
config_collection = db['configs']

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
        response = start_script()
        bot.reply_to(message, f"{response}", reply_markup=markups())

    elif message.text == "🛑 Stop hunting":
        response = stop_script()
        bot.reply_to(message, f"{response}",reply_markup=markups())

    elif message.text == "⚙️ Config":
        markup = telebot.types.InlineKeyboardMarkup()
        target_btn = telebot.types.InlineKeyboardButton('🎯 Set Target', callback_data='set_target')
        bot_btn = telebot.types.InlineKeyboardButton('🤖 Set Bot', callback_data='set_bot')
        platform_btn = telebot.types.InlineKeyboardButton('🌐 Set Platform', callback_data='set_platform')
        markup.row(target_btn)
        markup.row(bot_btn)
        markup.row(platform_btn)

        configs = get_configs()
        config_message = "\n".join([f"{key}: {value}" for key, value in configs.items() if key not in ['interval', 'max_retries']])
        
        bot.reply_to(message, f"Current configurations\n\n{config_message}")
        bot.reply_to(message, "Choose what you want to configure:", reply_markup=markup)

    else:
        bot.reply_to(message, "I don't understand you 😢",reply_markup=markups())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "set_target":
        msg = bot.send_message(call.message.chat.id, 
                             "Please enter the username to target (without @ symbol):", 
                             reply_markup=telebot.types.ForceReply())
        bot.register_next_step_handler(msg, process_target_step)
        
    elif call.data == "set_bot":
        msg = bot.send_message(call.message.chat.id, 
                             "Please enter the bot username that you want send the CA to:", 
                             reply_markup=telebot.types.ForceReply())
        bot.register_next_step_handler(msg, process_bot_step)
        
    elif call.data == "set_platform":
        platform_markup = telebot.types.InlineKeyboardMarkup()
        twitter = telebot.types.InlineKeyboardButton('Twitter', callback_data='platform_twitter')
        instagram = telebot.types.InlineKeyboardButton('Telegram', callback_data='platform_telegram')
        platform_markup.row(twitter, instagram)
        bot.edit_message_text(chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            text="Choose the platform:",
                            reply_markup=platform_markup)
    
    elif call.data.startswith('platform_'):
        platform = call.data.split('_')[1]
        change_config('platform', platform)
        bot.edit_message_text(chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            text=f"Platform has been set to: {platform.capitalize()}",
                            reply_markup=None)
        bot.send_message(call.message.chat.id, "Configuration updated!", reply_markup=markups())

def process_target_step(message):
    try:
        target = message.text.strip()  
        # Remove @ symbol if user included it
        if target.startswith('@'):
            target = target[1:]
            
        if not target:  # Check if username is empty
            raise ValueError("Username cannot be empty")
            
        change_config('target', target)
        bot.reply_to(message, f"Target has been set to: @{target}", reply_markup=markups())
    except ValueError as e:
        bot.reply_to(message, f"Invalid username! Please try again.", reply_markup=markups())

def process_bot_step(message):
    try:
        bot_name = message.text.strip()
        if not bot_name:  # Check if bot name is empty
            raise ValueError("Bot name cannot be empty")
            
        change_config('bot', bot_name)
        bot.reply_to(message, f"Bot has been set to: {bot_name}", reply_markup=markups())
    except ValueError as e:
        bot.reply_to(message, f"Invalid bot name! Please try again.", reply_markup=markups())

def get_configs():
    try:
        configs = config_collection.find_one() or {}
        # Remove MongoDB's _id field if it exists
        if '_id' in configs:
            del configs['_id']
        return configs
    except Exception as e:
        print(f"Error fetching configs from MongoDB: {e}")
        return {}

if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)
