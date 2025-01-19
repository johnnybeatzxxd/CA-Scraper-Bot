from twikit import Client
import asyncio
import json
import traceback
CLIENT_CACHE = {}
async def test_account(client,username):
    try:
        await client.get_user_tweets(username,"Replies")
        print(f"Logged in successfully for {username}.")
        return True
    except Exception as e:
        print(f"bad news account suspended: {e}")
        return False

async def get_or_create_client(account, file_path='cookies.json'):
    """Get or create a logged-in client for the given account."""
    global CLIENT_CACHE
    username = account["username"]

    if username in CLIENT_CACHE:
        print("Found logged-in client in cache and returned")
        return CLIENT_CACHE[username]

    try:
        client = Client('en-US')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f) 
                client.set_cookies(cookies)
            print("Loaded cookies and initialized client.")
        except FileNotFoundError:
            print("Cookies not found, logging in with credentials.")
            await client.login(
                auth_info_1=account["username"],
                auth_info_2=account["phone"],
                password=account["password"]
                # totp_secret=account["totp"]  # Uncomment if needed
            )
            print(f"Logged in successfully for {username}.")

            cookies = client.get_cookies()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f)
            print(f"Cookies saved to {file_path}.")

        CLIENT_CACHE[username] = client
        return client

    except Exception as e:
        print(f"Error initializing client for {username}: {e}")
        traceback.print_exc()
        return None
