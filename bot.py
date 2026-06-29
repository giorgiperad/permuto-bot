import os
import time
import requests
import logging
from py_ecc.bls import G2Aug as bls

# ლოგირების გამართვა Railway კონსოლისთვის
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)

API_URL = "https://perps.permuto.capital"
MARKET = os.getenv("TRADING_MARKET", "QQQ-VOL-PERP")
HEX_SECRET_KEY = os.getenv("BLS_SECRET_KEY")

session_token = None
trading_user_id = None
last_auth_time = 0

def get_bls_public_key():
    """აგენერირებს 96-სიმბოლოიან საჯარო გასაღებს საიდუმლოდან"""
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    pk = bls.SkToPk(sk)
    return pk.hex()

def sign_challenge_nonce(nonce_hex):
    """
    ხელს აწერს nonce-ს ოფიციალური G2Aug (AugSchemeMPL) წესით.
    ეს ფუნქცია ავტომატურად ამატებს საჯარო გასაღებს შეტყობინების წინ და იყენებს სწორ Chia DST-ს.
    """
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    msg_bytes = bytes.fromhex(nonce_hex)
    
    signature = bls.Sign(sk, msg_bytes)
    return signature.hex()

def authenticate_bot():
    global session_token, trading_user_id, last_auth_time
    
    if not HEX_SECRET_KEY:
        logging.error("გარემოს ცვლადი 'BLS_SECRET_KEY' ვერ მოიძებნა Railway-ზე!")
        return False

    try:
        pubkey_hex = get_bls_public_key()
        logging.info(f"ავტორიზაციის მცდელობა საჯარო გასაღებით: {pubkey_hex[:15]}...")

        # ნაბიჯი 1: Challenge მოთხოვნა
        challenge_url = f"{API_URL}/exchange/wallet_link_challenge"
        payload = {
            "wallet_pubkey": pubkey_hex,
            "wallet_curve": "bls12381",
            "wallet_signing_key_role": "master"
        }
        
        res1 = requests.post(challenge_url, json=payload)
        if res1.status_code != 200:
            logging.error(f"Challenge შეცდომა სერვერიდან: {res1.text}")
            return False
            
        challenge_data = res1.json()
        challenge_token = challenge_data["challenge_token"]
        nonce = challenge_data["nonce"]

        # ნაბიჯი 2: ხელმოწერა G2Aug სქემით
        signature = sign_challenge_nonce(nonce)

        # ნაბიჯი 3: სესიის ავტორიზაცია
        auth_url = f"{API_URL}/exchange/wallet_auth"
        auth_payload = {
            "challenge_token": challenge_token,
            "signature": signature
        }
        
        res2 = requests.post(auth_url, json=auth_payload)
        if res2.status_code != 200:
            logging.error(f"Wallet Auth შეცდომა სერვერიდან: {res2.text}")
            return False
            
        auth_data = res2.json()
        session_token = auth_data["token"]
        trading_user_id = auth_data["trading_user_id"]
        last_auth_time = time.time()
        
        logging.info(f"სერვერმა მიიღო ხელმოწერა! User ID: {trading_user_id}")
        return True

    except Exception as e:
        logging.error(f"კრიტიკული შეცდომა ავტორიზაციისას: {e}")
        return False

def maintain_market_maker_orders():
    global session_token
    if not session_token:
        return

    url = f"{API_URL}/exchange/batch_upsert"
    headers = {
        "Authorization": f"Bearer {session_token}",
        "Content-Type": "application/json"
    }

    # სატესტო ორდერები
    payload = {
        "user_id": trading_user_id,
        "orders": [
            {
                "market": MARKET,
                "side": "buy",
                "price": "0.1800",
                "size": "1.0",
                "tif": "gtc"
            },
            {
                "market": MARKET,
                "side": "sell",
                "price": "0.2200",
                "size": "1.0",
                "tif": "gtc"
            }
        ]
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            logging.info(f"ორდერები წარმატებით გაიგზავნა {MARKET}-ზე.")
        elif response.status_code == 401:
            logging.warning("სესიას ვადა გაუვიდა, ხელახალი ავტორიზაცია...")
            if authenticate_bot():
                headers["Authorization"] = f"Bearer {session_token}"
                requests.post(url, json=payload, headers=headers)
        else:
            logging.error(f"ორდერები არ დაიდო: {response.text}")
    except Exception as e:
        logging.error(f"კავშირის შეცდომა ორდერის გაგზავნისას: {e}")

def main():
    logging.info("სერვერის ბოტი ჩაირთო.")
    if not authenticate_bot():
        return

    while True:
        current_time = time.time()
        if current_time - last_auth_time >= 2400:
            authenticate_bot()

        maintain_market_maker_orders()
        time.sleep(15)

if __name__ == "__main__":
    main()
