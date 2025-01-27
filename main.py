import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet
from get_client import get_or_create_client  
from send_message import send_message_to_bot
import logging
import random
import telebot
from get_ca import get_contract
from pymongo import MongoClient
from datetime import datetime, timedelta

load_dotenv()

# MongoDB Setup
MONGO_URL = os.getenv('MONGO_URL')
mongo_client = MongoClient(MONGO_URL)
db = mongo_client['CA-Hunter']  # Replace with your database name
credentials_collection = db['credentials']
config_collection = db['configs']

ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")

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
    logging.info(f"New tweet posted: {tweet.text}")
    logging.info(f"tweet created at: {tweet.created_at}")
    
    # Parse tweet creation time and check if it's older than 2 minutes
    tweet_time = datetime.strptime(tweet.created_at, "%a %b %d %H:%M:%S %z %Y")
    current_time = datetime.now(tweet_time.tzinfo)
    time_difference = current_time - tweet_time
    logging.info(time_difference)
    if time_difference > timedelta(minutes=2):
        logging.info("Tweet is older than 2 minutes, skipping processing")
        return
    
    if tweet.retweeted_tweet:
        logging.info("its retweets so im passing!")
        return
    result = get_contract(tweet)

    if result:
        await send_message_to_bot(your_message=result[0])  # Now this await is valid
        bot.send_message(ADMIN_USER_ID,f"New tweet posted: {tweet.text}")
        bot.send_message(ADMIN_USER_ID,f"Contract Address Found: {result[0]}\n")
        return      
    bot.send_message(ADMIN_USER_ID,f"New tweet posted: {tweet.text}")
    bot.send_message(ADMIN_USER_ID,f"No CA Found!")

class MaxRetriesExceededError(Exception):
    """Custom exception for handling max retries exceeded."""
    pass

class RateLimitError(Exception):
    """Custom exception for handling rate limits."""
    pass

async def get_latest_tweet(user, client) -> list:
    try:
        return await client.get_user_tweets(user.id, "Tweets")
    except Exception as e:
        if "Rate limit exceeded" in str(e) or "code':88" in str(e):
            raise RateLimitError(f"Rate limit exceeded for client")
        logging.error(f"Error while fetching latest tweets for user {user.name}: {e}")
        bot.send_message(ADMIN_USER_ID,f"Error while fetching latest tweets for user {user.name}: {e}")
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
            # await asyncio.sleep(3)
            
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
        f"Client Initialization Summary:\n\n"
        f"✅ Successful ({len(successful_accounts)}): {', '.join(successful_accounts)}\n"
        f"❌ Failed ({len(failed_accounts)}): {', '.join(failed_accounts)}\n\n"
        f"Total clients initialized: {len(clients)}"
    )
    bot.send_message(ADMIN_USER_ID, summary_message)
    
    logging.info(f"{len(clients)} clients initialized successfully.")
    return clients

# --- Control flag and stop function ---
running = False

def stop_main():
    global running
    running = False
# ---

def recalculate_interval(num_clients):
    RATE_LIMIT_REQUESTS = 50 
    RATE_LIMIT_WINDOW = 15 * 60
    
    total_requests_per_window = RATE_LIMIT_REQUESTS * num_clients
    # Add 20% safety margin
    safe_interval = (RATE_LIMIT_WINDOW / total_requests_per_window) * 1.2
    return safe_interval

async def main(TARGET, CHECK_INTERVAL):
    global running
    running = True
    bot.send_message(ADMIN_USER_ID,f"Initializing clients...")
    clients = await initialize_clients()
    num_clients = len(clients)

    if num_clients == 0:
        logging.error("No clients initialized. Exiting...")
        bot.send_message(ADMIN_USER_ID,"No clients initialized. Exiting...")
        bot.send_message(ADMIN_USER_ID,f"script stopped")
        return

    #
    RATE_LIMIT_REQUESTS = 50 
    RATE_LIMIT_WINDOW = 15 * 60  
    
    # Calculate requests per second we can make with all clients combined
    total_requests_per_window = RATE_LIMIT_REQUESTS * num_clients
    # Add 20% safety margin to avoid hitting limits
    safe_interval = (RATE_LIMIT_WINDOW / total_requests_per_window) * 1.2
    
    # Use the calculated interval or the minimum CHECK_INTERVAL, whichever is larger
    check_interval = safe_interval
    
    logging.info(f"Calculated interval: {check_interval:.2f} seconds with {num_clients} clients")
    #bot.send_message(533017326, f"Running with interval: {check_interval:.2f} seconds using {num_clients} clients")

    index = 0
    logging.info(f"Requesting user info for target: {TARGET}")
    try:
        user = await clients[index].get_user_by_screen_name(TARGET)
    except Exception as e:
        logging.error(f"Failed to fetch user info for target {TARGET}: {e}")
        bot.send_message(ADMIN_USER_ID,f"Failed to fetch user info for target {TARGET}: {e}")
        bot.send_message(ADMIN_USER_ID,f"script stopped")
        return

    before_tweet = None
    bot.send_message(ADMIN_USER_ID,f"Searching for CA...")
    
    while running:
        if not before_tweet:
            try:
                logging.info(f"Fetching initial tweets using client index {index}.")
                before_tweet = await get_latest_tweet(user, clients[index])
            except RateLimitError:
                logging.warning(f"Rate limit hit for client {index}, removing client")
                bot.send_message(ADMIN_USER_ID, f"⚠️ Client {index} rate limited and removed. Recalculating interval...")
                clients.pop(index)
                if not clients:
                    bot.send_message(ADMIN_USER_ID, "❌ No clients remaining. Stopping script.")
                    return
                check_interval = recalculate_interval(len(clients))
                index = index % len(clients)
                continue
            except MaxRetriesExceededError:
                logging.warning(f"Client at index {index} failed to fetch initial tweets.")
                index = (index + 1) % len(clients)
                continue
            except Exception as e:
                logging.error(f"Unexpected error while fetching initial tweets: {e}")
                index = (index + 1) % len(clients)
                continue

        logging.info("Waiting for the next check...")
        random_seconds = random.randint(0, 3)/10
        print(f"Sleeping for {check_interval + random_seconds} seconds")
        await asyncio.sleep(check_interval + random_seconds)

        index = (index + 1) % len(clients)

        logging.info(f"Fetching latest tweets using client index: {index}")
        try:
            latest_tweet = await get_latest_tweet(user, clients[index])
        except RateLimitError:
            logging.warning(f"Rate limit hit for client {index}, removing client")
            bot.send_message(ADMIN_USER_ID, f"⚠️ Client {index} rate limited and removed. Recalculating interval...")
            clients.pop(index)
            if not clients:
                bot.send_message(ADMIN_USER_ID, "❌ No clients remaining. Stopping script.")
                return
            check_interval = recalculate_interval(len(clients))
            index = index % len(clients)
            continue
        except MaxRetriesExceededError:
            logging.warning(f"Client at index {index} failed to fetch latest tweets.")
            continue
        except Exception as e:
            logging.error(f"Unexpected error while fetching latest tweets: {e}")
            continue

        difference = [item for item in latest_tweet if item not in before_tweet]

        if difference:
            for item in difference:
                index = (index + 1) % len(clients)
                logging.info(f"Fetching full tweet details using client index: {index}")
                try:
                    tweet = await clients[index].get_tweet_by_id(item.id)
                    await callback(tweet)
                except Exception as e:
                    logging.error(f"Error fetching tweet details: {e}")
                    continue

        before_tweet = latest_tweet

    print("Main loop stopped.") # Indicate that the loop has exited

