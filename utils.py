import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet
import threading
from get_client import get_or_create_client  
from send_message import send_message_to_bot
import json
import logging
import random
from pymongo import MongoClient

load_dotenv()
MONGO_URL = os.getenv('MONGO_URL')
client = MongoClient(MONGO_URL)
db = client['CA-Hunter'] 
config_collection = db['configs']  

main_loop = None
main_thread = None
main_task = None  # Add this to track the running task

# Add logging configuration at the top after imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def start_script(user_id):
    global main_thread
    global main_loop
    global main_task

    logging.info("Attempting to start script...")

    if main_thread is None or not main_thread.is_alive():
        logging.info("Creating new event loop and thread...")
        main_loop = asyncio.new_event_loop()
        
        # get configs from MongoDB
        configs = config_collection.find_one() or {}
        logging.info("Retrieved configurations from MongoDB")

        target = configs.get("target")
        if target is None or target == "":
            logging.error("⚙️ Configuration Error: Target is not set in the configuration.")
            return "⚙️ Configuration Error: Target is not set. Please ensure the target is specified in your configuration."

        bot = configs.get("bot")
        if bot is None or bot == "":
            logging.error("⚙️ Configuration Error: Bot is not set in the configuration.")
            return "⚙️ Configuration Error: Bot is not set. Please ensure the bot is specified in your configuration."

        platform = configs.get("platform")
        if platform is None or platform == "":
            logging.error("⚙️ Configuration Error: Platform is not set in the configuration.")
            return "⚙️ Configuration Error: Platform is not set. Please ensure the platform is specified in your configuration."
        
        interval = configs.get("interval", 1)  # Default to 1 second if not set
        platform = configs.get("platform", "twitter").lower()  # Default to twitter if not set
        
        logging.info(f"Starting script with target: {target}, platform: {platform}")

        def run_main():
            global main_task
            logging.info("Setting up event loop in new thread")
            asyncio.set_event_loop(main_loop)
            
            # Choose platform-specific main function
            if platform == "telegram":
                from tg import main as telegram_main
                main_task = main_loop.create_task(telegram_main(target, interval, user_id))
            else:  # default to Twitter
                from main import main as twitter_main
                main_task = main_loop.create_task(twitter_main(target, interval, user_id))
                
            try:
                logging.info("Starting main task execution")
                main_loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                logging.info("Main task was cancelled")
            except Exception as e:
                logging.error(f"Unexpected error in main task: {str(e)}")
            finally:
                logging.info("Closing event loop")
                main_loop.close()

        main_thread = threading.Thread(target=run_main)
        main_thread.start()
        logging.info("Script started successfully")
        return f"Script started on {platform.capitalize()} platform!"
    else:
        logging.warning("Attempted to start script while it's already running")
        return "Script is already running!"

def stop_script():
    global main_thread
    global main_loop
    global main_task

    logging.info("Attempting to stop script...")

    if main_thread is not None and main_thread.is_alive():
        logging.info("Script is running, initiating shutdown sequence")
        from main import stop_main
        stop_main()  # Set the running flag to False
        logging.info("Stop flag set")

        if main_task:
            logging.info("Cancelling main task")
            main_loop.call_soon_threadsafe(main_task.cancel)
        
        logging.info("Waiting for thread to complete (timeout: 5 seconds)")
        main_thread.join(timeout=5)
        
        if main_thread.is_alive():
            logging.warning("Thread did not complete within timeout period")
        else:
            logging.info("Thread completed successfully")

        # Clean up globals
        logging.info("Cleaning up global variables")
        main_thread = None
        main_loop = None
        main_task = None

        logging.info("Script stopped successfully")
        return "Script stopped!"
    else:
        logging.warning("Attempted to stop script while it's not running")
        return "Script is not running!"

def change_config(key, value):
    logging.info(f"Updating configuration - Key: {key}, Value: {value}")
    config_collection.update_one(
        {}, 
        {'$set': {key: value}},
        upsert=True
    )
    logging.info("Configuration updated successfully")
    return "Config updated!"
