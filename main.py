import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet
from get_client import get_or_create_client
from get_cookies import save_cookies_locally
from send_message import send_message_to_bot
import json

load_dotenv()

TARGET = "elonmusk" 

CHECK_INTERVAL = 5  


async def callback(tweet: Tweet) -> None:
    print(tweet.reply_to, tweet.in_reply_to)
    print(f'New tweet posted : {tweet.text}')
    await send_message_to_bot(your_message=tweet.text)


async def get_latest_tweet(user,client) -> Tweet:
    try:
        return await client.get_user_tweets(user.id, "Replies")
    except:
        return await client.get_user_tweets(user.id, "Replies")


def remove_cookie_alternative(filepath, name_to_remove):

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found.")
        return

    new_data = {
        key: value
        for key, value in data.items()
        if key != name_to_remove
    }

    if len(new_data) == len(data):
        print(f"Error: No cookie entry found for '{name_to_remove}'.")
        return
    
    with open(filepath, 'w') as f:
        json.dump(new_data, f, indent=2)
    print(f"Cookie entry for '{name_to_remove}' removed and file saved.")

async def initialize_clients():

    clients = []
    with open("credintials.json","r") as f:
        credintials = json.load(f)

    for account in credintials["accounts"]:
        try:
            client = await get_or_create_client(account)
        except Exception as e:
            print(f"Error initializing client for {account['username']}: {e}")
            continue
        if client:
            clients.append(client)
    print(len(clients),"clients initialized.")
    return clients

async def main():

    clients = await initialize_clients()
    num_clients = len(clients)

    index = 0
    print("user obj request sent with index: ", index)
    user = await clients[index].get_user_by_screen_name(TARGET)
    await asyncio.sleep(CHECK_INTERVAL)
    print("request sent with index: ", index)
    before_tweet = await get_latest_tweet(user,clients[index])

    while True:

        print("waiting for the next check...")
        await asyncio.sleep(CHECK_INTERVAL)
        if index == num_clients - 1:
            index = 0
        else:
            index = index + 1 

        print("request sent with index: ", index)
        latest_tweet = await get_latest_tweet(user,clients[index])
        print(latest_tweet)

        difference = [item for item in latest_tweet if item not in before_tweet]

        if difference:
            for item in difference:
                if index == num_clients - 1:
                    index = 0
                else:
                    index = index + 1 
                print("request sent with index: ", index)
                tweet = await clients[index].get_tweet_by_id(item.id)
                await callback(tweet)

        before_tweet = latest_tweet

asyncio.run(main())
