from pymongo import MongoClient
import json
import os
from dotenv import load_dotenv

load_dotenv()

def connect_to_mongodb():
    MONGO_URL = os.getenv('MONGO_URL')
    client = MongoClient(MONGO_URL)
    db = client['CA-Hunter']
    return db

def migrate_configs():
    db = connect_to_mongodb()
    config_collection = db['configs']
    
    # Read configs.json
    try:
        with open('configs.json', 'r') as f:
            configs = json.load(f)
        
        # Insert or update configs
        config_collection.update_one(
            {},  # Empty filter to match any document
            {'$set': configs},
            upsert=True
        )
        print("✅ Configs migrated successfully")
    except Exception as e:
        print(f"❌ Error migrating configs: {e}")

def migrate_credentials():
    db = connect_to_mongodb()
    credentials_collection = db['credentials']
    
    # Read credentials.json
    try:
        with open('credintials.json', 'r') as f:
            credentials = json.load(f)
        
        # Insert credentials
        credentials_collection.insert_one(credentials)
        print("✅ Credentials migrated successfully")
    except Exception as e:
        print(f"❌ Error migrating credentials: {e}")

def migrate_cookies():
    db = connect_to_mongodb()
    cookies_collection = db['cookies']
    
    # Read cookies.json
    try:
        with open('cookies.json', 'r') as f:
            cookies_data = json.load(f)
        
        # Convert the cookies data structure to array of documents
        cookies_documents = []
        for username, cookies in cookies_data.items():
            cookies_documents.append({
                'username': username,
                'cookies': cookies
            })
        
        # Insert cookies
        if cookies_documents:
            cookies_collection.insert_many(cookies_documents)
        print("✅ Cookies migrated successfully")
    except Exception as e:
        print(f"❌ Error migrating cookies: {e}")

def main():
    print("🚀 Starting migration process...")
    
    # Clear existing collections
    db = connect_to_mongodb()
    try:
        db.configs.drop()
        db.credentials.drop()
        db.cookies.drop()
        print("🗑️  Cleared existing collections")
    except Exception as e:
        print(f"⚠️  Warning while clearing collections: {e}")
    
    # Perform migrations
    migrate_configs()
    migrate_credentials()
    migrate_cookies()
    
    print("✨ Migration completed!")

if __name__ == "__main__":
    main()