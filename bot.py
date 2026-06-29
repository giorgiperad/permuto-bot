import asyncio
import json
import os
from blspy import AugSchemeMPL, PrivateKey
from mnemonic import Mnemonic
import httpx
import websockets

# კონფიგურაცია გარემოს ცვლადებიდან (Railway Variables)
BASE_URL = "https://perps.permuto.capital"
WS_URL = "wss://perps.permuto.capital/ws"  # გადაამოწმე ზუსტი მისამართი openapi.json-ში
SEED_PHRASE = os.getenv("WALLET_SEED_PHRASE")

class PermutoMMBot:
    def __init__(self):
        self.session_token = None
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
        self.wallet_sk = None
        self.wallet_pk_hex = None

    def derive_keys_from_seed(self):
        """24 სიტყვის კონვერტაცია Chia BLS გასაღებებში"""
        if not SEED_PHRASE:
            raise ValueError("🛑 შეცდომა: WALLET_SEED_PHRASE არ არის მითითებული სეთინგებში!")
        
        print("🔑 გასაღებების გენერირება Seed Phrase-დან...")
        # 1. სიტყვების გადაყვანა ბაიტებში
        mnemo = Mnemonic("english")
        seed_bytes = mnemo.to_seed(SEED_PHRASE, passphrase="")
        
        # 2. Master Private Key-ს შექმნა (Chia იყენებს BLS12-381-ს)
        master_sk = AugSchemeMPL.key_gen(seed_bytes)
        
        # 3. Chia Wallet-ის სტანდარტული მისამართის წარმოება (Path: m/12381/8444/2/0)
        # ეს ემთხვევა Sage/Chia საფულეების პირველ ძირითად მისამართს
        self.wallet_sk = AugSchemeMPL.derive_path_unhardened(master_sk, [12381, 8444, 2, 0])
        self.wallet_pk_hex = bytes(self.wallet_sk.get_g1_element()).hex()
        
        print(f"✅ საჯარო გასაღები (Public Key) ნაპოვნია: {self.wallet_pk_hex}")

    async def authenticate(self):
        """Market Maker Auth ლოგიკა: Challenge -> Sign -> Auth"""
        print("🔐 ავტორიზაციის პროცესი იწყება...")
        
        # 1. ითხოვე Challenge პლატფორმისგან
        # (ენდპოინტები ეფუძნება Permuto-ს დოკუმენტაციას, გადაამოწმე openapi.json)
        challenge_payload = {"public_key": self.wallet_pk_hex}
        res = await self.client.post("/exchange/wallet_link_challenge", json=challenge_payload)
        
        if res.status_code != 200:
            print(f"🛑 Challenge-ის მოთხოვნა ჩავარდა: {res.text}")
            return False
            
        challenge_data = res.json()
        challenge_bytes = bytes.fromhex(challenge_data["challenge"])

        # 2. ხელმოწერა (Unattended Sage bot - Raw nonce bytes signing)
        signature = AugSchemeMPL.sign(self.wallet_sk, challenge_bytes)
        signature_hex = bytes(signature).hex()

        # 3. სესიის ავტორიზაცია ტოკენის მისაღებად
        auth_payload = {
            "public_key": self.wallet_pk_hex,
            "challenge": challenge_data["challenge"],
            "signature": signature_hex
        }
        auth_res = await self.client.post("/exchange/wallet_auth", json=auth_payload)
        
        if auth_res.status_code != 200:
            print(f"🛑 ავტორიზაცია ჩავარდა: {auth_res.text}")
            return False
            
        self.session_token = auth_res.json().get("session_token")
        print("🎉 ავტორიზაცია წარმატებულია! სესიის ტოკენი მიღებულია.")
        return True

    async def watch_market_and_trade(self):
        """WebSocket კავშირი და მარკეტ მეიქერის ძირითადი ციკლი"""
        headers = {"Authorization": f"Bearer {self.session_token}"}
        
        async with websockets.connect(WS_URL, extra_headers=headers) as ws:
            print("📈 WebSocket კავშირი დამყარდა. იწყება მონაცემების მიღება...")
            
            # მაგალითი: ბაზრის ორდერბუქის გამოწერა (შეცვალე Permuto-ს წესის მიხედვით)
            subscribe_msg = {
                "action": "subscribe",
                "channels": ["orderbook"],
                "market": "BTC-PERP" 
            }
            await ws.send(json.dumps(subscribe_msg))

            async for message in ws:
                data = json.loads(message)
                await self.market_making_strategy(data)

    async def market_making_strategy(self, data):
        """აქ იწერება შენი სტრატეგიის მათემატიკა"""
        # ეს ფუნქცია ტრიალებს ყოველ ჯერზე, როცა ბაზარზე ფასი იცვლება
        print(f"⚡ ბაზრის ახალი მონაცემი: {data}")
        
        # მაგალითი: თუ ორდერის დასმა გინდა (REST API-ით):
        # order_payload = {"market": "BTC-PERP", "side": "buy", "price": 60000, "size": 0.1}
        # headers = {"Authorization": f"Bearer {self.session_token}"}
        # await self.client.post("/exchange/orders", json=order_payload, headers=headers)
        pass

    async def start(self):
        # 1. გასაღებების მომზადება
        self.derive_keys_from_seed()
        # 2. ავტორიზაცია
        if await self.authenticate():
            # 3. მუშაობის დაწყება
            await self.watch_market_and_trade()

if __name__ == "__main__":
    bot = PermutoMMBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("🛑 ბოტი გამორთულია მომხმარებლის მიერ.")
