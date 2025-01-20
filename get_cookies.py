from twikit import Client
import asyncio
import json
import traceback

async def save_cookies_locally(account, file_path='cookies.json'):
    try:
        client = Client('en-US')
        await client.login(
            auth_info_1=account["username"],
            auth_info_2=account["email"],
            password=account["password"]
            # totp_secret=account["totp"]  
        )
        print("Logged in successfully.")

        cookies = client.get_cookies()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f)
        print(f"Cookies saved to {file_path}.")

    except Exception as e:
        print(f"Error logging in and saving cookies: {e}")
        traceback.print_exc()

