import configparser
import json
from zeep import Client
from zeep.helpers import serialize_object
from datetime import date, timedelta

from utilities._utils import std
from utilities._stdfirm import *
from utilities._stdcode import *

import logging as log


# Чтение конфига
cfg = configparser.ConfigParser(); cfg.read("config.ini")

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

    def get_orders(self, Delta: int=14, *, need_start: date=None, need_end: date=None):
        client = Client(self.URL)
        need_date = date.today() - timedelta(days=Delta)
        result = serialize_object(client.service.GetOrders(
            KEY1=self.KEY_1,
            KEY2=self.KEY_2,
            start_date=min(need_start, need_end) if need_start and need_end else need_date,
            end_date=max(need_start, need_end) if need_start and need_end else need_date
        ))
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
        return success, failure, summa



def main():
    # 1. Получить и сохранить данные
    success, failure, summa = {}, {}, 0.0
    log.info('Установка базовых значений')

    try:
        # Объявление
        rsko = Rossko(
            Url=cfg['Rossko']['url_order'],
            Key_1=cfg['Rossko']['first'],
            Key_2=cfg['Rossko']['second']
            )
        get_log.info('Создание класса Rossko')
        
        # Череда методов
        try:
            get_log.info('Запрос на сервер')
            rsko_answer = rsko.get_orders(Delta=int(cfg['DEFAULT']['delta_days']))
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
        
        # Объединение результов
        success = success | rsko_suc
        failure = failure | rsko_fail
        summa += rsko_sum
    except Exception as exc:
        log.error(f"Ошибка: {exc}")
        raise SystemExit

    return success, failure, summa
        
    