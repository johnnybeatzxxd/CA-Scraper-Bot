from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")  

client = TelegramClient("user_session", API_ID, API_HASH)

async def send_message_to_bot(bot_username: str = "johnnybeatz", your_message: str = "Hello ") -> None:
    print("Sending message to bot...")
    await client.start(phone=PHONE_NUMBER)

    await client.send_message(bot_username, your_message)
    print("Message sent!")

    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(send_message_to_bot())

