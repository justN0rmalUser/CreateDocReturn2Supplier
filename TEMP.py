import requests
from pprint import pprint


params = {"secret": "MCGtSmtUuyjzKGMJERVTaKeMjQBzSrLV"}
try:
    response = requests.get("https://api.pr-lg.ru/orders/list?", params=params)
    response.raise_for_status()
    pprint(response.json())
except requests.RequestException as e:
    raise RuntimeError(f"Ошибка при выполнении запроса к Profit Liga: {e}")