from twikit import Client
import asyncio
import json
import traceback

async def test_account(client,username):
    state = await client._get_user_state()
    if state == "suspended":
        print(f"bad news account suspended: {username}")
        return False
    print(f"Logged in successfully for {username}.")
    return True

async def get_or_create_client(account, file_path='cookies.json'):
    """Get or create a logged-in client for the given account."""
    username = account["username"]

    try:
        client = Client('en-US')
        try:

            with open(file_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f) 
                cookie = cookies.get(username,None)
                if cookie:
                    client.set_cookies(cookie)
                    print("Loaded cookies and initialized client.")
                    status = await test_account(client,username)
                    if not status:
                        return None
                else:
                    raise FileNotFoundError("Saved cookie not found!")
        except FileNotFoundError:
            print("Cookies not found, logging in with credentials.")
            await client.login(
                auth_info_1=account["username"],
                auth_info_2=account["email"],
                password=account["password"]
                # totp_secret=account["totp"]  # Uncomment if needed
            )
            print(f"Logged in successfully for {username}.")
            status  = await test_account(client,username)

            if not status:
                print(f"bad news account suspended: {e}")
                return None

            cookie = client.get_cookies()
            cookies[username] = cookie

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2)
            print(f"Cookies saved to {file_path}.")

        return client

    except Exception as e:
        print(f"Error initializing client for {username}: {e}")
        traceback.print_exc()
        return None
