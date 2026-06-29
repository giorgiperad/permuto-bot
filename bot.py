import os
from blspy import AugSchemeMPL
from chia_crypto_utils import Mnemonic # ბიბლიოთეკა სიტყვების კონვერტაციისთვის

# ⚠️ უსაფრთხოებისთვის: Seed Phrase აუცილებლად ჩასვი Railway-ს Environment Variables-ში!
# არასოდეს ჩაწერო სიტყვები პირდაპირ კოდში.
SEED_PHRASE = os.getenv("WALLET_SEED_PHRASE") 

def get_keys_from_seed(seed_phrase: str):
    """24 სიტყვის გადაყვანა Chia-ს Private და Public გასაღებებში"""
    # 1. სიტყვების გადაყვანა ბაიტებში (Seed Bytes)
    mnemonic = Mnemonic(seed_phrase.split())
    seed_bytes = mnemonic.to_seed()
    
    # 2. Master Private Key-ს გენერაცია (BLS სტანდარტით)
    master_sk = AugSchemeMPL.key_gen(seed_bytes)
    
    # 3. Chia-ს წესით, პირველი მისამართის (First Wallet/Observer key) წარმოება (Derivation)
    # Permuto-ს სავარაუდოდ სჭირდება კონკრეტული ინდექსის გასაღები (მაგ. index 0)
    # შენიშვნა: დერივაციის ზუსტი პათი შეიძლება დაგჭირდეს Permuto-ს სექციის მიხედვით m/12381/8444/2/0
    wallet_sk = AugSchemeMPL.derive_path_unhardened(master_sk, [12381, 8444, 2, 0]) 
    wallet_pk = wallet_sk.get_g1_element()
    
    return wallet_sk, wallet_pk

# გამოყენების მაგალითი ბოტის შიგნით:
private_key, public_key = get_keys_from_seed(SEED_PHRASE)

# Permuto-სთვის გასაგზავნად Public Key უნდა გადავიყვანოთ Hex სტრინგში:
public_key_hex = bytes(public_key).hex()
print(f"შენი Public Key (Hex): {public_key_hex}")
