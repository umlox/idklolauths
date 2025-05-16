from flask import Flask, request
import aiohttp
import asyncio
import os
import datetime
import sqlite3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DB_PATH = 'users.db'
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Flask app
app = Flask(__name__)

# SQLite DB setup
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

async def send_to_webhook(user_data):
    if not WEBHOOK_URL:
        print("⚠️ WEBHOOK_URL not set.")
        return

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
            async with session.post(WEBHOOK_URL, json={"embeds": [embed]}) as response:
                if response.status == 204:
                    print("✅ Webhook sent successfully.")
                else:
                    print(f"❌ Webhook failed: HTTP {response.status}")
    except Exception as e:
        print(f"❌ Error sending webhook: {e}")

async def process_oauth(code, guild_id):
    print(f"🔄 Processing OAuth for guild: {guild_id}")

    async with aiohttp.ClientSession() as session:
        token_url = "https://discord.com/api/oauth2/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI
        }

        async with session.post(token_url, data=data) as response:
            token_data = await response.json()

            if 'access_token' not in token_data:
                print("❌ Failed to get access token:", token_data)
                return False

            headers = {'Authorization': f"Bearer {token_data['access_token']}"}
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as me_response:
                user_data = await me_response.json()

            user_doc = {
                'id': user_data.get('id'),
                'username': user_data.get('username'),
                'email': user_data.get('email'),
                'avatar': user_data.get('avatar'),
                'token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token'),
                'token_type': token_data.get('token_type'),
                'scope': token_data.get('scope', ''),
                'guild_id': guild_id,
                'auth_date': datetime.datetime.utcnow().isoformat()
            }

            try:
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
                print(f"✅ Auth saved for: {user_doc['username']}")
                await send_to_webhook(user_doc)
                return True
            except Exception as e:
                print(f"❌ Database error: {e}")
                return False

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('guild_id', '')

    print(f"📥 Callback received with code: {code}")

    if not code:
        return "❌ No authorization code provided."

    try:
        result = asyncio.run(process_oauth(code, guild_id))
        if result:
            return """
                <html>
                <head>
                    <style>
                        body {
                            background-color: #000;
                            color: white;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            font-family: Arial, sans-serif;
                        }
                        .auth-box {
                            background: linear-gradient(45deg, #9b42f5, #7a19f3);
                            padding: 30px 50px;
                            border-radius: 15px;
                            box-shadow: 0 0 20px rgba(155, 66, 245, 0.5);
                            text-align: center;
                        }
                    </style>
                </head>
                <body>
                    <div class="auth-box">
                        ✨ Authorization Successful!
                    </div>
                    <script>
                        setTimeout(() => window.close(), 3000);
                    </script>
                </body>
                </html>
            """
        else:
            return "❌ Authorization failed."
    except Exception as e:
        print(f"❌ Error during OAuth: {e}")
        return "⚠️ An error occurred while processing your request."

@app.route('/')
def home():
    return "✅ OAuth server is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
