import requests
import pprint
import json
from datetime import date, timedelta

print(date.today() - timedelta(days=int(14)))

params = {
    "secret": "MCGtSmtUuyjzKGMJERVTaKeMjQBzSrLV",
    "page": 2
}
res = requests.get("https://api.pr-lg.ru/orders/list/?", params=params)
with open("jsko.json", 'w', encoding='utf-8') as js: 
    json.dump(res.json(), js, ensure_ascii=False, indent=4)