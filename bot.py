import requests
import time
import os

BASE_URL = "https://perps.permuto.capital"
TOKEN = "874361ccf9c38ba6df8d9834bf740f8206cdde90fa79bf12677e40a4e9b38813"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def get_meta():
    try:
        r = requests.get(f"{BASE_URL}/info/meta", timeout=10)
        return r.json()
    except:
        return None

def get_mids():
    try:
        r = requests.get(f"{BASE_URL}/info/mids", timeout=10)
        return r.json().get("mids", {})
    except:
        return {}

def get_account():
    try:
        r = requests.get(f"{BASE_URL}/exchange/account", headers=HEADERS, timeout=10)
        return r.json()
    except:
        return None

def update_grid():
    meta = get_meta()
    if not meta:
        return
    
    band_pct = meta.get("vol_oracle_band_pct", 50) / 100
    mids = get_mids()
    
    orders = []
    for market in ["QQQ-VOL-PERP", "NVDA-VOL-PERP", "TSLA-VOL-PERP"]:
        mid = float(mids.get(market, 0.15))
        if mid < 0.05:
            continue
            
        # დინამიური spread (უფრო ვიწრო ცენტრში)
        spread = 0.006 if mid > 0.1 else 0.009
        size = 35.0   # შეცვალე შენი რისკის მიხედვით (50-100)

        # Band-ის შემოწმება
        lower = mid * (1 - band_pct)
        upper = mid * (1 + band_pct)
        
        bid_price = max(lower, round(mid * (1 - spread), 4))
        ask_price = min(upper, round(mid * (1 + spread), 4))
        
        orders.append({"market": market, "side": "buy", "type": "limit", "price": str(bid_price), "size": str(size)})
        orders.append({"market": market, "side": "sell", "type": "limit", "price": str(ask_price), "size": str(size)})
    
    try:
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", 
                         json={"orders": orders}, 
                         headers=HEADERS, 
                         timeout=15)
        print(f"[{time.strftime('%H:%M:%S')}] Grid Updated | Status: {r.status_code} | Markets: 3")
    except Exception as e:
        print("Grid Error:", e)

print("🚀 საუკეთესო Permuto Market Maker Bot v2 დაწყებულია...")
print("Ctrl + C რომ გააჩერო")

while True:
    try:
        update_grid()
        time.sleep(22)   # ოპტიმალური ინტერვალი
    except KeyboardInterrupt:
        print("ბოტი გაჩერებულია.")
        break
    except Exception as e:
        print("General Error:", e)
        time.sleep(10)
