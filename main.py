import json
from typing import Optional
from requests import Response, request
from bs4 import BeautifulSoup, Tag
from scryfallapi import find_scryfall_card_data
import re
import os
import csv
from dotenv import load_dotenv
from itertools import zip_longest

CARD_PRICERE_EXPRESSION = r"(?<![\d,])\b\d+\b(?![\d,])"
CARD_SELLER_DATA_RE_EXPRESSION = r'JSON\.parse\("([^"]+|\\")*"\)'


def find_colletion_file(search_path: str) -> str | None:
    for root, dirs, files in os.walk(search_path):
        for file in files:
            if file.endswith(".csv"):
                return os.path.join(root, file)
    return None


def get_data_from_collection(collection_file_path: str) -> dict[str:dict]:
    collection = {}
    with open(collection_file_path, newline="") as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=";")
        headers = next(csv_reader)
        if "Price" in headers[0]:
            for card_data in csv_reader:
                card_name, card_local_name, card_prices = card_data
                collection[card_name] = {
                    "local_name": card_local_name,
                    "price": json.loads(
                        card_prices.replace("'", '"').replace("None", "null")
                    ),
                }
        else:
            for card_name in csv_reader:
                card_name = "".join(card_name)
                collection[card_name] = find_scryfall_card_data(card_name)
            update_collection_file(collection_file_path, collection)
    return collection


def update_collection_file(collection_file_path: str, collection_data: dict) -> None:
    with open(collection_file_path, mode="w", newline="\n") as csv_file:
        csv_writer = csv.writer(csv_file, delimiter=";")
        csv_writer.writerow(["Name|Local_name|Price"])
        for key, value in collection_data.items():
            csv_writer.writerow(
                [key, value["local_name"] or "no_local_name", value["prices"]]
            )


def get_card_info(card_line):
    card_block_values = []
    card_desc = ""
    for sibling in card_line.next_siblings:
        if sibling.name == "br":
            break
        card_block_values.append(sibling.text)
    else:

        if list(card_line.next_siblings):
            if not re.search(CARD_PRICERE_EXPRESSION, "".join(card_block_values)):
                parent = sibling.parent
                if parent.next_sibling:
                    while not parent.next_sibling.name:

                        card_block_values.append(parent.next_sibling.text)
                        parent = parent.next_sibling
                        if not parent.next_sibling:
                            break

                    else:
                        parent: Tag = parent.next_sibling
                        for child in parent.children:
                            if (
                                child.name == "br"
                                or child.name == "a"
                                or re.search(
                                    CARD_PRICERE_EXPRESSION, "".join(card_block_values)
                                )
                            ):
                                break
                            card_block_values.append(child.text)

    card_desc = "".join(card_block_values)
    card_desc = card_desc.replace("\xa0", "").replace("\n", "")
    price_match = re.search(CARD_PRICERE_EXPRESSION, card_desc)
    try:
        card_price = int(price_match.group())
    except AttributeError:
        card_price = 0
    return {"card_desc": card_desc, "tradepost_card_price": card_price}


def get_cards_from_tradepost(
    trade_post_url: str,
) -> dict[dict[str:str, str:int, str:dict]] | None:
    cards = {}
    response: Response = request("get", trade_post_url)
    page = response.text
    bs4page = BeautifulSoup(page, features="html.parser")

    trade_post = bs4page.find_all("a", {"class": "topdeck_tooltipCard"})
    for card_line in trade_post:
        card_name = card_line.text.strip()
        new_card_info = get_card_info(card_line)

        if not card_line.text in cards:
            cards.update({card_name: new_card_info})
        else:

            if not cards[card_name].get("another_offers_from_tp", []):
                cards[card_name]["another_offers_from_tp"] = []
            cards[card_name]["another_offers_from_tp"].append(new_card_info)
    return cards


def find_card_topdeck_price(card_name: str, card_name_local: Optional[str]) -> list[dict[str:str, str:int, str:int]]:
    price_list = []
    response = request("GET", os.environ.get("TOP_DECK_SEARCH_URL"), params={"q": card_name})
    bs4page = BeautifulSoup(response.text, features="html.parser")
    for el in bs4page.find_all("script"):
        if "SinglesSearchVM" in el.next_element:
            finded_str = str(
                re.search(CARD_SELLER_DATA_RE_EXPRESSION, el.text).group(1)
            )
            decoded_string = bytes(finded_str, "utf-8").decode("unicode_escape")
            result = json.loads(decoded_string)
            for trade in result:
                if card_name == trade["name"] or trade["name"] == card_name_local:
                    price_list.append(
                        {
                            "seller": trade["seller"],
                            "cost": trade["cost"],
                            "qty": trade["qty"],
                        }
                    )
            break
    return price_list


def filter_cards_from_tradepost(
    collection_list: list[str], cards_from_trade_post: dict[dict[str:str, str:int]]
) -> list:
    finded_card_in_tradepost = {}
    for card_name in collection_list:
        needed_card = cards_from_trade_post.get(card_name, None)
        if needed_card:
            finded_card_in_tradepost[card_name] = needed_card
    return finded_card_in_tradepost

def update_collection_data_with_tp_data(collection_data:dict, cards_from_trade_post:dict) -> dict:
    updated_card_data = {}
    for card_name, card_data in collection_data.items():
        new_card_data:dict = cards_from_trade_post.get(card_name) or {}
        if new_card_data:
            new_card_data.update(card_data)
            

        new_card_data_by_locals = cards_from_trade_post.get(card_data.get('local_name'))
        if new_card_data_by_locals:
            if new_card_data:
                if not new_card_data.get("another_offers_from_tp", []):
                    new_card_data["another_offers_from_tp"] = []
                new_card_data["another_offers_from_tp"].append(new_card_data_by_locals)
            else:
                new_card_data.update(card_data)
                new_card_data.update(new_card_data_by_locals)
        if new_card_data:
            updated_card_data[card_name] = new_card_data
    return updated_card_data

def update_collection_dta_with_topdeck_price(data:dict) -> dict:
    for card_name, card_data in data.items():
    
        price_list = find_card_topdeck_price(card_name, card_data.get("local_name"))
        data[card_name].update({"top_deck_price": price_list})
    return data

def print_to_terminal(data: dict):
    
    for card_name, card_data in data.items():
        print()
        print()
        print("CARD:", card_name)
        print("-"*(len(card_name)+5))
        print(
            "\tDescription:",
            re.sub(r" +", "  ", card_data["card_desc"].strip()),
            "\n\tPrice:",
            card_data["tradepost_card_price"],
        )
        if card_data.get("another_offers", []):
            print("\tAnother offers from this trader: ")
            for el in card_data.get("another_offers", []):
                print(
                    "\t\t",
                    "Description: ",
                    re.sub(r" +", "  ", el["card_desc"].strip()),
                    "\n\t\t",
                    "Price: ",
                    el["tradepost_card_price"],
                )
                print(f"\t\t{(30*"-")}")
        tp_price_list = card_data.get("top_deck_price", [])
        if len(tp_price_list) > 1:
            print("\tAnother offers from Topdeck:")
            print("\t\t%-*s%-*s%-*s" % (20, "Name", 10, "Price", 10, "Qty"))
            print(f"\t\t{(40*"-")}")
            for trade_variant in tp_price_list[: min(5, len(tp_price_list))]:
                print(
                    "\t\t%-*s%-*d%-*d"
                    % (
                        20,
                        (
                            trade_variant["seller"]["name"]
                            if isinstance(trade_variant["seller"], dict)
                            else trade_variant["seller"]
                        ),
                        10,
                        trade_variant["cost"],
                        10,
                        trade_variant["qty"],
                    )
                )
        print()
        print("\tWestern market price")
        print("\t--------------------")
        western_markets_price =card_data.get("price", {})
        for set_name, price_data in western_markets_price.items():
            markets_name = list(price_data)
            print("\t\t%-*s%-*s%-*s" % (10, set_name, 35, markets_name[0], 35, markets_name[1]))
            print("\t\t----")

            for print_type, price in zip(zip_longest(*price_data.values()), zip_longest(*[el.values() for el in price_data.values()])):
                print("\t\t%-*s%-*s%-*s%-*s%-*s" % (10, " ", 20, print_type[0] or "None", 15, price[0] or "-" if print_type[0] else "", 20, print_type[1] or "", 15, price[1] or "-" if print_type[1] else ""))
            print("\t\t", "-"*75)



def main():
    load_dotenv()
    collection_file = find_colletion_file(os.environ.get("PASS_TO_COLLECTION_FILE_DIRECTORY"))
    if not collection_file:
        print(
            f"No csv collection file in directory {os.environ.get("PASS_TO_COLLECTION_FILE_DIRECTORY")}"
        )
        return
    collection_data = get_data_from_collection(collection_file)
    cards_from_trade_post = get_cards_from_tradepost(os.environ.get("TRADE_POST_URL"))
    updated_card_data = update_collection_data_with_tp_data(collection_data, cards_from_trade_post)
    updated_card_data_with_td_price = update_collection_dta_with_topdeck_price(updated_card_data)
    print_to_terminal(updated_card_data_with_td_price)
    



if __name__ == "__main__":
    main()
