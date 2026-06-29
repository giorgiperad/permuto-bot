import os
import requests
import time
import json
import websocket
import threading

BASE_URL = "https://perps.permuto.capital"

# ⚠️ აიღე ბრაუზერის დეველოპერული მენიუდან (F12) შენი ავტორიზებული სესიის ტოკენი (perps_session)
# და ჩასვი Railway-ის Variables-ში სახელად: PERPS_SESSION_TOKEN
SESSION_TOKEN = os.getenv("PERPS_SESSION_TOKEN", "აქ_ჩასვი_ტოკენი_თუ_ლოკალურად_ტესტავ")

HEADERS = {
    "Authorization": f"Bearer {SESSION_TOKEN}",
    "Content-Type": "application/json"
}

BASE_SPREAD = 0.007
MAX_TOTAL_EXPOSURE = 400.0

def get_mids():
    try:
        r = requests.get(f"{BASE_URL}/info/mids", timeout=10)
        return r.json().get("mids", {})
    except:
        return {}

def get_account_exposure():
    """ დოკუმენტაციით /exchange/account არის POST მოთხოვნა """
    try:
        r = requests.post(f"{BASE_URL}/exchange/account", json={}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            account_data = r.json()
            positions = account_data.get("positions", [])
            total_exposure = 0.0
            for pos in positions:
                total_exposure += abs(float(pos.get("size", 0.0)))
            return total_exposure
        elif r.status_code == 401:
            print("🚨 სესია ექსპირებულია! განაახლეთ PERPS_SESSION_TOKEN Railway-ზე.")
    except Exception as e:
        print(f"მოთხოვნის შეცდომა (Exposure): {e}")
    return 0.0

def calculate_size(mid):
    if mid > 0.25: return 25.0
    elif mid > 0.12: return 40.0
    else: return 55.0

def update_grid():
    if not SESSION_TOKEN or "აქ_ჩასვი" in SESSION_TOKEN:
        print("⏳ შეცდომა: PERPS_SESSION_TOKEN არ არის დაყენებული Variables-ში!")
        return

    current_exposure = get_account_exposure()
    if current_exposure >= MAX_TOTAL_EXPOSURE:
        print(f"⚠️ ლიმიტი შევსებულია ({current_exposure}/{MAX_TOTAL_EXPOSURE}). ახალი ორდერები დაიბლოკა.")
        return

    mids = get_mids()
    if not mids:
        return

    orders = []
    markets = ["QQQ-VOL-PERP", "NVDA-VOL-PERP", "TSLA-VOL-PERP"]
    
    for market in markets:
        mid = float(mids.get(market, 0.15))
        if mid < 0.05:
            continue

        size = calculate_size(mid)
        spread = BASE_SPREAD

        if mid > 0.2:
            spread = BASE_SPREAD * 0.85

        bid = round(mid * (1 - spread), 4)
        ask = round(mid * (1 + spread), 4)

        orders.append({"market": market, "side": "buy", "type": "limit", "price": str(bid), "size": str(size)})
        orders.append({"market": market, "side": "sell", "type": "limit", "price": str(ask), "size": str(size)})

    if not orders:
        return

    try:
        # დოკუმენტაციით /exchange/batch_upsert არის POST მოთხოვნა
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", json={"orders": orders}, headers=HEADERS, timeout=15)
        
        status = "✅" if r.status_code == 200 else f"❌ ({r.status_code})"
        print(f"[{time.strftime('%H:%M:%S')}] {status} Grid განახლდა | Exposure: {current_exposure:.1f}/{MAX_TOTAL_EXPOSURE}")
    except Exception as e:
        print(f"❌ ორდერების გაგზავნა ჩავარდა: {e}")

def ws_thread():
    def on_message(ws, msg):
        try:
            data = json.loads(msg)
            print("WS Channel:", data.get("channel", "unknown"))
        except:
            pass

    while True:
        try:
            ws = websocket.WebSocketApp("wss://perps.permuto.capital/ws", on_message=on_message)
            ws.run_forever(ping_interval=25)
        except:
            pass
        time.sleep(5)

# ვებზოკეტის გაშვება
threading.Thread(target=ws_thread, daemon=True).start()

print("🌟 Permuto Cup Sage-Based Bot v5.2 ჩაირთო!")
time.sleep(2)

while True:
    update_grid()
    time.sleep(20)
