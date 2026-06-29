import requests
import time
import json
import websocket
import threading

BASE_URL = "https://perps.permuto.capital"
# ⚠️ ჩასვი შენი ოფიციალური API Key, რომელიც Cloud Wallet-ის "Bot API keys" მენიუდან აიღე
API_KEY = "874361ccf9c38ba6df8d9834bf740f8206cdde90fa79bf12677e40a4e9b38813"

BASE_SPREAD = 0.007
MAX_TOTAL_EXPOSURE = 400.0  # მაქსიმალური ნებადართული პოზიცია

session_token = None
headers = {}
lock = threading.Lock()

def refresh_session_loop():
    """ 
    ავტორიზაციის ციკლი: იღებს დროებით სესიას და ანახლებს ყოველ 30 წუთში, 
    რათა თავიდან ავიცილოთ 40 წუთიანი ლიმიტის ამოწურვა და 401 შეცდომა.
    """
    global session_token, headers
    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] 🔄 სესიის განახლება...")
            # დოკუმენტაციის თანახმად: ბოტი აკეთებს POST-ს /exchange/agent_session-ზე Bearer API_KEY-ით
            r = requests.post(
                f"{BASE_URL}/exchange/agent_session",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                timeout=10
            )
            
            if r.status_code == 200:
                res_data = r.json()
                # ამოწმებს სხვადასხვა შესაძლო ქეისს, თუ რა ფორმატით აბრუნებს API ტოკენს
                token = res_data.get("session_token") or res_data.get("token") or res_data.get("agent_session")
                
                if token:
                    with lock:
                        session_token = token
                        headers = {
                            "Authorization": f"Bearer {session_token}",
                            "Content-Type": "application/json"
                        }
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ სესია წარმატებით გააქტიურდა!")
                else:
                    print(f"❌ შეცდომა: სესიის ტოკენი ვერ მოიძებნა JSON სტრუქტურაში: {res_data}")
            else:
                print(f"❌ ავტორიზაცია ჩავარდა სტატუსით: {r.status_code} - {r.text}")
                
        except Exception as e:
            print(f"❌ Auth Exception: {e}")
            
        # 30 წუთიანი ძილი (1800 წამი) - 40 წუთზე გაცილებით უსაფრთხოა
        time.sleep(1800)

def get_mids():
    try:
        r = requests.get(f"{BASE_URL}/info/mids", timeout=10)
        return r.json().get("mids", {})
    except:
        return {}

def get_account_exposure():
    """ ითვლის მიმდინარე პოზიციების ჯამს რისკების კონტროლისთვის """
    with lock:
        if not headers: return 0.0
        local_headers = headers.copy()
        
    try:
        r = requests.get(f"{BASE_URL}/exchange/account", headers=local_headers, timeout=10)
        if r.status_code == 200:
            account_data = r.json()
            positions = account_data.get("positions", [])
            total_exposure = 0.0
            for pos in positions:
                # აჯამებს ყველა მიმდინარე პოზიციის აბსოლუტურ ზომას
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
    with lock:
        if not headers:
            print("⏳ ველოდებით პირველად ავტორიზაციას...")
            return
        local_headers = headers.copy()

    # უსაფრთხოების ფილტრი: თუ ექსპოზიციამ ლიმიტს გადააჭარბა, ახალ ორდერებს აღარ დებს
    current_exposure = get_account_exposure()
    if current_exposure >= MAX_TOTAL_EXPOSURE:
        print(f"⚠️ ექსპოზიციის ლიმიტი შევსებულია ({current_exposure}/{MAX_TOTAL_EXPOSURE}). ახალი ორდერები დაიბლოკა.")
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

        # დინამიური სპრედი მაღალი ვოლატილობისას
        if mid > 0.2:
            spread = BASE_SPREAD * 0.85

        bid = round(mid * (1 - spread), 4)
        ask = round(mid * (1 + spread), 4)

        orders.append({"market": market, "side": "buy", "type": "limit", "price": str(bid), "size": str(size)})
        orders.append({"market": market, "side": "sell", "type": "limit", "price": str(ask), "size": str(size)})

    if not orders:
        return

    try:
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", json={"orders": orders}, headers=local_headers, timeout=15)
        
        if r.status_code == 401:
            print("🚨 სესია ვადაგასულია (401 Error)! ველოდებით მომდევნო რეფრეშს...")
            return
            
        status = "✅" if r.status_code == 200 else f"❌ ({r.status_code})"
        print(f"[{time.strftime('%H:%M:%S')}] {status} Grid განახლდა | Exposure: {current_exposure:.1f}/{MAX_TOTAL_EXPOSURE}")
    except Exception as e:
        print(f"❌ Grid-ის გაგზავნა ჩავარდა: {e}")

def ws_thread():
    """ ცალკე თრედი სტაბილური ვებზოკეტისთვის ავტო-რეკონექტით """
    def on_message(ws, msg):
        try:
            data = json.loads(msg)
            print("WS Live Channel:", data.get("channel", "unknown"))
        except:
            pass

    while True:
        try:
            ws = websocket.WebSocketApp("wss://perps.permuto.capital/ws", on_message=on_message)
            ws.run_forever(ping_interval=25)
        except:
            pass
        time.sleep(5)  # დაცდა რეკონექტამდე

# თრედების გაშვება
threading.Thread(target=refresh_session_loop, daemon=True).start()
threading.Thread(target=ws_thread, daemon=True).start()

print("🌟 Permuto Volatility Cup Bot v5.0 წარმატებით ჩაირთო!")
time.sleep(4)  # მცირე პაუზა, რომ ავტორიზაცია დასრულდეს

while True:
    update_grid()
    time.sleep(20)
