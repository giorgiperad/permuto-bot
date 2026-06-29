import os
import time
import requests
import logging

# ლოგირების გამართვა Railway-ის კონსოლისთვის
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)

# კონფიგურაცია
API_URL = "https://perps.permuto.capital"
API_KEY = os.getenv("PERPS_API_KEY")  # უნდა იწყებოდეს perps_agent_-ით
MARKET = os.getenv("TRADING_MARKET", "QQQ-VOL-PERP")  # სასურველი მარკეტი კონკურსისთვის

# გლობალური ცვლადები სესიის მენეჯმენტისთვის
session_token = None
trading_user_id = None
last_renew_time = 0

def renew_agent_session():
    """
    ახორციელებს ავტორიზაციას API Key-ს გამოყენებით და იღებს სესიის ტოკენს.
    სესიის ხანგრძლივობაა 8 საათი, მაგრამ რეკომენდებულია განახლება 40 წუთში ერთხელ.
    """
    global session_token, trading_user_id, last_renew_time
    
    if not API_KEY:
        logging.error("გარემოს ცვლადი 'PERPS_API_KEY' ვერ მოიძებნა! გთხოვთ დაამატოთ ის Railway-ზე.")
        return False

    logging.info("სესიის ტოკენის მოთხოვნა პლატფორმიდან...")
    url = f"{API_URL}/exchange/agent_session"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            session_token = data.get("token")
            trading_user_id = data.get("trading_user_id")
            last_renew_time = time.time()
            logging.info(f"ავტორიზაცია წარმატებულია. User ID: {trading_user_id}")
            return True
        else:
            logging.error(f"ავტორიზაციის შეცდომა (სტატუსი: {response.status_code}): {response.text}")
            return False
    except Exception as e:
        logging.error(f"კავშირის შეცდომა ავტორიზაციის მცდელობისას: {e}")
        return False

def place_market_maker_quotes():
    """
    აგზავნის ორმხრივ ორდერებს (Bid და Ask).
    იყენებს batch_upsert-ს, რაც უზრუნველყოფს ძველი ორდერების ჩანაცვლებას/განახლებას.
    """
    global session_token
    if not session_token:
        logging.warning("სესიის ტოკენი არ არსებობს, ორდერების გაგზავნა შეუძლებელია.")
        return

    url = f"{API_URL}/exchange/batch_upsert"
    headers = {
        "Authorization": f"Bearer {session_token}",
        "Content-Type": "application/json"
    }

    # სტრატეგიის მარტივი მაგალითი (ფასები უნდა შეცვალო ბაზრის მიხედვით)
    # აქ ვსვამთ ყიდვის ორდერს 0.18-ზე და გაყიდვის ორდერს 0.22-ზე
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
            logging.warning("მიღებულია 401 შეცდომა (Invalid session). სასწრაფოდ ვანახლებთ სესიას...")
            if renew_agent_session():
                # ხელახლა ვცდილობთ ორდერის გაგზავნას ახალი ტოკენით
                headers["Authorization"] = f"Bearer {session_token}"
                requests.post(url, json=payload, headers=headers)
        else:
            logging.error(f"ორდერების განთავსება ჩაიშალა (სტატუსი: {response.status_code}): {response.text}")
    except Exception as e:
        logging.error(f"შეცდომა API-სთან კავშირისას: {e}")

def main():
    logging.info("ბოტი წარმატებით ჩაირთო. იწყება საწყისი ავტორიზაცია...")
    
    # პირველი ავტორიზაცია ჩართვისას
    if not renew_agent_session():
        logging.critical("საწყისი ავტორიზაცია ვერ მოხერხდა. ბოტი მუშაობას წყვეტს.")
        return

    while True:
        current_time = time.time()

        # სესიის განახლება ყოველ 40 წუთში (2400 წამი) უსაფრთხოებისთვის
        if current_time - last_renew_time >= 2400:
            logging.info("გავიდა 40 წუთი. ავტომატურად ვანახლებთ სესიის ტოკენს...")
            renew_agent_session()

        # ორდერების მართვა
        place_market_maker_quotes()

        # ბოტის ბიჯი (ინტერვალი) - ამოწმებს და ანახლებს ორდერებს ყოველ 15 წამში
        time.sleep(15)

if __name__ == "__main__":
    main()
