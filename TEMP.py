from zeep import Client
from datetime import date
import requests
from pprint import pprint

print(date.today())

params = {"secret": "MCGtSmtUuyjzKGMJERVTaKeMjQBzSrLV"}
try:
    client = Client("http://api.rossko.ru/service/v2.1/GetOrders")
    raw_response = client.service.GetOrders(
        KEY1="29a962af3ba240b014147bc6271e9de6",
        KEY2="9e1f5e4bfbb91f2359a897fc8664a643", 
        start_date=date.fromisoformat('2026-01-01'), 
        end_date=date.fromisoformat('2026-04-29'),
        limit=100
    )    
    pprint(raw_response)
except requests.RequestException as e:
    raise RuntimeError(f"Ошибка при выполнении запроса к Profit Liga: {e}")