from telethon import TelegramClient
import os
from dotenv import load_dotenv
import asyncio
import threading
from telethon.sessions import StringSession
import time
from pymongo import MongoClient

load_dotenv()

# MongoDB Setup
MONGO_URL = os.getenv('MONGO_URL')
mongo_client = MongoClient(MONGO_URL)
db = mongo_client['CA-Hunter']
config_collection = db['configs']

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

class TelegramConnection:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.client = None
            self.loop = None
            self.thread = None
            self.initialized = False
            self._setup_client()

    def code_callback(self):
        print("Please check your Telegram app for the code!")
        return input('Enter the code you received: ')

    def password_callback(self):
        return input('Please enter your 2FA password: ')

    async def _start_client(self):
        try:
            await self.client.start(phone=PHONE_NUMBER, code_callback=self.code_callback, password=self.password_callback)
            print("Client started successfully!")
            self.initialized = True
        except Exception as e:
            print(f"Error starting client: {e}")
            self.initialized = False

    def _run_client(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            self.client = TelegramClient(
                "user_session",
                API_ID,
                API_HASH,
                sequential_updates=True
            )

            print("Starting Telegram client...")
            self.loop.run_until_complete(self._start_client())
            self.loop.run_forever()
        except Exception as e:
            print(f"Error in client thread: {e}")
            self.initialized = False

    def _setup_client(self):
        if not self.initialized:
            self.thread = threading.Thread(target=self._run_client, daemon=True)
            self.thread.start()
            
            timeout = 60  # 60 seconds timeout
            start_time = time.time()
            while not self.initialized and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            if not self.initialized:
                raise RuntimeError("Failed to initialize Telegram client")

    def send_message(self, username, message):
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        async def _send():
            try:
                await self.client.send_message(username, message)
                print("Message sent successfully!")
            except Exception as e:
                print(f"Error sending message: {e}")

        future = asyncio.run_coroutine_threadsafe(_send(), self.loop)
        return future.result(timeout=10)

# Global instance
_telegram_connection = None

def get_telegram_connection():
    global _telegram_connection
    if _telegram_connection is None:
        _telegram_connection = TelegramConnection()
    return _telegram_connection

def send_message_to_bot(bot_username: str = "johnnybeatz", your_message: str = "Hello ") -> None:
    try:
        # Get bot username from MongoDB
        config = config_collection.find_one() or {}
        bot_username = config.get("bot", bot_username)  # Use default if not found
        
        connection = get_telegram_connection()
        connection.send_message(bot_username, your_message)
    except Exception as e:
        print(f"Error sending message: {e}")

if __name__ == "__main__":
    try:
        print("Initializing Telegram connection...")
        connection = get_telegram_connection()
        print("Connection established!")
        
        # Get bot username from MongoDB for testing
        config = config_collection.find_one() or {}
        bot_username = config.get("bot", "johnnybeatz")  # Use default if not found
        
        send_message_to_bot(
            bot_username=bot_username,
            your_message="Test message from initialization"
        )
        print("Test complete!")
    except Exception as e:
        print(f"Error during initialization: {e}")

