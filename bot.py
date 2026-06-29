import os
import sys
import time
import requests
import logging

# ლოგირების გამართვა, რომელიც მომენტალურად ბეჭდავს ტექსტს კონსოლში
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logging.info("--- ბოტი წარმატებით ჩაირთო და იწყებს მუშაობას ---")

try:
    from py_ecc.bls import G2ProofOfPossession as bls
    logging.info("py_ecc ბიბლიოთეკა წარმატებით ჩაიტვირთა.")
except ImportError as e:
    logging.critical(f"კრიტიკული შეცდომა ბიბლიოთეკის ჩატვირთვისას: {e}")
    sys.exit(1)

API_URL = "https://perps.permuto.capital"
MARKET = os.getenv("TRADING_MARKET", "QQQ-VOL-PERP")
HEX_SECRET_KEY = os.getenv("BLS_SECRET_KEY")

session_token = None
trading_user_id = None
last_auth_time = 0

def get_bls_public_key():
    """საიდუმლო გასაღებიდან საჯარო გასაღების (Hex) მიღება"""
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    pk = bls.SkToPk(sk)
    return pk.hex()

def sign_challenge_nonce(nonce_hex, pubkey_hex):
    """
    ხელს აწერს nonce-ს Chia AugSchemeMPL წესით:
    Sign = Sign(sk, DST + pk + message)
    """
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    
    # Chia-ს ოფიციალური AugSchemeMPL ფორმატი
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    msg_bytes = bytes.fromhex(nonce_hex)
    
    # ვაერთებთ ყველაფერს ერთად: DST + PK + MSG
    augmented_message = b"BLS_SIG_AUG___________" + pubkey_bytes + msg_bytes
    
    signature = bls.Sign(sk, augmented_message)
    return signature.hex()

def authenticate_bot():
    global session_token, trading_user_id, last_auth_time
    
    if not HEX_SECRET_KEY:
        logging.error("გარემოს ცვლადი 'BLS_SECRET_KEY' ვერ მოიძებნა Railway-ზე!")
        return False

    try:
        pubkey_hex = get_bls_public_key()
        logging.info(f"ავტორიზაციის მცდელობა საჯარო გასაღებით: {pubkey_hex[:15]}...")

        # ნაბიჯი 1: Challenge
        res1 = requests.post(f"{API_URL}/exchange/wallet_link_challenge", json={
            "wallet_pubkey": pubkey_hex,
            "wallet_curve": "bls12381",
            "wallet_signing_key_role": "master"
        })
        
        if res1.status_code != 200:
            logging.error(f"Challenge შეცდომა სერვერიდან: {res1.text}")
            return False
        
        challenge_data = res1.json()
        challenge_token = challenge_data["challenge_token"]
        nonce = challenge_data["nonce"]

        # ნაბიჯი 2: ხელმოწერა
        signature = sign_challenge_nonce(nonce, pubkey_hex)

        # ნაბიჯი 3: სესიის მიღება
        res2 = requests.post(f"{API_URL}/exchange/wallet_auth", json={
            "challenge_token": challenge_token,
            "signature": signature
        })
        
        if res2.status_code != 200:
            logging.error(f"Wallet Auth შეცდომა სერვერიდან: {res2.text}")
            return False
        
        auth_data = res2.json()
        session_token = auth_data["token"]
        trading_user_id = auth_data["trading_user_id"]
        last_auth_time = time.time()
        
        logging.info(f"ავტორიზაცია წარმატებულია! User ID: {trading_user_id}")
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

    # მარკეტ მეიქერის სატესტო ორდერები
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
    if not authenticate_bot():
        logging.critical("პირველადი ავტორიზაცია ვერ მოხერხდა. ბოტი ჩერდება.")
        return

    while True:
        current_time = time.time()
        # ყოველ 40 წუთში სესიის განახლება უსაფრთხოებისთვის
        if current_time - last_auth_time >= 2400:
            authenticate_bot()

        maintain_market_maker_orders()
        time.sleep(15)

if __name__ == "__main__":
    main()
