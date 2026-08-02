# ============================================================
# TELEGRAM TEST SCRIPT
# ============================================================
import os
import httpx
import json

def test_telegram():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "8875705717:AAEsq786bJYypamBCokHlMvOJAVjKTPb82I")
    
    if not bot_token:
        print("❌ No bot token found")
        return
    
    print("🤖 Testing Telegram bot...")
    
    # Test getMe
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = httpx.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("ok"):
                    print(f"✅ Bot is online: {data.get('result', {}).get('username')}")
                else:
                    print(f"❌ Bot error: {data}")
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response: {response.text[:100]}")
        else:
            print(f"❌ HTTP error: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_telegram()
