import os
import time
import requests
import logging
from py_ecc.bls import G2ProofOfPossession as bls

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')

API_URL = "https://perps.permuto.capital"
MARKET = os.getenv("TRADING_MARKET", "QQQ-VOL-PERP")
HEX_SECRET_KEY = os.getenv("BLS_SECRET_KEY")

session_token = None
trading_user_id = None
last_auth_time = 0

def get_bls_public_key():
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    pk = bls.SkToPk(sk)
    return pk.hex()

def sign_challenge_nonce(nonce_hex, pubkey_hex):
    sk_bytes = bytes.fromhex(HEX_SECRET_KEY)
    sk = int.from_bytes(sk_bytes, "big")
    
    # Chia AugSchemeMPL: ხელმოწერისას გასაღებს და შეტყობინებას ვაერთებთ
    # და ვიყენებთ Sign ფუნქციას მხოლოდ 2 არგუმენტით
    augmented_message = bytes.fromhex(pubkey_hex) + bytes.fromhex(nonce_hex)
    signature = bls.Sign(sk, augmented_message) 
    return signature.hex()

def authenticate_bot():
    global session_token, trading_user_id, last_auth_time
    try:
        pubkey_hex = get_bls_public_key()
        res1 = requests.post(f"{API_URL}/exchange/wallet_link_challenge", json={
            "wallet_pubkey": pubkey_hex,
            "wallet_curve": "bls12381",
            "wallet_signing_key_role": "master"
        })
        if res1.status_code != 200: return False
        
        data = res1.json()
        signature = sign_challenge_nonce(data["nonce"], pubkey_hex)
        
        res2 = requests.post(f"{API_URL}/exchange/wallet_auth", json={
            "challenge_token": data["challenge_token"],
            "signature": signature
        })
        if res2.status_code != 200: return False
        
        auth_data = res2.json()
        session_token = auth_data["token"]
        trading_user_id = auth_data["trading_user_id"]
        last_auth_time = time.time()
        logging.info(f"ავტორიზაცია წარმატებულია. User ID: {trading_user_id}")
        return True
    except Exception as e:
        logging.error(f"ავტორიზაციის შეცდომა: {e}")
        return False

def maintain_market_maker_orders():
    if not session_token: return
    headers = {"Authorization": f"Bearer {session_token}", "Content-Type": "application/json"}
    payload = {
        "user_id": trading_user_id,
        "orders": [
            {"market": MARKET, "side": "buy", "price": "0.1800", "size": "1.0", "tif": "gtc"},
            {"market": MARKET, "side": "sell", "price": "0.2200", "size": "1.0", "tif": "gtc"}
        ]
    }
    requests.post(f"{API_URL}/exchange/batch_upsert", json=payload, headers=headers)

def main():
    if authenticate_bot():
        while True:
            maintain_market_maker_orders()
            time.sleep(15)

if __name__ == "__main__":
    main()
