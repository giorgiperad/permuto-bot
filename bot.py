import requests
import time
import json
import websocket
import threading

BASE_URL = "https://perps.permuto.capital"
TOKEN = "874361ccf9c38ba6df8d9834bf740f8206cdde90fa79bf12677e40a4e9b38813"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

MAX_POSITION = 150.0   # მაქსიმალური პოზიცია ერთ მარკეტზე
SPREAD = 0.007

ws = None

def get_meta():
    try:
        return requests.get(f"{BASE_URL}/info/meta", timeout=10).json()
    except:
        return None

def get_account():
    try:
        return requests.get(f"{BASE_URL}/exchange/account", headers=HEADERS, timeout=10).json()
    except:
        return None

def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("channel") == "bbo":
            print(f"Live BBO: {data['data']['market']} | Mark: {data['data'].get('markPrice')}")
    except:
        pass

def start_websocket():
    global ws
    try:
        ws = websocket.WebSocketApp(
            "wss://perps.permuto.capital/ws",
            on_message=on_message
        )
        ws.run_forever(ping_interval=20)
    except:
        pass

# WebSocket ძაფში
threading.Thread(target=start_websocket, daemon=True).start()

print("🚀 ჭკვიანი Permuto MM Bot v3 (WebSocket + Auto Sizing) დაწყებულია...")

while True:
    try:
        meta = get_meta()
        account = get_account()
        mids = requests.get(f"{BASE_URL}/info/mids").json().get("mids", {})

        orders = []
        for market in ["QQQ-VOL-PERP", "NVDA-VOL-PERP", "TSLA-VOL-PERP"]:
            mid = float(mids.get(market, 0.15))
            if mid < 0.05: 
                continue

            # Auto Position Sizing
            size = min(MAX_POSITION, max(20.0, MAX_POSITION * 0.6))

            bid_price = round(mid * (1 - SPREAD), 4)
            ask_price = round(mid * (1 + SPREAD), 4)

            orders.append({"market": market, "side": "buy", "type": "limit", "price": str(bid_price), "size": str(size)})
            orders.append({"market": market, "side": "sell", "type": "limit", "price": str(ask_price), "size": str(size)})

        if orders:
            r = requests.post(f"{BASE_URL}/exchange/batch_upsert", 
                             json={"orders": orders}, 
                             headers=HEADERS, 
                             timeout=15)
            print(f"[{time.strftime('%H:%M:%S')}] Smart Grid Updated | Status: {r.status_code}")

        time.sleep(20)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
