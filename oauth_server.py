from flask import Flask, request
import aiohttp
import asyncio
import os
import datetime
import redis
from dotenv import load_dotenv

load_dotenv()

# Redis setup
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True
)

app = Flask(__name__)

async def send_to_webhook(user_data):
    webhook_url = os.getenv('WEBHOOK_URL')
    
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
        async with session.post(webhook_url, json={"embeds": [embed]}) as response:
            return response.status == 204

async def process_oauth(code):
    guild_id = request.args.get('guild_id', '')
    
    async with aiohttp.ClientSession() as session:
        # Token exchange
        token_data = await exchange_token(session, code)
        if not token_data or 'access_token' not in token_data:
            return False
            
        # Get user data
        user_data = await get_user_data(session, token_data['access_token'])
        if not user_data:
            return False
            
        # Store in Redis
        user_key = f"user:{user_data['id']}"
        user_doc = {
            'username': user_data['username'],
            'email': user_data.get('email', ''),
            'avatar': user_data.get('avatar', ''),
            'token': token_data['access_token'],
            'guild_id': guild_id,
            'auth_date': datetime.datetime.utcnow().isoformat()
        }
        
        # Store with pipeline for atomicity
        pipe = redis_client.pipeline()
        pipe.hmset(user_key, user_doc)
        pipe.sadd('active_users', user_data['id'])
        pipe.execute()

        # Send webhook
        await send_to_webhook(user_data)
        return True

async def exchange_token(session, code):
    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": os.getenv('CLIENT_ID'),
        "client_secret": os.getenv('CLIENT_SECRET'),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.getenv('REDIRECT_URI')
    }
    
    async with session.post(token_url, data=data) as response:
        return await response.json() if response.status == 200 else None

async def get_user_data(session, access_token):
    headers = {'Authorization': f"Bearer {access_token}"}
    async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as response:
        return await response.json() if response.status == 200 else None

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Ready for authorization"
        
    try:
        result = asyncio.run(process_oauth(code))
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
                            from { box-shadow: 0 0 20px rgba(155, 66, 245, 0.5); }
                            to { box-shadow: 0 0 30px rgba(155, 66, 245, 0.8); }
                        }
                    </style>
                </head>
                <body>
                    <div class="auth-box">
                        <div style="font-size: 24px; margin-bottom: 10px">✨</div>
                        Authorization Successful!
                    </div>
                    <script>setTimeout(() => window.close(), 3000);</script>
                </body>
                </html>
            """
        return "❌ Authorization failed. Please try again."
    except Exception as e:
        return "Authorization processing..."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
