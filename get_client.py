from twikit import Client
import asyncio
from dotenv import load_dotenv
import os
import json
import logging
import telebot 
from pymongo import MongoClient


load_dotenv()
bot = telebot.TeleBot(os.environ.get("TelegramBotToken"))

logging.basicConfig(
    level=logging.INFO,  
    format='%(asctime)s - %(levelname)s - %(message)s',  
    handlers=[
        logging.StreamHandler(),  
        logging.FileHandler("script.log", mode='a')  
    ]
)

# Optional: Suppress verbose logs from third-party libraries like `httpx`
logging.getLogger("httpx").setLevel(logging.WARNING)

MONGO_URL = os.getenv('MONGO_URL')
mongo_client = MongoClient(MONGO_URL)
db = mongo_client['CA-Hunter']  # Updated database name
cookies_collection = db['cookies']  # New collection for cookies

async def test_account(client, username):
    state = await client._get_user_state()
    logging.info(f"Account state for {username}: {state}")
    if state == "suspended":
        logging.warning(f"Account suspended: {username}")
        return False
    logging.info(f"Logged in successfully for {username}.")
    return True

async def get_or_create_client(account):
    username = account["username"]

    try:
        client = Client('en-US')
        try:
            # Get cookies from MongoDB instead of file
            cookie_doc = cookies_collection.find_one({"username": username})
            
            if cookie_doc and cookie_doc.get('cookies'):
                client.set_cookies(cookie_doc['cookies'])
                if not await test_account(client, username):
                    # Remove invalid cookies from MongoDB
                    cookies_collection.delete_one({"username": username})
                    raise ValueError("No valid cookie found for this account.")
            else:
                raise ValueError("No valid cookie found for this account.")
                
        except ValueError:
            logging.info(f"Logging in for {username}.")
            await client.login(
                auth_info_1=account["username"],
                auth_info_2=account["email"],
                password=account["password"]
            )
            if not await test_account(client, username):
                return None
                
            # Save cookies to MongoDB
            cookies_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "username": username,
                        "cookies": client.get_cookies()
                    }
                },
                upsert=True
            )
            logging.info(f"Cookies saved to MongoDB for {username}.")

        return client

    except Exception as e:
        logging.error(f"Error initializing client for {username}: {e}")
        return None



