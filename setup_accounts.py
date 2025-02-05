import json
import re
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from pymongo.operations import UpdateOne

# MongoDB Setup
MONGO_URL = os.getenv('MONGO_URL')
client = MongoClient(MONGO_URL)
db = client['CA-Hunter']
credentials_collection = db['credentials']
cookies_collection = db["cookies"]

def parse_accounts(filename='accounts.txt'):
    accounts = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                # Skip empty lines and header/footer content
                line = line.strip()
                
                if (not line or 
                    line.startswith('=') or 
                    'Заказ' in line or 
                    '↓' in line or 
                    'https://' in line):
                    continue
        
                # Parse only lines that look like credentials
                if ':' in line:
                    parts = line.split(':')
                    
                    if len(parts) >= 8:  # Ensure we have all required fields
                        account = {
                            'username': parts[0],
                            'password': parts[1],
                            'email': parts[2],
                            'email_pass': parts[3],
                            'auth_token': parts[4],
                            'ct0': parts[5],
                            'cookies': parts[6],
                            'user_agent': parts[7]
                        }
                        accounts.append(account)
                        print(f"Successfully parsed account: {account['username']}")  # Debug line
    
    except FileNotFoundError:
        print(f"Error: {filename} not found in current directory")
        return None
    except Exception as e:
        print(f"Error parsing file: {str(e)}")
        return None

    print(f"Total accounts parsed: {len(accounts)}")  # Debug line
    return accounts

def setup_accounts():
    load_dotenv()
    
    accounts = parse_accounts()
    if not accounts:
        return []
        
    try:
        # Get existing accounts in a single query
        existing_doc = credentials_collection.find_one({}, {'accounts.username': 1, 'offline.username': 1})
        
        # Extract usernames more efficiently
        existing_usernames = set()
        if existing_doc:
            if 'accounts' in existing_doc:
                existing_usernames.update(acc['username'] for acc in existing_doc['accounts'])
            if 'offline' in existing_doc:
                existing_usernames.update(acc['username'] for acc in existing_doc['offline'])
        
        # Filter out existing accounts
        new_accounts = [acc for acc in accounts if acc['username'] not in existing_usernames]
        
        if not new_accounts:
            print("No new accounts to add - all usernames already exist in database")
            return []

        # Prepare bulk cookie operations
        cookie_operations = []
        for account in new_accounts:
            if 'auth_token' in account and 'ct0' in account:
                cookie_data = {
                    "username": account["username"],
                    "cookies": {
                        "auth_token": account['auth_token'],
                        "ct0": account['ct0'],
                    }
                }
                cookie_operations.append(UpdateOne(
                    {account['username']: {"$exists": True}},
                    {"$set": cookie_data},
                    upsert=True
                ))

        # Perform bulk operations
        if new_accounts:
            credentials_collection.update_one(
                {},
                {'$push': {'accounts': {'$each': new_accounts}}},
                upsert=True
            )
            print(f"Successfully added {len(new_accounts)} new accounts to credentials collection")

        if cookie_operations:
            cookies_collection.bulk_write(cookie_operations)
            print(f"Saved cookies for {len(cookie_operations)} accounts")
        
        print(f"Skipped {len(accounts) - len(new_accounts)} existing accounts")
        return new_accounts
        
    except Exception as e:
        print(f"Error saving to MongoDB: {str(e)}")
        return []

if __name__ == "__main__":
    setup_accounts()
