from flask import Flask, request
import aiohttp
import asyncio
import os
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()

# Initialize MongoDB connection
client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017'))
db = client.get_database()  # Use the default database or specify a name here
users_collection = db.users  # The collection to store user data

app = Flask(__name__)

async def send_to_webhook(user_data):
    webhook_url = os.getenv('WEBHOOK_URL')
    print(f"Sending webhook for user: {user_data.get('username')}")
    
    embed = {
        "title": "🔐 New Authorization",
        "color": 0x2b2d31,
        "fields": [
            {
                "name": "👤 User",
                "value": f"{user_data.get('username')} (`{user_data.get('id')}`)",
                "inline": True
            },
            {
                "name": "📧 Email",
                "value": user_data.get('email', 'Not provided'),
                "inline": True
            }
        ],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "footer": {
            "text": "🎡 @2vsq for auth bots"
        }
    }
    
    async with aiohttp.ClientSession() as session:
        await session.post(webhook_url, json={"embeds": [embed]})

async def process_oauth(code):
    guild_id = request.args.get('guild_id', '')
    print(f"Processing OAuth for guild: {guild_id}")
    
    async with aiohttp.ClientSession() as session:
        token_url = "https://discord.com/api/oauth2/token"
        data = {
            "client_id": os.getenv('CLIENT_ID'),
            "client_secret": os.getenv('CLIENT_SECRET'),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.getenv('REDIRECT_URI')
        }
        
        async with session.post(token_url, data=data) as response:
            token_data = await response.json()
            
            if 'access_token' in token_data:
                headers = {'Authorization': f"Bearer {token_data['access_token']}"}
                async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as me_response:
                    user_data = await me_response.json()
                    print(f"Saving auth for: {user_data.get('username')}")
                    
                    # Insert or update user in MongoDB
                    try:
                        # Check if the user already exists in the database
                        existing_user = users_collection.find_one({"id": user_data.get('id')})
                        if existing_user:
                            # Update the user data if it already exists
                            users_collection.update_one(
                                {"id": user_data.get('id')},
                                {"$set": {
                                    "username": user_data.get('username'),
                                    "email": user_data.get('email'),
                                    "avatar": user_data.get('avatar'),
                                    "token": token_data.get('access_token'),
                                    "guild_id": guild_id,
                                    "auth_date": datetime.datetime.utcnow()
                                }}
                            )
                        else:
                            # Insert a new user
                            users_collection.insert_one({
                                "id": user_data.get('id'),
                                "username": user_data.get('username'),
                                "email": user_data.get('email'),
                                "avatar": user_data.get('avatar'),
                                "token": token_data.get('access_token'),
                                "guild_id": guild_id,
                                "auth_date": datetime.datetime.utcnow()
                            })
                        
                        print(f"Auth saved successfully for {user_data.get('username')}!")
                    except Exception as e:
                        print(f"Database error: {e}")
                        raise
                    
                    await send_to_webhook(user_data)
                    return True
    return False

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('guild_id')
    
    if code:
        try:
            result = asyncio.run(process_oauth(code))
            print(f"New auth saved: {result}")
            return "✅ Authorization successful! You can close this window."
        except Exception as e:
            print(f"Error during OAuth process: {e}")
            return "Authorization processing..."
    return "Ready for authorization"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
