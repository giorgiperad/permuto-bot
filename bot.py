import os
import time
import requests
import logging
from py_ecc.bls import G2ProofOfPossession as bls

# ლოგირების გამართვა Railway კონსოლისთვის
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)

API_URL = "https://perps.permuto.capital"
MARKET = os.getenv("TRADING_MARKET", "QQQ-VOL-PERP")

# 1. ლოკალური BLS გასაღების წაკითხვა Railway-დან
# გასაღები უნდა იყოს 32-ბაიტიანი (64 სიმბოლოიანი hex სტრინგი)
HEX_SECRET_KEY = os.getenv("4c617465737443686961424c534b65795365637265744b657931323334353637")

# სესიის გლობალური ცვლადები
session_token = None
trading_user_id = None
last_auth_time = 0

def get_bls_public_key():
    """აგენერირებს 96-ბაიტიან (192 სიმბოლო hex) საჯარო გასაღებს საიდუმლოდან"""
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    pk = bls.SkToPk(sk)
    return pk.hex()

def sign_challenge_nonce(nonce_hex):
    """ხელს აწერს სერვერიდან მიღებულ nonce-ს Chia-ს სტანდარტის (AugSchemeMPL) მიხედვით"""
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    msg_bytes = bytes.fromhex(nonce_hex)
    
    # Chia-ს სპეციფიკაციით, ხელმოწერისთვის გამოიყენება ცარიელი (empty) DST ბაიტები
    signature = bls.Sign(sk, msg_bytes)
    return signature.hex()

def authenticate_bot():
    """მარკეტ მეიქერის ავტორიზაციის სრული ციკლი"""
    global session_token, trading_user_id, last_auth_time
    
    if not HEX_SECRET_KEY:
        logging.error("გარემოს ცვლადი 'BLS_SECRET_KEY' ვერ მოიძებნა! დაამატე ის Railway-ზე.")
        return False

    try:
        pubkey = get_bls_public_key()
        logging.info(f"ავტორიზაციის დაწყება საჯარო გასაღებით: {pubkey[:10]}...")

        # ნაბიჯი 1: Challenge მოთხოვნა
        challenge_url = f"{API_URL}/exchange/wallet_link_challenge"
        payload = {
            "wallet_pubkey": pubkey,
            "wallet_curve": "bls12381",
            "wallet_signing_key_role": "master"
        }
        
        res1 = requests.post(challenge_url, json=payload)
        if res1.status_code != 200:
            logging.error(f"Challenge შეცდომა: {res1.text}")
            return False
            
        challenge_data = res1.json()
        challenge_token = challenge_data["challenge_token"]
        nonce = challenge_data["nonce"]

        # ნაბიჯი 2: ლოკალური ხელმოწერა
        signature = sign_challenge_nonce(nonce)

        # ნაბიჯი 3: სესიის მიღება (Wallet Auth)
        auth_url = f"{API_URL}/exchange/wallet_auth"
        auth_payload = {
            "challenge_token": challenge_token,
            "signature": signature
        }
        
        res2 = requests.post(auth_url, json=auth_payload)
        if res2.status_code != 200:
            logging.error(f"Wallet Auth შეცდომა: {res2.text}")
            return False
            
        auth_data = res2.json()
        session_token = auth_data["token"]
        trading_user_id = auth_data["trading_user_id"]
        last_auth_time = time.time()
        
        logging.info(f"ავტორიზაცია წარმატებულია! Trading User ID: {trading_user_id}")
        return True

    except Exception as e:
        logging.error(f"შეცდომა ავტორიზაციის პროცესში: {e}")
        return False

def maintain_market_maker_orders():
    """ორმხრივი ორდერების განთავსება / განახლება"""
    global session_token
    if not session_token:
        return

    url = f"{API_URL}/exchange/batch_upsert"
    headers = {
        "Authorization": f"Bearer {session_token}",
        "Content-Type": "application/json"
    }

    # მარკეტ მეიქერის საილუსტრაციო ბადი (Grid)
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
            logging.info(f"მარკეტ მეიქერის ორდერები წარმატებით განახლდა {MARKET}-ზე.")
        elif response.status_code == 401:
            logging.warning("სესიას ვადა გაუვიდა (401). ხელახალი ავტორიზაცია...")
            if authenticate_bot():
                # ხელახლა ვცდილობთ ახალი ტოკენით
                headers["Authorization"] = f"Bearer {session_token}"
                requests.post(url, json=payload, headers=headers)
        else:
            logging.error(f"ორდერების განთავსება ჩაიშალა: {response.text}")
    except Exception as e:
        logging.error(f"შეცდომა ორდერების გაგზავნისას: {e}")

def main():
    logging.info("ბოტი ჩაირთო. იწყება პირველადი BLS ავტორიზაცია...")
    
    if not authenticate_bot():
        logging.critical("პირველადი ავტორიზაცია ვერ მოხერხდა. ბოტი მუშაობას წყვეტს.")
        return

    while True:
        current_time = time.time()

        # სესიის განახლების ციკლი ყოველ 40 წუთში (2400 წამში)
        if current_time - last_auth_time >= 2400:
            logging.info("გავიდა 40 წუთი. ავტომატურად ვანახლებთ სესიას...")
            authenticate_bot()

        # ორდერების მართვა
        maintain_market_maker_orders()

        # ინტერვალი მომდევნო შემოწმებამდე (15 წამი)
        time.sleep(15)

if __name__ == "__main__":
    main()
