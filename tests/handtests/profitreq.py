import requests
from pprint import pprint
import json

params = {"secret": "MCGtSmtUuyjzKGMJERVTaKeMjQBzSrLV", "page": 1}

response = requests.get("https://api.pr-lg.ru/orders/list?", params=params)
response.raise_for_status()
with open("profit.json", 'w', encoding="utf-8") as f:
    f.write(json.dumps(response.json(), ensure_ascii=False, indent=2))
    json.load