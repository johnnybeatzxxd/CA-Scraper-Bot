from telethon import TelegramClient
import os
from dotenv import load_dotenv
import asyncio
import threading
from telethon.sessions import StringSession
import time
from pymongo import MongoClient
from telethon.errors import SessionPasswordNeededError

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
    _auth_data = {'code': None, 'password': None, 'waiting_for': None}
    
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
            self.bot_auth_callback = None
            self._connection_event = threading.Event()

    def _get_session(self):
        """Get session string from MongoDB"""
        try:
            config = config_collection.find_one({'type': 'telethon_session'})
            if config and 'session_string' in config:
                return config['session_string']
        except Exception as e:
            print(f"Error getting session: {e}")
        return None

    def _save_session(self, session_string):
        """Save session string to MongoDB"""
        try:
            config_collection.update_one(
                {'type': 'telethon_session'},
                {'$set': {'session_string': session_string}},
                upsert=True
            )
            print("Session saved successfully!")
        except Exception as e:
            print(f"Error saving session: {e}")

    def initialize(self):
        """Explicitly initialize the client when needed"""
        if not self.initialized or not self.is_connected():
            # Reset connection state
            self._connection_event.clear()
            self._auth_data = {'code': None, 'password': None, 'waiting_for': None}
            self._setup_client()

    def set_auth_data(self, auth_type, value):
        self._auth_data[auth_type] = value
        self._auth_data['waiting_for'] = None

    def code_callback(self):
        self._auth_data['waiting_for'] = 'code'
        if self.bot_auth_callback:
            self.bot_auth_callback("Please send the Telegram verification code.")
        
        # Wait for code to be set
        while self._auth_data['code'] is None:
            time.sleep(1)
        
        code = self._auth_data['code']
        self._auth_data['code'] = None
        return code

    def password_callback(self):
        self._auth_data['waiting_for'] = 'password'
        if self.bot_auth_callback:
            self.bot_auth_callback("Please send your 2FA password.")
        
        # Wait for password to be set
        while self._auth_data['password'] is None:
            time.sleep(1)
        
        password = self._auth_data['password']
        self._auth_data['password'] = None
        return password

    def get_waiting_for(self):
        return self._auth_data['waiting_for']

    def is_connected(self):
        return self.initialized and self.client and self.client.is_connected()

    async def _start_client(self):
        try:
            print("Starting authentication process...")
            if self.bot_auth_callback:
                self.bot_auth_callback("Starting Telegram authentication process...")

            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                self.initialized = False
                self._connection_event.clear()
                
                print("User not authorized. Requesting code...")
                if self.bot_auth_callback:
                    self.bot_auth_callback("You need to authenticate. Sending verification code to your phone...")
                
                sent_code = await self.client.send_code_request(PHONE_NUMBER)
                code = self.code_callback()
                print(f"Got code, signing in...")
                
                try:
                    await self.client.sign_in(PHONE_NUMBER, code)
                except SessionPasswordNeededError:
                    print("2FA enabled, requesting password...")
                    password = self.password_callback()
                    try:
                        await self.client.sign_in(password=password)
                    except Exception as e:
                        print(f"Error during 2FA: {e}")
                        # Clear session on 2FA failure
                        config_collection.delete_one({'type': 'telethon_session'})
                        await self.client.disconnect()
                        self.initialized = False
                        self._connection_event.clear()
                        raise
                
                # Save session after successful authentication
                session_string = self.client.session.save()
                self._save_session(session_string)
            
            print("Client started and authenticated successfully!")
            if self.bot_auth_callback:
                self.bot_auth_callback("Successfully authenticated with Telegram!")
            
            self.initialized = True
            self._connection_event.set()
            
        except Exception as e:
            print(f"Error in _start_client: {e}")
            self.initialized = False
            self._connection_event.clear()
            
            if "authorization key" in str(e).lower() or "password" in str(e).lower():
                print("Invalid session or password detected, removing and retrying authentication...")
                # Delete the invalid session from MongoDB
                config_collection.delete_one({'type': 'telethon_session'})
                # Disconnect the current client
                if self.client:
                    await self.client.disconnect()
                # Create new client without session
                self.client = TelegramClient(
                    StringSession(),
                    API_ID,
                    API_HASH,
                    sequential_updates=True
                )
                # Retry authentication
                await self._start_client()
                return
                
            if self.bot_auth_callback:
                self.bot_auth_callback(f"Authentication error: {str(e)}")
            raise

    def _run_client(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Try to get existing session
            session_string = self._get_session()
            if session_string:
                print("Found existing session, trying to reuse...")
                self.client = TelegramClient(
                    StringSession(session_string),
                    API_ID,
                    API_HASH,
                    sequential_updates=True
                )
            else:
                print("No existing session found, creating new one...")
                self.client = TelegramClient(
                    StringSession(),
                    API_ID,
                    API_HASH,
                    sequential_updates=True
                )

            print("Starting Telegram client...")
            self.loop.run_until_complete(self._start_client())
            
            # Save session after successful authentication
            if self.client.is_connected():
                session_string = self.client.session.save()
                self._save_session(session_string)
            
            self.loop.run_forever()
        except Exception as e:
            print(f"Error in client thread: {e}")
            self.initialized = False

    def _setup_client(self):
        if not self.initialized:
            try:
                # Reset any existing client and thread
                if self.client:
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
                    self.client = None
                if self.thread and self.thread.is_alive():
                    self.thread = None
                
                self.thread = threading.Thread(target=self._run_client, daemon=True)
                self.thread.start()
                
                # Wait for connection with timeout
                if not self._connection_event.wait(timeout=90):
                    print("Timeout waiting for Telegram client initialization")
                    self.initialized = False
                    self._connection_event.clear()
                    raise RuntimeError("Timeout waiting for Telegram client initialization")
            except Exception as e:
                print(f"Error in setup_client: {e}")
                self.initialized = False
                self._connection_event.clear()
                raise

    def send_message(self, username, message):
        
        try:
            if not self.is_connected():
                print("Client not connected, attempting to reconnect...")
                self.initialize()
            
            async def _send():
                try:
                    await self.client.send_message(username, message)
                    return True
                except Exception as e:
                    print(f"Error sending message: {e}")
                    return False

            future = asyncio.run_coroutine_threadsafe(_send(), self.loop)
            return future.result(timeout=10)
        except Exception as e:
            print(f"Error in send_message: {e}")
            raise

# Global instance
_telegram_connection = None

def get_telegram_connection(initialize=False):
    """
    Get or create the Telegram connection.
    :param initialize: If True, initialize the connection immediately
    """
    global _telegram_connection
    if _telegram_connection is None:
        try:
            _telegram_connection = TelegramConnection()
            if initialize:
                _telegram_connection.initialize()
            print("Telegram connection instance created!")
        except Exception as e:
            print(f"Error with Telegram connection: {e}")
            raise
    return _telegram_connection

def send_message_to_bot(bot_username: str = "fiinnessey", your_message: str = "Hello ") -> None:
    try:
        # Get bot username from MongoDB
        config = config_collection.find_one() or {}
        bot_username = config.get("bot", bot_username)  # Use default if not found
        
        connection = get_telegram_connection(initialize=True)  # Initialize when sending message
        if not connection.is_connected():
            print("Connection not established, attempting to reconnect...")
            connection.initialize()
            
        connection.send_message(bot_username, your_message)
        print(f"Message sent successfully to {bot_username}")
    except Exception as e:
        print(f"Error sending message: {e}")
        raise

if __name__ == "__main__":
    print("This module should be imported, not run directly.")


