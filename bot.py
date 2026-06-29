import requests
import time

BASE_URL = "https://perps.permuto.capital"
TOKEN = "874361ccf9c38ba6df8d9834bf740f8206cdde90fa79bf12677e40a4e9b38813"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def update_grid():
    try:
        mids = requests.get(f"{BASE_URL}/info/mids").json().get("mids", {})
        
        orders = []
        for market in ["QQQ-VOL-PERP", "NVDA-VOL-PERP", "TSLA-VOL-PERP"]:
            mid = float(mids.get(market, 0.15))
            if mid < 0.05:
                continue
            spread = 0.008
            size = 40.0
            
            orders.append({"market": market, "side": "buy", "type": "limit", "price": str(round(mid * (1 - spread), 4)), "size": str(size)})
            orders.append({"market": market, "side": "sell", "type": "limit", "price": str(round(mid * (1 + spread), 4)), "size": str(size)})
        
        r = requests.post(f"{BASE_URL}/exchange/batch_upsert", json={"orders": orders}, headers=HEADERS)
        print(f"[{time.strftime('%H:%M:%S')}] Grid updated - Status: {r.status_code}")
    except Exception as e:
        print("Error:", e)

print("ბოტი მუშაობს... (Ctrl + C რომ გააჩერო)")
while True:
    update_grid()
    time.sleep(25)