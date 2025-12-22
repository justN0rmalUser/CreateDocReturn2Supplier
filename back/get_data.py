import configparser
import json

import requests
from zeep import Client
from zeep.helpers import serialize_object

from datetime import date, timedelta, datetime

from utilities._utils import std
from utilities._stdfirm import get_fmt_firm
from utilities._stdcode import get_fmt_code

import logging as log


# Чтение конфига
cfg = configparser.ConfigParser(); cfg.read("config.ini")  # noqa: E702

get_log = log.getLogger("Getter")
get_log.setLevel(log.DEBUG)

get_hand = log.FileHandler(filename="logs\\get.log", encoding='utf-8')
get_hand.setFormatter(log.Formatter('[%(asctime)s] %(levelname)s | %(message)s'))

get_log.addHandler(get_hand)


class Rossko:
    def __init__(self, Url: str, Key_1: str, Key_2: str):
        self.URL = Url
        self.KEY_1 = Key_1
        self.KEY_2 = Key_2

    def get_orders(self, Date: date, *, need_start: date=None, need_end: date=None):
        # Создание клиента
        client = Client(self.URL)
        result = serialize_object(client.service.GetOrders(
            KEY1=self.KEY_1,
            KEY2=self.KEY_2,
            start_date=min(need_start, need_end) if need_start and need_end else Date,
            end_date=max(need_start, need_end) if need_start and need_end else Date
        ))
        
        # Запись в файл
        with open("js_res.json", 'w', encoding='utf-8') as js:
            json.dump(result, js, ensure_ascii=False, indent=4)
        return json.loads(json.dumps(result, ensure_ascii=False, indent=4))


    def filter_orders_by_status(self, orders: dict):
        """Фильтрация заказов по статусу"""
        summa = 0
        failure = {}
        success = {}

        orders_list = orders.get("OrdersList", {}).get("Order")
        for order_index in orders_list:
            for part in order_index.get("parts", {}).get("part"):
                # Успешные случаи
                if part.get("status") in (31, 36):  
                    
                    brand = get_fmt_firm.get(std(part['brand'])) 
                    code = get_fmt_code.get(std(part['partnumber']))
                    price = float(part['price'].replace(',', '.'))
                    count = float(part['count'])
                    
                    if brand and code:
                        success[(brand, code)] = (price, count)
                        summa += price * count

                # Неуспешные случаи
                if part.get("status") in range(32, 36): 
                    
                    brand = part['brand'] 
                    code = part['partnumber']
                    price = float(part['price'].replace(',', '.'))
                    count = float(part['count'])
                    
                    failure[(brand, code)] = (price, count)
        return (success, failure, summa)

class ProfitLiga:
    def __init__(self, Url: str, API_KEY: str):
        self.URL = Url
        self.Key = API_KEY

    # Профит    
    def profitReq(self, Date: date):
        # Старт
        params = {
            "secret": self.Key,
            "page": 1
            }
        aggregated_data = []
        while True:
            curent_page_data = requests.get(self.URL, params=params).json()

            big_date = datetime.strptime(curent_page_data["data"][0]['delivery_date'], "%Y-%m-%d").date()
            small_date = datetime.strptime(curent_page_data["data"][99]['delivery_date'], "%Y-%m-%d").date()

            date_less_sup = big_date >= Date
            date_bigger_inf = small_date < Date
            date_is_inf = small_date == Date
            date_less_inf = small_date > Date
            
            if date_less_sup:
                if date_bigger_inf:
                    aggregated_data.append(curent_page_data["data"])
                    break
            
                if date_is_inf:
                    aggregated_data.append(curent_page_data["data"])
                    params["page"] += 1

                if date_less_inf:
                    params["page"] += 1
            else:
                break
        return aggregated_data


    def profit_filter(self, pages, Date: date):
        summa = 0
        failure = {}
        success = {}
        # Старт
        for page in pages:
            for order in page:
                if datetime.strptime(order["delivery_date"], "%Y-%m-%d").date() == Date:
                    for good in order["products"]:
                        if good["status_id"] == '20':
                            brand = get_fmt_firm.get(std(good['brand']))
                            code = get_fmt_code.get(std(good['article']))
                            price = float(good['price'])
                            count = float(good['quantity'])

                            success[(brand, code)] = (price, count)
                            summa += price * count
        return (success, failure, summa)



def rosskoData(DATE):
    try:
        # Объявление
        get_log.info('Создание класса Rossko')
        rsko = Rossko(
            Url=cfg['Rossko']['url_order'],
            Key_1=cfg['Rossko']['first'],
            Key_2=cfg['Rossko']['second']
            )
        
        # Череда методов
        try:
            get_log.info('Запрос на сервер')
            rsko_answer = rsko.get_orders(Date=DATE)
            get_log.info('Запрос успешен')
        except:
            get_log.error('Запрос не успешен')
            raise

        try:
            get_log.info('Фильтрация')
            rsko_suc, rsko_fail, rsko_sum = rsko.filter_orders_by_status(rsko_answer)
            get_log.info('Фильтрация завершена')
        except:
            get_log.error('Ошибка при фильтрации')
            raise
    except Exception as exc:
        log.error(f"Ошибка: {exc}")
        raise SystemExit

    return rsko_suc, rsko_fail, rsko_sum
        
def profitData(DATE):
    try:
        # Объявление
        get_log.info('Создание класса Profit')
        prof = ProfitLiga(
            Url=cfg['Profit']['profit_get'],
            API_KEY=cfg['Profit']['profit_key']
            )
        
        # Череда методов
        try:
            get_log.info('Запрос на сервер')
            prof_answer = prof.profitReq(Date=DATE)
            get_log.info('Запрос успешен')
        except:
            get_log.error('Запрос не успешен')
            raise

        try:
            get_log.info('Фильтрация')
            prof_suc, prof_fail, prof_sum = prof.profit_filter(prof_answer, DATE)
            get_log.info('Фильтрация завершена')
        except:
            get_log.error('Ошибка при фильтрации')
            raise
    except Exception as exc:
        log.error(f"Ошибка: {exc}")
        raise SystemExit

    return prof_suc, prof_fail, prof_sum

def main():
    DATE = date.today() - timedelta(days=int(cfg['DEFAULT']['delta_days']))
    
    rsko_success, rsko_failure, rsko_summa = rosskoData(DATE)
    prof_success, prof_failure, prof_summa = profitData(DATE)
    
    return (8880, rsko_success, rsko_failure, rsko_summa), (8876, prof_success, prof_failure, prof_summa)