import asyncio
import logging
from telethon import events, types
from send_message import get_telegram_connection
from pymongo import MongoClient
import os
import telebot
from dotenv import load_dotenv
from get_ca import get_contract, get_contract_address, get_text
import base64

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
db_name = os.getenv('DATABASE_NAME')
db = mongo_client[db_name]  
config_collection = db['configs']


bot = telebot.TeleBot(os.environ.get("TelegramBotToken"))

# Control flags
running = False
# Add a list to track event handlers
message_handlers = []

def stop_main():
    global running
    running = False
    logger.info("Stop flag set in Telegram platform")

async def main(TARGET, CHECK_INTERVAL, user_id):
    global running
    global message_handlers
    
    running = True
    
    try:
        # Get existing Telegram connection
        connection = get_telegram_connection()
        if not connection or not connection.client:
            logger.error("Failed to get Telegram connection")
            bot.send_message(user_id, "❌ Failed to establish Telegram connection")
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
        bot_username = config.get("bot", "fiinnessey")
        
        try:
            @client.on(events.NewMessage(chats=TARGET))
            async def handler(event):
                if not running:
                    return
                try:
                    message = event.message
                    logger.info(f"New message received from group {TARGET}")
                    
                    # Check if the message contains text
                    if message.text:
                        logger.info(f"Message content: {message.text[:100]}...")
                        contract_addresses = get_contract_address(message.text)
                        if contract_addresses:
                            # only send the first contract address
                            # await client.send_message(bot_username, contract_addresses[0])
                            bot.send_message(user_id,f"{contract_addresses[0]}")
                            logger.info(f"Contract address forwarded from {TARGET}: {contract_addresses[0]}")
                    
                    # Check if the message contains media (photo)
                    if message.media:
                        if isinstance(message.media, types.MessageMediaPhoto):
                            photo = message.photo
                            
                            # Download the photo to memory
                            photo_data = await client.download_media(photo, file=bytes)
                            
                            # Encode the photo data to base64
                            base64_photo = base64.b64encode(photo_data).decode('utf-8')
                            
                            # Extract text from the photo using get_text
                            text = get_text(base64_photo, type="base64")

                            if text:
                                contract_addresses = get_contract_address(text)
                                if contract_addresses:
                                    for contract_address in contract_addresses:
                                        # await client.send_message(bot_username, contract_address)
                                        bot.send_message(user_id,f"{contract_address}")
                                        logger.info(f"Contract address forwarded from {TARGET}: {contract_address}")
                                else:
                                    logger.info("No contract addresses found in the image.")
                            else:
                                logger.error("Failed to extract text from the image.")
                        else:
                            logger.info("Message contains unsupported media type.")

                except Exception as e:
                    logger.error(f"Message forward error: {str(e)}")
        except ValueError as e:
            logger.error(f"Invalid target channel: {str(e)}")
            bot.send_message(user_id, f"❌ Invalid target channel '{TARGET}'. Please check the ID/username exists and the bot has access.")
            return

        # Store the handler reference
        message_handlers.append(handler)
        logger.info(f"Starting to monitor Telegram channel: {TARGET}")
        bot.send_message(user_id, f"✅ Started monitoring channel: {TARGET}")
        
        # Keep the client running
        while running:
            try:
                await asyncio.sleep(1)
                if not client.is_connected():
                    logger.warning("Client disconnected, attempting to reconnect...")
                    bot.send_message(user_id, "⚠️ Lost connection, attempting to reconnect...")
                    await client.connect()
            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
                bot.send_message(user_id, "⏹ Monitoring stopped by user request")
                break
            except RuntimeError as e:
                if "event loop" in str(e).lower():
                    logger.error("Event loop conflict: %s", str(e))
                    connection.disconnect()
                    await client.connect()
                else:
                    raise
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                break

    except Exception as e:
        logger.error(f"Fatal error in Telegram platform: {str(e)}")
        bot.send_message(user_id, f"⚠️ Fatal error: {str(e)[:200]}")
        await bot.send_message(user_id, "Script stopped!")


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






