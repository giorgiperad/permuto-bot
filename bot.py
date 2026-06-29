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
USER_ID = None  # ავტომატურად შეივსება

def get_user_identity():
    """ ამოწმებს მიმდინარე სესიას და იღებს სავალდებულო user_id-ს """
    global USER_ID
    try:
        # ჯერ ვცადოთ /exchange/session ენდპოინტი
        r = requests.get(f"{BASE_URL}/exchange/session", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            USER_ID = data.get("user_id") or data.get("trading_user_id") or data.get("wallet_user_id")
            if USER_ID:
                print(f"✅ User ID ნაპოვნია სესიიდან: {USER_ID}")
                return USER_ID
        
        # ალტერნატივა: თუ სესიიდან ვერ აიღო, ვცადოთ account-იდან
        r = requests.post(f"{BASE_URL}/exchange/account", json={}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            USER_ID = data.get("user_id") or data.get("account", {}).get("user_id")
            if USER_ID:
                print(f"✅ User ID ნაპოვნია ექაუნთიდან: {USER_ID}")
                return USER_ID
    except Exception as e:
        print(f"⚠️ ვერ მოხერხდა User ID-ს იდენტიფიცირება: {e}")
    return None

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
    global USER_ID
    
    # თუ უზერ აიდი ჯერ არ გვაქვს, ვცადოთ მისი ხელახლა აღება
    if not USER_ID:
        USER_ID = get_user_identity()
        if not USER_ID:
            print("⏳ ❌ ორდერები ვერ იგზავნება, რადგან user_id ვერ მოიძებნა. ვცდით მომდევნო ციკლზე.")
            return

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
        if mid < 0.01:
            continue

        size = calculate_size(mid)
        spread = BASE_SPREAD

        if mid > 0.2:
            spread = BASE_SPREAD * 0.85

        bid = round(mid * (1 - spread), 5)
        ask = round(mid * (1 + spread), 5)

        # 🛑 კრიტიკული ცვლილება: ჩაშენებულია "user_id" თითოეულ ორდერში
        orders.append({
            "user_id": USER_ID,
            "market": market,
            "side": "buy",
            "type": "limit",
            "price": bid,
            "size": size,
            "reduce_only": False
        })
        orders.append({
            "user_id": USER_ID,
            "market": market,
            "side": "sell",
            "type": "limit",
            "price": ask,
            "size": size,
            "reduce_only": False
        })

    if not orders:
        return

    try:
        # ვაგზავნით გასწორებულ სტრუქტურას
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", json={"orders": orders}, headers=HEADERS, timeout=15)
        
        if r.status_code == 200:
            print(f"[{time.strftime('%H:%M:%S')}] ✅ Grid წარმატებით განახლდა | Exposure: {current_exposure:.1f}")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ ({r.status_code}) სერვერის პასუხი: {r.text}")
            
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

print("🌟 Permuto Cup Sage Bot ვერსია 5.7 ჩაირთო!")
# სტარტზევე ავიღოთ უზერ აიდი
get_user_identity()
time.sleep(2)

while True:
    update_grid()
    time.sleep(20)
