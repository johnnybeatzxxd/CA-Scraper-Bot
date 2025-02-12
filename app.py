from flask import Flask, request, jsonify
import json
import telebot
import os
import asyncio
from dotenv import load_dotenv
from pymongo import MongoClient
from utils import start_script, stop_script, change_config
from send_message import send_message_to_bot, get_telegram_connection
from setup_accounts import setup_accounts 

load_dotenv(override=True)

app = Flask(__name__)

# MongoDB Setup
MONGO_URL = os.getenv('MONGO_URL')
client = MongoClient(MONGO_URL)
db_name = os.getenv('DATABASE_NAME')
db = client[db_name]  
config_collection = db['configs']
users = db["users"]

# Telegram Bot Setup
bot_token = os.environ.get("TelegramBotToken")
bot = telebot.TeleBot(bot_token)

# Add these global variables at the top with other imports
telegram_connection = None
OWNER_IDS = [int(id) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id]
owners = OWNER_IDS
selected_accounts_for_deletion = {}

def markups():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)   
    start = telebot.types.KeyboardButton('⚡ Start hunting')   
    stop = telebot.types.KeyboardButton('🛑 Stop hunting')   
    workers = telebot.types.KeyboardButton('👥 Workers')
    config = telebot.types.KeyboardButton('⚙️ Config')
    
    # Get current credentials status
    configs = config_collection.find_one({'type': 'telegram_creds'}) or {}
    cred_status = f"🔑 {configs.get('api_id', 'No Creds')}"
    creds_btn = telebot.types.KeyboardButton(cred_status)
    
    markup.add(start, stop, workers, config)
    markup.row(creds_btn)  # Add credentials button as full-width row
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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_msg = f"👋 Welcome {message.from_user.first_name}!\n\n"
    welcome_msg += "I'm your Crypto Hunter Bot 🚀\n\n"
    welcome_msg += "Key Features:\n"
    welcome_msg += "- 🎯 Hunting newly launched Twitter/Telegram accounts\n"
    welcome_msg += "- ⚡ Sniping tokens at lightning speed\n" 
    welcome_msg += "- 💸 Auto-buying tokens immediately after launch\n"
    welcome_msg += "- 🔒 Secure and reliable execution\n\n"
    welcome_msg += "⚠️ Access Required:\n"
    welcome_msg += "This is a private bot - please contact @fiinnessey to request access.\n\n"
    welcome_msg += "Once authorized, you can start hunting using the buttons below! 🎯"
    bot.reply_to(message, welcome_msg, parse_mode='Markdown', reply_markup=markups())
@bot.message_handler(func=lambda message: message.text.startswith('/allow') and message.chat.id in owners)
def handle_allow(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /allow <user_id1> <user_id2> ...")
            return
            
        user_ids = [int(id) for id in parts[1:]]
        
        users.update_one(
            {},
            {"$addToSet": {"allowed_users": {"$each": user_ids}}},
            upsert=True
        )
        
        allowed = users.find_one().get("allowed_users", [])
        bot.reply_to(message, f"✅ Allowed users updated!\nCurrent allowed IDs: {', '.join(map(str, allowed))}")
        
    except ValueError:
        bot.reply_to(message, "Invalid user ID format. Must be integers.")
    except Exception as e:
        bot.reply_to(message, f"Error updating allowed users: {str(e)}")

@bot.message_handler(func=lambda message: message.text.startswith('/block') and message.chat.id in owners)
def handle_block(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /block <user_id1> <user_id2> ...")
            return
            
        user_ids = [int(id) for id in parts[1:]]
        
        users.update_one(
            {},
            {"$pull": {"allowed_users": {"$in": user_ids}}}
        )
        
        allowed = users.find_one().get("allowed_users", [])
        bot.reply_to(message, f"✅ Users blocked!\nRemaining allowed IDs: {', '.join(map(str, allowed))}")
        
    except ValueError:
        bot.reply_to(message, "Invalid user ID format. Must be integers.")
    except Exception as e:
        bot.reply_to(message, f"Error blocking users: {str(e)}")


@bot.message_handler(func=lambda message: True)
def chat(message):
    global telegram_connection
    user_id = message.chat.id
   
    # Check if we're waiting for authentication
    if telegram_connection and telegram_connection.get_waiting_for():
        if message.chat.id not in owners:
            user_doc = users.find_one({})
            allowed_users = user_doc.get('allowed_users', []) if user_doc else []
            if message.chat.id not in allowed_users:
                return
        handle_auth_request(message.chat.id, message)
        return

    if message.text == "⚡ Start hunting":
      
        if message.chat.id not in owners:
            user_doc = users.find_one({})
            allowed_users = user_doc.get('allowed_users', []) if user_doc else []
            if message.chat.id not in allowed_users:
                bot.reply_to(message, "❌ You are not authorized to start the bot.")
                return

        try:   
             
            creds_doc = config_collection.find_one({'type': 'telegram_creds'})
            if not creds_doc or not all(key in creds_doc for key in ['api_id', 'api_hash', 'phone_number']):
                bot.reply_to(message, "❌ No Telegram credentials set! Please configure them first.")
                return   
            if not telegram_connection:
                bot.reply_to(message, "Initializing Telegram connection...")
                telegram_connection = get_telegram_connection()
                
                def bot_auth_callback(msg):
                    global telegram_connection
                    bot.send_message(message.chat.id, msg)
                    if msg == "Successfully authenticated with Telegram!":
                        response = start_script(user_id)
                        bot.send_message(message.chat.id, f"{response}", reply_markup=markups())
                        telegram_connection.bot_auth_callback = lambda x: None
                    elif "authentication failed" in msg.lower():
                        telegram_connection = None
                        bot.send_message(message.chat.id, "Authentication failed. Please try starting again.", 
                                       reply_markup=markups())

                telegram_connection.bot_auth_callback = bot_auth_callback
                telegram_connection.initialize()
                
                # Add retry mechanism
                if not telegram_connection.is_connected():
                    bot.reply_to(message, "Connection failed. Please check credentials and try again.", 
                               reply_markup=markups())
                return
            
            if telegram_connection.is_connected():
                bot.reply_to(message, "Telegram connection is ready!")
                response = start_script(user_id)
                bot.reply_to(message, f"{response}", reply_markup=markups())
            else:
                waiting_for = telegram_connection.get_waiting_for()
                if waiting_for:
                    bot.reply_to(message, f"Please provide your {waiting_for}.", reply_markup=markups())
                else:
                    config_collection.delete_one({'type': 'telethon_session'})
                    bot.reply_to(message, "Connection failed. Please try again.", reply_markup=markups())
                
        except ValueError as e:
            if "Missing Telegram credentials" in str(e):
                bot.reply_to(message, "❌ Telegram credentials not configured! Use the 🔑 button to set them up.")
            else:
                bot.reply_to(message, f"Error: {str(e)}")

    elif message.text == "🛑 Stop hunting":
        if message.chat.id not in owners:
            user_doc = users.find_one({})
            allowed_users = user_doc.get('allowed_users', []) if user_doc else []
            if message.chat.id not in allowed_users:
                bot.reply_to(message, "❌ You are not authorized to stop the bot.")
                return
        response = stop_script()
        bot.reply_to(message, f"{response}",reply_markup=markups())

    elif message.text == "👥 Workers":
        if message.chat.id not in owners:
            user_doc = users.find_one({})
            allowed_users = user_doc.get('allowed_users', []) if user_doc else []
            if message.chat.id not in allowed_users:
                bot.reply_to(message, "❌ You are not authorized to see workers.")
                return
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
        if message.chat.id not in owners:
            user_doc = users.find_one({})
            allowed_users = user_doc.get('allowed_users', []) if user_doc else []
            if message.chat.id not in allowed_users:
                bot.reply_to(message, "❌ You are not authorized to configure the bot.")
                return
        markup = telebot.types.InlineKeyboardMarkup()
        target_btn = telebot.types.InlineKeyboardButton('🎯 Set Target', callback_data='set_target')
        bot_btn = telebot.types.InlineKeyboardButton('🤖 Set Bot', callback_data='set_bot')
        platform_btn = telebot.types.InlineKeyboardButton('🌐 Set Platform', callback_data='set_platform')
        markup.row(target_btn)
        markup.row(bot_btn)
        markup.row(platform_btn)

        configs = get_configs()
        filtered_configs = {k: v for k, v in configs.items() 
                          if k not in ['type', 'api_id', 'api_hash', 'phone_number','interval','max_retries'] 
                          and not k.startswith('_')}
        config_message = "\n".join([f"{key}: {value}" for key, value in reversed(filtered_configs.items())])
        bot.reply_to(message, f"Current configurations:\n\n{config_message}")
        bot.reply_to(message, "Choose what you want to configure:", reply_markup=markup)

    elif message.text.startswith('🔑'):
        if message.chat.id not in owners:
            user_doc = users.find_one({})
            allowed_users = user_doc.get('allowed_users', []) if user_doc else []
            if message.chat.id not in allowed_users:
                bot.reply_to(message, "❌ You are not authorized to configure the bot.")
                return
        markup = telebot.types.InlineKeyboardMarkup()
        creds_btn = telebot.types.InlineKeyboardButton('Manage Credentials', callback_data='set_telegram_creds')
        markup.row(creds_btn)
        
        # Get current credentials
        configs = config_collection.find_one({'type': 'telegram_creds'}) or {}
        status_message = "Current Telegram Credentials:\n\n"
        status_message += f"API_ID: {configs.get('api_id', 'Not set')}\n"
        status_message += f"API_HASH: {configs.get('api_hash', 'Not set')[:4]}...\n"
        status_message += f"PHONE: {configs.get('phone_number', 'Not set')[:6]}..."
        
        bot.reply_to(message, status_message, reply_markup=markup)

    else:
        bot.reply_to(message, "I don't understand you 😢",reply_markup=markups())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global selected_accounts_for_deletion
    
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
        # Clear previous selections when opening delete menu
        selected_accounts_for_deletion[call.message.chat.id] = []
        
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
                callback_data=f"select_{account['username']}_good"
            )
            markup.row(btn)
        
        # Add buttons for offline accounts
        for account in offline_accounts:
            btn = telebot.types.InlineKeyboardButton(
                f"@{account['username']} - ❌", 
                callback_data=f"select_{account['username']}_bad"
            )
            markup.row(btn)

        # Add confirm delete button
        confirm_btn = telebot.types.InlineKeyboardButton(
            "🗑️ Delete Selected", 
            callback_data="confirm_delete"
        )
        markup.row(confirm_btn)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Select accounts to delete (click multiple):",
            reply_markup=markup
        )

    elif call.data.startswith('select_'):
        # Split the callback data to get username and status
        _, username, status = call.data.split('_')
        
        # Initialize selected accounts for this chat if not exists
        if call.message.chat.id not in selected_accounts_for_deletion:
            selected_accounts_for_deletion[call.message.chat.id] = []
        
        # Toggle selection
        account_info = {'username': username, 'status': status}
        current_selections = selected_accounts_for_deletion[call.message.chat.id]
        
        if any(acc['username'] == username for acc in current_selections):
            selected_accounts_for_deletion[call.message.chat.id] = [
                acc for acc in current_selections if acc['username'] != username
            ]
        else:
            selected_accounts_for_deletion[call.message.chat.id].append(account_info)
        
        # Update message to show selected accounts
        current_selections = selected_accounts_for_deletion[call.message.chat.id]
        if current_selections:
            selected_text = "Selected accounts:\n"
            for acc in current_selections:
                status_emoji = "✅" if acc['status'] == 'good' else "❌"
                selected_text += f"@{acc['username']} {status_emoji}\n"
        else:
            selected_text = "Select accounts to delete (click multiple):"
        
        # Keep the same markup as before
        markup = call.message.reply_markup
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=selected_text,
            reply_markup=markup
        )
        
    elif call.data == "confirm_delete":
        current_selections = selected_accounts_for_deletion.get(call.message.chat.id, [])
        if not current_selections:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="No accounts selected for deletion.",
            )
            return
            
        credentials_collection = db['credentials']
        
        # Delete selected accounts
        for account in current_selections:
            if account['status'] == 'good':
                credentials_collection.update_one(
                    {},
                    {'$pull': {'accounts': {'username': account['username']}}}
                )
            else:  # status == 'bad'
                credentials_collection.update_one(
                    {},
                    {'$pull': {'offline': {'username': account['username']}}}
                )
        
        deleted_accounts = ", ".join([f"@{acc['username']}" for acc in current_selections])
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Deleted accounts: {deleted_accounts}",
        )
        
        # Clear selections after deletion
        selected_accounts_for_deletion[call.message.chat.id] = []
        
        bot.send_message(call.message.chat.id, "Worker accounts deleted successfully!", reply_markup=markups())

    elif call.data in ['create_creds', 'change_creds']:
        msg = bot.send_message(
            call.message.chat.id,
            "Please enter your API_ID:",
            reply_markup=telebot.types.ForceReply()
        )
        bot.register_next_step_handler(msg, process_api_id_step)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Starting credential setup...",
            reply_markup=None
        )

    elif call.data == "set_telegram_creds":
        markup = telebot.types.InlineKeyboardMarkup()
        create_btn = telebot.types.InlineKeyboardButton('➕ Create New', callback_data='create_creds')
        change_btn = telebot.types.InlineKeyboardButton('✏️ Change Existing', callback_data='change_creds')
        markup.row(create_btn, change_btn)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Manage Telegram Credentials:",
            reply_markup=markup
        )

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

def handle_auth_request(chat_id, message):
    """Handle authentication code/password from user"""
    if telegram_connection:
        waiting_for = telegram_connection.get_waiting_for()
        if waiting_for == 'code':
            telegram_connection.set_auth_data('code', message.text.strip())
            bot.reply_to(message, "Verification code received, processing...")
        elif waiting_for == 'password':
            telegram_connection.set_auth_data('password', message.text.strip())
            bot.reply_to(message, "2FA password received, processing...")

def process_api_id_step(message):
    try:
        api_id = int(message.text.strip())
        msg = bot.send_message(message.chat.id, 
                             "Please enter your API_HASH:",
                             reply_markup=telebot.types.ForceReply())
        bot.register_next_step_handler(msg, process_api_hash_step, api_id)
    except ValueError:
        bot.send_message(message.chat.id, "Invalid API_ID! Must be a number.")

def process_api_hash_step(message, api_id):
    api_hash = message.text.strip()
    msg = bot.send_message(message.chat.id, 
                         "Please enter your PHONE_NUMBER (international format):",
                         reply_markup=telebot.types.ForceReply())
    bot.register_next_step_handler(msg, process_phone_step, api_id, api_hash)

def process_phone_step(message, api_id, api_hash):
    phone_number = message.text.strip()
    
    # Clear existing session when credentials change
    config_collection.delete_one({'type': 'telethon_session'})
    
    # Save to MongoDB
    config_collection.update_one(
        {'type': 'telegram_creds'},
        {'$set': {
            'api_id': api_id,
            'api_hash': api_hash,
            'phone_number': phone_number
        }},
        upsert=True
    )
    
   # Force disconnect existing connection
    global telegram_connection
    if telegram_connection:
        try:
            print("Disconnecting existing Telegram connection...")
            telegram_connection.disconnect()  # Use the proper disconnect method
            print("Successfully disconnected old connection")
        except Exception as e:
            print(f"Error disconnecting: {str(e)}")
        finally:
            telegram_connection = None  # Reset the connection instance
    
    bot.send_message(message.chat.id, "✅ Telegram credentials saved successfully!", reply_markup=markups())


if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)






