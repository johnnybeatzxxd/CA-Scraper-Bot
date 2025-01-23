import asyncio
import logging
from telethon import events
from send_message import get_telegram_connection
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables and setup MongoDB
load_dotenv()
MONGO_URL = os.getenv('MONGO_URL')
mongo_client = MongoClient(MONGO_URL)
db = mongo_client['CA-Hunter']
config_collection = db['configs']

# Control flags
running = False
# Add a list to track event handlers
message_handlers = []

def stop_main():
    global running
    running = False
    logger.info("Stop flag set in Telegram platform")

async def main(TARGET, CHECK_INTERVAL):
    global running
    global message_handlers
    running = True
    
    try:
        # Get existing Telegram connection
        connection = get_telegram_connection()
        if not connection or not connection.client:
            logger.error("Failed to get Telegram connection")
            return
            
        client = connection.client
        
        # Ensure client is connected
        if not client.is_connected():
            await client.connect()
        
        # Remove any existing handlers
        for handler in message_handlers:
            client.remove_event_handler(handler)
        message_handlers.clear()
        
        # Get bot username from config
        config = config_collection.find_one() or {}
        bot_username = config.get("bot", "johnnybeatz")
        
        @client.on(events.NewMessage(chats=TARGET))
        async def handler(event):
            if not running:
                return
            try:
                message = event.message.text
                await client.send_message(bot_username, message)
                logger.info(f"Message forwarded from {TARGET}: {message[:50]}...")
            except Exception as e:
                logger.error(f"Message forward error: {str(e)}")

        # Store the handler reference
        message_handlers.append(handler)
        logger.info(f"Starting to monitor Telegram channel: {TARGET}")
        
        # Keep the client running
        while running:
            try:
                await asyncio.sleep(1)
                if not client.is_connected():
                    logger.warning("Client disconnected, attempting to reconnect...")
                    await client.connect()
            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                break

    except Exception as e:
        logger.error(f"Fatal error in Telegram platform: {str(e)}")
    finally:
        # Clean up handlers when stopping
        for handler in message_handlers:
            client.remove_event_handler(handler)
        message_handlers.clear()
        running = False
        logger.info("Telegram platform stopped")

if __name__ == "__main__":
    target_channel = "@example_channel"
    asyncio.run(main(target_channel, 1))






