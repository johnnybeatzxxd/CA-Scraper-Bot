import asyncio
from dotenv import load_dotenv
import os
from twikit import Client, Tweet


load_dotenv()
client = Client("en-US")

TARGET = "JohnnyBeatz_"
CHECK_INTERVAL = 1

# LOGIN
USERNAME = os.getenv("USERNAME")
EMAIL = os.getenv("EMAIL") 
PASSWORD = os.getenv("PASSWORD") 


def callback(tweet: Tweet) -> None:
    print(tweet.reply_to, tweet.in_reply_to)
    print(f'New tweet posted : {tweet.text}')


async def get_latest_tweet(user) -> Tweet:
    return await client.get_user_tweets(user.id, "Replies")


async def main():

    await client.login(
        auth_info_1=USERNAME,
        auth_info_2=EMAIL,
        password=PASSWORD
    )

    user = await client.get_user_by_screen_name(TARGET)
    print("this is the user: ", user)
    before_tweet = await get_latest_tweet(user)

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        latest_tweet = await get_latest_tweet(user)
        print(before_tweet)
        print(latest_tweet)

        difference = [item for item in latest_tweet if item not in before_tweet]

        if difference:
            for item in difference:
                tweet = await client.get_tweet_by_id(item.id)
                callback(tweet)

        before_tweet = latest_tweet

asyncio.run(main())
