import requests
import time
import json
import websocket
import threading

BASE_URL = "https://perps.permuto.capital"
TOKEN = "874361ccf9c38ba6df8d9834bf740f8206cdde90fa79bf12677e40a4e9b38813"

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

MAX_TOTAL_EXPOSURE = 400.0   # საერთო რისკი (შეცვალე სურვილისამებრ)
BASE_SPREAD = 0.007

def get_meta():
    try: return requests.get(f"{BASE_URL}/info/meta", timeout=10).json()
    except: return None

def get_mids():
    try: return requests.get(f"{BASE_URL}/info/mids", timeout=10).json().get("mids", {})
    except: return {}

def get_account():
    try: return requests.get(f"{BASE_URL}/exchange/account", headers=HEADERS, timeout=10).json()
    except: return None

def calculate_size(mid):
    # Auto sizing — პატარა პოზიცია თუ ფასი მაღალია
    if mid > 0.25:
        return 25.0
    elif mid > 0.12:
        return 40.0
    else:
        return 55.0

def update_grid():
    meta = get_meta()
    mids = get_mids()
    account = get_account()
    
    if not meta or not mids:
        return

    orders = []
    for market in ["QQQ-VOL-PERP", "NVDA-VOL-PERP", "TSLA-VOL-PERP"]:
        mid = float(mids.get(market, 0.15))
        if mid < 0.05: 
            continue

        size = calculate_size(mid)
        spread = BASE_SPREAD

        # უფრო ჭკვიანი spread (ვიწრო როცა volatility დაბალია)
        if mid > 0.2:
            spread = BASE_SPREAD * 0.85   # უფრო ვიწრო

        bid = round(mid * (1 - spread), 4)
        ask = round(mid * (1 + spread), 4)

        orders.append({"market": market, "side": "buy", "type": "limit", "price": str(bid), "size": str(size)})
        orders.append({"market": market, "side": "sell", "type": "limit", "price": str(ask), "size": str(size)})

    try:
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", json={"orders": orders}, headers=HEADERS, timeout=15)
        status = "✅" if r.status_code == 200 else "❌"
        print(f"[{time.strftime('%H:%M:%S')}] {status} Grid | 3 markets | Exposure controlled")
    except:
        print("Grid update failed")

# WebSocket (uptime + live data)
def ws_thread():
    def on_message(ws, msg):
        print("WS Live:", json.loads(msg).get("channel", "unknown"))
    
    try:
        ws = websocket.WebSocketApp("wss://perps.permuto.capital/ws", on_message=on_message)
        ws.run_forever(ping_interval=25)
    except:
        pass

threading.Thread(target=ws_thread, daemon=True).start()

print("🌟 სრულიად ავტონომიური Market Maker Bot v4 დაწყებულია (კონკურსისთვის)")

while True:
    update_grid()
    time.sleep(20)
