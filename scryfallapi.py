from bs4 import BeautifulSoup
import requests

SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"
finded_card = "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger"


def find_scryfall_card_data(card_name: str):
    response = requests.request(
        "GET",
        SCRYFALL_SEARCH_URL,
        params={
            "q": card_name,
            "pretty": True,
            "include_multilingual": True,
            "unique": "prints",
        },
    )
    data = response.json().get("data")
    card_info = {"prices": {}, "local_name": None}
    if data:
        for card_data in data:
            if card_data.get("lang") and card_data.get("lang") == "en":
                card_info["prices"][card_data.get("set")] = {"TCGplayer": {}, "Cardmarket": {}}
                card_price = card_data.get("prices")
                for currency_n_type, price in card_price.items():
                    
                    if currency_n_type.startswith("usd"):
                        card_info["prices"][card_data.get("set")]["TCGplayer"][currency_n_type] = price
                    elif currency_n_type.startswith("eur"):
                        card_info["prices"][card_data.get("set")]["Cardmarket"][currency_n_type] = price
                        
            if card_data.get("lang") and card_data.get("lang") == "ru":
                card_info["local_name"] = card_data.get("printed_name")
    return card_info



if __name__ == "__main__":
    print(find_scryfall_card_data(finded_card))
