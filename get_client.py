from twikit import Client
import asyncio
import json
import logging

logging.basicConfig(
    level=logging.INFO,  
    format='%(asctime)s - %(levelname)s - %(message)s',  
    handlers=[
        logging.StreamHandler(),  
        logging.FileHandler("script.log", mode='a')  
    ]
)

# Optional: Suppress verbose logs from third-party libraries like `httpx`
logging.getLogger("httpx").setLevel(logging.WARNING)

async def test_account(client, username):
    state = await client._get_user_state()
    logging.info(f"Account state for {username}: {state}")
    if state == "suspended":
        logging.warning(f"Account suspended: {username}")
        return False
    logging.info(f"Logged in successfully for {username}.")
    return True

async def get_or_create_client(account, file_path='cookies.json'):
    username = account["username"]

    try:
        client = Client('en-US')
        cookies = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)

            cookie = cookies.get(username)
            if cookie:
                client.set_cookies(cookie)
                if not await test_account(client, username):
                    cookies.pop(username, None)
                    save_cookies(file_path, cookies)
                    return None
            else:
                raise ValueError("No valid cookie found for this account.")
        except (FileNotFoundError, ValueError):
            logging.info(f"Logging in for {username}.")
            await client.login(
                auth_info_1=account["username"],
                auth_info_2=account["email"],
                password=account["password"]
            )
            if not await test_account(client, username):
                return None
            cookies[username] = client.get_cookies()
            save_cookies(file_path, cookies)

        return client

    except Exception as e:
        logging.error(f"Error initializing client for {username}: {e}")
        return None

def save_cookies(file_path, cookies):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, indent=2)
    logging.info(f"Cookies saved to {file_path}.")

