from flask import Flask, request, jsonify
import json
import telebot
import os
import asyncio
from dotenv import load_dotenv
from pymongo import MongoClient
from utils import start_script, stop_script, change_config
from send_message import send_message_to_bot
from setup_accounts import setup_accounts 

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
    workers = telebot.types.KeyboardButton('👥 Workers')
    config = telebot.types.KeyboardButton('⚙️ Config')
    markup.add(start,stop,workers,config)
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

    elif message.text == "👥 Workers":
        credentials_collection = db['credentials']
        doc = credentials_collection.find_one({})
        
        # Get both offline and online accounts
        offline_accounts = doc.get('offline', []) if doc else []
        online_accounts = doc.get('accounts', []) if doc else []
        
        # Create status message
        status_message = "Worker Accounts Status:\n\n"
        status_message += f"✅ Active Workers: {len(online_accounts)}\n"
        status_message += f"❌ Offline Workers: {len(offline_accounts)}\n"
        status_message += f"📊 Total Workers: {len(online_accounts) + len(offline_accounts)}"
        
        # Create inline keyboard
        markup = telebot.types.InlineKeyboardMarkup()
        list_btn = telebot.types.InlineKeyboardButton('📋 List Workers', callback_data='list_workers')
        add_btn = telebot.types.InlineKeyboardButton('➕ Add Worker', callback_data='add_worker')
        delete_btn = telebot.types.InlineKeyboardButton('🗑️ Delete Worker', callback_data='delete_worker')
        markup.row(list_btn)
        markup.row(add_btn)
        markup.row(delete_btn)
        
        # Send status message with inline keyboard
        bot.reply_to(message, status_message, reply_markup=markup)

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

    elif call.data == "list_workers":
        credentials_collection = db['credentials']
        doc = credentials_collection.find_one({})
        
        # Get both offline and online accounts
        offline_accounts = doc.get('offline', []) if doc else []
        online_accounts = doc.get('accounts', []) if doc else []
        
        if not offline_accounts and not online_accounts:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="No worker accounts found."
            )
            return
        
        account_list = "Worker Accounts:\n\n"
        
        # List online accounts (good status)
        for i, account in enumerate(online_accounts, 1):
            account_list += f"{i}. @{account['username']} - ✅ Good\n"
        
        # List offline accounts (bad status)
        for i, account in enumerate(offline_accounts, len(online_accounts) + 1):
            account_list += f"{i}. @{account['username']} - ❌ Bad\n"
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=account_list
        )

    elif call.data == "add_worker":
        markup = telebot.types.InlineKeyboardMarkup()
        text_btn = telebot.types.InlineKeyboardButton('📝 Text Input', callback_data='text_input')
        file_btn = telebot.types.InlineKeyboardButton('📎 Upload File', callback_data='file_upload')
        markup.row(text_btn, file_btn)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Choose how you want to add workers:",
            reply_markup=markup
        )

    elif call.data == "text_input":
        msg = bot.send_message(
            call.message.chat.id,
            "Please enter worker accounts in the following format:\n\n"
            "username email password\n"
            "(one account per line)\n\n"
            "Example:\n"
            "worker1 worker1@email.com pass123\n"
            "worker2 worker2@email.com pass456",
            reply_markup=telebot.types.ForceReply()
        )
        bot.register_next_step_handler(msg, process_workers_step)

    elif call.data == "file_upload":
        msg = bot.send_message(
            call.message.chat.id,
            "Please upload a text file containing worker accounts.\n",
            reply_markup=telebot.types.ForceReply()
        )
        bot.register_next_step_handler(msg, process_file_upload)

    elif call.data == "delete_worker":
        credentials_collection = db['credentials']
        doc = credentials_collection.find_one({})
        
        # Get both offline and online accounts
        offline_accounts = doc.get('offline', []) if doc else []
        online_accounts = doc.get('accounts', []) if doc else []
        
        if not offline_accounts and not online_accounts:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="No worker accounts to delete."
            )
            return
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add buttons for online accounts
        for account in online_accounts:
            btn = telebot.types.InlineKeyboardButton(
                f"@{account['username']} - ✅", 
                callback_data=f"del_{account['username']}_good"
            )
            markup.row(btn)
        
        # Add buttons for offline accounts
        for account in offline_accounts:
            btn = telebot.types.InlineKeyboardButton(
                f"@{account['username']} - ❌", 
                callback_data=f"del_{account['username']}_bad"
            )
            markup.row(btn)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Select account to delete:",
            reply_markup=markup
        )
        
    elif call.data.startswith('del_'):
        # Split the callback data to get username and status
        _, username, status = call.data.split('_')
        credentials_collection = db['credentials']
        
        # Remove from the appropriate array based on status
        if status == 'good':
            credentials_collection.update_one(
                {},
                {'$pull': {'accounts': {'username': username}}}
            )
        else:  # status == 'bad'
            credentials_collection.update_one(
                {},
                {'$pull': {'offline': {'username': username}}}
            )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Account @{username} has been deleted.",
        )
        bot.send_message(call.message.chat.id, "Worker account deleted successfully!", reply_markup=markups())

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

def process_workers_step(message):
    try:
        workers = []
        lines = message.text.strip().split('\n')
        
        for line in lines:
            parts = line.strip().split()
            if len(parts) != 3:
                raise ValueError("Invalid format")
            
            username, email, password = parts
            workers.append({
                'username': username,
                'email': email,
                'password': password
            })
        
        # Save workers to credentials collection in the accounts list
        credentials_collection = db['credentials']
        credentials_collection.update_one(
            {},  # empty filter to match any document
            {
                '$push': {
                    'accounts': {
                        '$each': workers
                    }
                }
            },
            upsert=True  # create document if it doesn't exist
        )
        
        bot.reply_to(
            message,
            f"Successfully added {len(workers)} worker accounts!",
            reply_markup=markups()
        )
    except ValueError:
        bot.reply_to(
            message,
            "Invalid format! Please make sure each line contains: username email password",
            reply_markup=markups()
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"Error adding workers: {str(e)}",
            reply_markup=markups()
        )

def process_file_upload(message):
    try:
        if not message.document or not message.document.mime_type == 'text/plain':
            raise ValueError("Please upload a text file (.txt)")

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Save the file locally
        with open('accounts.txt', 'wb') as new_file:
            new_file.write(downloaded_file)

        accounts = setup_accounts()

        bot.reply_to(
            message,
            f"{len(accounts)} workers added from the file!",
            reply_markup=markups()
        )
    except ValueError as e:
        bot.reply_to(message, str(e), reply_markup=markups())
    except Exception as e:
        bot.reply_to(
            message,
            f"Error processing file: {str(e)}",
            reply_markup=markups()
        )

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
