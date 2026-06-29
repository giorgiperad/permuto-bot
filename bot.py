import os
import requests
import time
import json
import websocket
import threading

BASE_URL = "https://perps.permuto.capital"

# შენი სესიის ტოკენი
SESSION_TOKEN = "874361ccf9c38ba6df8d9834bf740f8206cdde90fa79bf12677e40a4e9b38813"

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
    try:
        r = requests.post(f"{BASE_URL}/exchange/account", json={}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            account_data = r.json()
            positions = account_data.get("positions", [])
            total_exposure = 0.0
            for pos in positions:
                total_exposure += abs(float(pos.get("size", 0.0)))
            return total_exposure
    except:
        pass
    return 0.0

def calculate_size(mid):
    if mid > 0.25: return 25.0
    elif mid > 0.12: return 40.0
    else: return 55.0

def update_grid():
    current_exposure = get_account_exposure()
    if current_exposure >= MAX_TOTAL_EXPOSURE:
        print(f"⚠️ ექსპოზიციის ლიმიტი შევსებულია ({current_exposure}/{MAX_TOTAL_EXPOSURE}).")
        return

    mids = get_mids()
    if not mids:
        return

    orders = []
    markets = ["QQQ-VOL-PERP", "NVDA-VOL-PERP", "TSLA-VOL-PERP"]
    
    for market in markets:
        mid = float(mids.get(market, 0.15))
        if mid < 0.01: # ვოლატილობის ბაზრებისთვის მინიმალური ზღვარი შევამციროთ
            continue

        size = calculate_size(mid)
        spread = BASE_SPREAD

        if mid > 0.2:
            spread = BASE_SPREAD * 0.85

        # დამრგვალება მეტ ნიშნამდე (5 ნიშანი), რადგან ვოლატილობის მარკეტებზე ფასები პატარაა
        bid = round(mid * (1 - spread), 5)
        ask = round(mid * (1 + spread), 5)

        # 🛑 ცვლილება: "price" და "size" გადაეცემა როგორც float რიცხვი და არა სტრინგი ("")
        # ასევე დამატებულია "asset" ველი ყოველი შემთხვევისთვის, თუ API ითხოვს
        orders.append({
            "market": market,
            "asset": market.split("-")[0], 
            "side": "buy",
            "type": "limit",
            "price": bid,
            "size": size,
            "reduce_only": False
        })
        orders.append({
            "market": market,
            "asset": market.split("-")[0],
            "side": "sell",
            "type": "limit",
            "price": ask,
            "size": size,
            "reduce_only": False
        })

    if not orders:
        return

    try:
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", json={"orders": orders}, headers=HEADERS, timeout=15)
        
        if r.status_code == 200:
            print(f"[{time.strftime('%H:%M:%S')}] ✅ Grid წარმატებით განახლდა | Exposure: {current_exposure:.1f}")
        else:
            # თუ მაინც 422 ამოაგდო, დავბეჭდოთ სერვერის ზუსტი პასუხი, რომ გავიგოთ რა არ მოსწონს JSON-ში
            print(f"[{time.strftime('%H:%M:%S')}] ❌ ({r.status_code}) შეცდომა! სერვერის პასუხი: {r.text}")
            
    except Exception as e:
        print(f"❌ მოთხოვნის შეცდომა: {e}")

def ws_thread():
    def on_message(ws, msg):
        pass
    while True:
        try:
            ws = websocket.WebSocketApp("wss://perps.permuto.capital/ws", on_message=on_message)
            ws.run_forever(ping_interval=25)
        except:
            pass
        time.sleep(5)

threading.Thread(target=ws_thread, daemon=True).start()

print("🌟 Permuto Cup Sage Bot ვერსია 5.6 ჩაირთო!")
time.sleep(2)

while True:
    update_grid()
    time.sleep(20)
