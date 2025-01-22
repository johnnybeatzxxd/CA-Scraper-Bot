import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet
from get_client import get_or_create_client  
from send_message import send_message_to_bot
import logging
import random
import telebot
from pymongo import MongoClient

load_dotenv()

# MongoDB Setup
MONGO_URL = os.getenv('MONGO_URL')
mongo_client = MongoClient(MONGO_URL)
db = mongo_client['CA-Hunter']  # Replace with your database name
credentials_collection = db['credentials']
config_collection = db['configs']

bot = telebot.TeleBot(os.environ.get("TelegramBotToken"))
# TARGET = "elonmusk"  # Target account to monitor
# CHECK_INTERVAL = 1   # Interval between checks in seconds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("script.log", mode='a')
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def callback(tweet: Tweet) -> None:
    logging.info(f"New tweet posted: {tweet.text}")
    await send_message_to_bot(your_message=tweet.text)
    bot.send_message(533017326,f"New tweet posted: {tweet.text}")

class MaxRetriesExceededError(Exception):
    """Custom exception for handling max retries exceeded."""
    pass

async def get_latest_tweet(user, client) -> list:
    try:
        return await client.get_user_tweets(user.id, "Tweets")
    except Exception as e:
        logging.error(f"Error while fetching latest tweets for user {user.name}: {e}")
        bot.send_message(533017326,f"Error while fetching latest tweets for user {user.name}: {e}")
        raise MaxRetriesExceededError(f"Max retries exceeded for client {client}")

async def initialize_clients():
    clients = []
    all_accounts = []
    failed_accounts = []
    successful_accounts = []
    
    # Get credentials from MongoDB
    credentials_docs = credentials_collection.find({})
    
    # First, collect all accounts (both offline and online)
    for doc in credentials_docs:
        # Get offline accounts first
        offline_accounts = doc.get('offline', [])
        for account in offline_accounts:
            account['offline'] = True
            all_accounts.append(account)
            
        # Then get regular accounts
        online_accounts = doc.get('accounts', [])
        for account in online_accounts:
            account['offline'] = False
            all_accounts.append(account)
    
    # Try to initialize clients for all accounts
    for account in all_accounts:
        try:
            # Add delay between account initialization attempts
            await asyncio.sleep(3)
            
            client = await get_or_create_client(account)
            if client:
                clients.append(client)
                successful_accounts.append(account['username'])
                logging.info(f"Successfully initialized client for {account['username']}")
            else:
                failed_accounts.append(account['username'])
                logging.warning(f"Failed to initialize client for {account['username']}")
        except Exception as e:
            failed_accounts.append(account['username'])
            logging.error(f"Failed to initialize client for {account.get('username', 'unknown')}: {e}")
    
    # Send summary message through telegram
    summary_message = (
        f"Client Initialization Summary:\n"
        f"✅ Successful ({len(successful_accounts)}): {', '.join(successful_accounts)}\n"
        f"❌ Failed ({len(failed_accounts)}): {', '.join(failed_accounts)}\n"
        f"Total clients initialized: {len(clients)}"
    )
    bot.send_message(533017326, summary_message)
    
    logging.info(f"{len(clients)} clients initialized successfully.")
    return clients

# --- Control flag and stop function ---
running = False

def stop_main():
    global running
    running = False
# ---

async def main(TARGET, CHECK_INTERVAL):
    global running
    running = True
    bot.send_message(533017326,f"Initializing clients...")
    clients = await initialize_clients()
    num_clients = len(clients)

    if num_clients == 0:
        logging.error("No clients initialized. Exiting...")
        bot.send_message(533017326,"No clients initialized. Exiting...")
        bot.send_message(533017326,f"script stopped")
        return

    index = 0
    logging.info(f"Requesting user info for target: {TARGET}")
    try:
        user = await clients[index].get_user_by_screen_name(TARGET)
    except Exception as e:
        logging.error(f"Failed to fetch user info for target {TARGET}: {e}")
        bot.send_message(533017326,f"Error while fetching latest tweets for user {TARGET}: {e}")
        bot.send_message(533017326,f"script stopped")
        return

    before_tweet = None
    bot.send_message(533017326,f"Searching for CA...")
    
    # Get configurations from MongoDB
    config = config_collection.find_one() or {}
    check_interval = config.get('interval', CHECK_INTERVAL)
    
    while running:
        if not before_tweet:
            try:
                logging.info(f"Fetching initial tweets using client index {index}.")
                before_tweet = await get_latest_tweet(user, clients[index])
            except MaxRetriesExceededError:
                logging.warning(f"Client at index {index} failed to fetch initial tweets.")
                index = (index + 1) % num_clients
                continue
            except Exception as e:
                logging.error(f"Unexpected error while fetching initial tweets: {e}")
                index = (index + 1) % num_clients
                continue

        logging.info("Waiting for the next check...")
        random_seconds = random.randint(0, 10)/10
        print(f"Sleeping for {check_interval + random_seconds} seconds")
        await asyncio.sleep(check_interval + random_seconds)

        index = (index + 1) % num_clients

        logging.info(f"Fetching latest tweets using client index: {index}")
        try:
            latest_tweet = await get_latest_tweet(user, clients[index])
        except MaxRetriesExceededError:
            logging.warning(f"Client at index {index} failed to fetch latest tweets.")
            continue
        except Exception as e:
            logging.error(f"Unexpected error while fetching latest tweets: {e}")
            continue

        difference = [item for item in latest_tweet if item not in before_tweet]

        if difference:
            for item in difference:
                index = (index + 1) % num_clients
                logging.info(f"Fetching full tweet details using client index: {index}")
                try:
                    tweet = await clients[index].get_tweet_by_id(item.id)
                    await callback(tweet)
                except Exception as e:
                    logging.error(f"Error fetching tweet details: {e}")
                    continue

        before_tweet = latest_tweet

    print("Main loop stopped.") # Indicate that the loop has exited

