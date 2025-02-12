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
db_name = os.getenv('DATABASE_NAME')
db = mongo_client[db_name]  
config_collection = db['configs']

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
            print("Initializing TelegramConnection - fresh instance")
            self.client = None
            self.loop = None
            self.thread = None
            self.initialized = False
            self.bot_auth_callback = None
            self._connection_event = threading.Event()
            # Get credentials from MongoDB
            self.creds = config_collection.find_one({'type': 'telegram_creds'}) or {}
            self.api_id = self.creds.get('api_id')
            self.api_hash = self.creds.get('api_hash')
            self.phone_number = self.creds.get('phone_number')
            self._current_cred_hash = None
            self._refresh_credentials()
            print(f"Initial credentials hash: {self._current_cred_hash}")

    def _refresh_credentials(self):
        """Reload credentials from DB and check for changes"""
        new_creds = config_collection.find_one({'type': 'telegram_creds'}) or {}
        
        # Compare individual fields instead of using hash
        if (new_creds.get('api_id') != self.api_id or
            new_creds.get('api_hash') != self.api_hash or
            new_creds.get('phone_number') != self.phone_number):
            
            print("Credentials changed - clearing session")
            config_collection.delete_one({'type': 'telethon_session'})
            self.client = None
            self.initialized = False
        
        # Update instance credentials
        self.api_id = new_creds.get('api_id')
        self.api_hash = new_creds.get('api_hash')
        self.phone_number = new_creds.get('phone_number')

    def _get_session(self):
        """Get session string from MongoDB"""
        try:
            config = config_collection.find_one({'type': 'telethon_session'})
            return config.get('session_string') if config else None
        except Exception as e:
            print(f"Error getting session: {e}")
            return None

    def _save_session(self, session_string):
        """Save session string to MongoDB"""
        try:
            print(f"Saving new session string: {session_string[:15]}...")
            config_collection.update_one(
                {'type': 'telethon_session'},
                {'$set': {'session_string': session_string}},
                upsert=True
            )
        except Exception as e:
            print(f"Error saving session: {str(e)}")
            raise

    def initialize(self):
        """Explicitly initialize the client when needed"""
        self._refresh_credentials()
        
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
                print("User not authorized - beginning authentication flow")
                self.initialized = False
                self._connection_event.clear()
                
                print("User not authorized. Requesting code...")
                if self.bot_auth_callback:
                    self.bot_auth_callback("You need to authenticate. Sending verification code to your phone...")
                
                sent_code = await self.client.send_code_request(self.phone_number)
                code = self.code_callback()
                print(f"Got code, signing in...")
                
                try:
                    await self.client.sign_in(self.phone_number, code)
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
                
                print("Auth successful - generating session string")
                session_string = self.client.session.save()
                print(f"Session string generated: {session_string[:15]}...")  # Log first 15 chars
                self._save_session(session_string)
            else:
                print("User already authorized - checking session consistency")
                session_string = self.client.session.save()
                print(f"Existing session string: {session_string[:15]}...")
                self._save_session(session_string)  # Ensure we save even if already authorized
            
            print("Client started and authenticated successfully!")
            if self.bot_auth_callback:
                self.bot_auth_callback("Successfully authenticated with Telegram!")
            
            self.initialized = True
            self._connection_event.set()
            
        except Exception as e:
            print(f"Error in _start_client: {e}")
            # Clear session and reset connection
            await self.client.disconnect()
            self.client = None
            self.initialized = False
            self._connection_event.clear()
            
            # Add proper error feedback
            error_msg = f"Authentication failed: {str(e)}"
            if "phone number" in str(e).lower():
                error_msg = "Invalid phone number format"
            elif "api_id" in str(e).lower():
                error_msg = "Invalid API ID"
            
            if self.bot_auth_callback:
                self.bot_auth_callback(error_msg)
            
            # Create fresh client for retry
            self.client = TelegramClient(
                StringSession(),
                self.api_id,
                self.api_hash,
                sequential_updates=True
            )
            raise

    def _run_client(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Validate credentials before proceeding
            if not all([self.api_id, self.api_hash, self.phone_number]):
                raise ValueError("Missing Telegram credentials in database")

            # Try to get existing session
            session_string = self._get_session()
            if session_string:
                print("Creating client with existing session in worker thread")
                self.client = TelegramClient(
                    StringSession(session_string),
                    self.api_id,
                    self.api_hash,
                    loop=self.loop,  # Explicitly set the event loop
                    sequential_updates=True
                )
            else:
                print("Creating new client in worker thread")
                self.client = TelegramClient(
                    StringSession(),
                    self.api_id,
                    self.api_hash,
                    loop=self.loop,  # Explicitly set the event loop
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
                session_string = self._get_session()
                
                # Reset any existing client and thread
                if self.client:
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
                    self.client = None
                if self.thread and self.thread.is_alive():
                    self.thread = None
                
                # Create new thread and client together
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

    def disconnect(self):
        """Explicitly disconnect the client"""
        try:
            if self.client and self.loop:
                print("Initiating Telegram client shutdown...")
                async def _disconnect():
                    try:
                        if self.client.is_connected():
                            await self.client.disconnect()
                            print("Telegram client disconnected successfully")
                        self.initialized = False
                    except Exception as e:
                        print(f"Error during disconnect: {str(e)}")
                
                # Wait for disconnection to complete
                future = asyncio.run_coroutine_threadsafe(_disconnect(), self.loop)
                future.result(timeout=10)  # Wait up to 10 seconds for disconnect
                self.client = None
                print("Telegram connection fully reset")
        except Exception as e:
            print(f"Error in disconnect: {str(e)}")
        finally:
            self._connection_event.clear()

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

def send_message_to_bot(your_message: str = "Hello ") -> None:
    try:
        # Get bot username from config
        config = config_collection.find_one() or {}
        bot_username = config.get("bot", "fiinnessey")
        
        connection = get_telegram_connection(initialize=True)
        if not connection.is_connected():
            connection.initialize()
            
        connection.send_message(bot_username, your_message)
        print(f"Message sent successfully to {bot_username}")
    except Exception as e:
        print(f"Error sending message: {e}")
        raise

if __name__ == "__main__":
    print("This module should be imported, not run directly.")



