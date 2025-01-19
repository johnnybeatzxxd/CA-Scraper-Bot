import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet
from get_client import get_or_create_client
from get_cookies import save_cookies_locally
import json

load_dotenv()

USERNAME = os.getenv("USERNAME")
EMAIL = os.getenv("EMAIL") 
PASSWORD = os.getenv("PASSWORD") 

TARGET = "johnnyxxdpro" 

CHECK_INTERVAL = 10  

account = {
    "username": USERNAME,
    "email": EMAIL,
    "password": PASSWORD,
}

def callback(tweet: Tweet) -> None:
    print(tweet.reply_to, tweet.in_reply_to)
    print(f'New tweet posted : {tweet.text}')


async def get_latest_tweet(user,client) -> Tweet:
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

async def main():

    username = account.get("username")
    while True:
        client = await get_or_create_client(account)
        try:
            user = await client.get_user_by_screen_name(TARGET)
            break
        except Exception as e:
            print(f"Error:{e}")
            await asyncio.sleep(10)
            await remove_cookie_alternative("cookies.json",username)

    print("this is the user: ", user.screen_name)
    before_tweet = await get_latest_tweet(user,client)

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        latest_tweet = await get_latest_tweet(user,client)
        print(latest_tweet)

        difference = [item for item in latest_tweet if item not in before_tweet]

        if difference:
            for item in difference:
                tweet = await client.get_tweet_by_id(item.id)
                callback(tweet)

        before_tweet = latest_tweet

asyncio.run(main())
