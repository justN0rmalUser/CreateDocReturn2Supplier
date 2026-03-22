import json
from pprint import pprint

import requests
from zeep import Client
from zeep.helpers import serialize_object

from datetime import date, timedelta, datetime
import time

from utilities._utils import std, logger, get_config
from utilities.fmt import fmt_firm, fmt_code


LOG = logger(name="Getter", fpath="logs\\get.log")
ERRDATA = logger(name="Errors", fpath="logs\\corrupt_data.log")

cfg = get_config()
DATE = date.today() - timedelta(days=int(cfg["DEFAULT"]["delta_days"]))


class Rossko:
    def __init__(self, Url: str, Key_1: str, Key_2: str):
        self.URL = Url
        self.KEY_1 = Key_1
        self.KEY_2 = Key_2


    def get_data(self, *, need_start: date | None = None, need_end: date | None = None):
        # Создание клиента
        client = Client(self.URL)
        result = serialize_object(client.service.GetOrders(
            KEY1=self.KEY_1,
            KEY2=self.KEY_2,
            start_date=min(need_start, need_end) if need_start and need_end else DATE,
            end_date=max(need_start, need_end) if need_start and need_end else DATE
        ))

        with open("tempoo.json", 'w', encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, indent=4))
        output = json.loads(json.dumps(result, ensure_ascii=False, indent=4))
        
        if output["success"]:
            orders_list = output.get("OrdersList", {}).get("Order")
        else:
            raise AssertionError("Значение успешности запроса в выходе = False")
        
        assert orders_list, "Ответ пустой"
        return orders_list
    

    def filter_by_status(self, orders: list | tuple):
        """Фильтрация заказов по статусу"""
        result = {
            "metadata": {
                "suplier": 8880
            }
        }
        returned = {}
        sett = set()

        for order_index in orders:
            parts = order_index.get("parts", {}).get("part")
            for part in parts:
                status = int(part.get("status"))

                brand = fmt_firm.get(std(part['brand'])) 
                code = fmt_code.get(std(part['partnumber']))
                price = float(part['price'].replace(',', '.'))
                count = float(part['count'])

                if status in range(31, 34) or status == 36: # Возможен откат & Успешные случаи
                    if brand and code:
                        returned[part["guid"]] = {
                                "brand": brand, 
                                "partnumber": code, 
                                "count": count, 
                                "price": price
                            }
                        if status in range(31, 34):
                            with open(cfg["DEFAULT"]["disputParts_fp"], mode='a') as FILE:
                                FILE.write(f"{part["guid"]}|{order_index["created_date"]}\n")
                        if (uuid := f"{part["guid"]}|{brand}|{code}") in sett:
                            print(uuid)
                        else:
                            sett.add(uuid)
                    else:
                        ERRDATA.warning(f"""Модуль: get_data | Поставщик: Rossko | Тип ошибки: Отсутствие кода или бренда;
                                        У товара <{part["name"]}>
                                        Статус: <{status}> | Производитель: <{brand if brand else "НЕ НАЙДЕН"}> | Код товара: <{code if code else "НЕ НАЙДЕН"}>""")
        assert returned, "Никакие данные не подходят"
        result["parts"] = returned
        # pprint(result)
        return result


def get_rosskoData():
    # Объявление
    try:
        LOG.debug('ROSSKO: Создание класса')
        rossko = Rossko(
            Url=    cfg["Rossko"]["URL"],
            Key_1=  cfg["Rossko"]["first_secret"],
            Key_2=  cfg["Rossko"]["second_secret"]
        )
    except Exception as exc:
        LOG.critical(f"ROSSKO: Неизвестная ошибка! Ошибка: <{exc}>")
        raise

    # Череда методов
    ## Запрос на сервер
    try:
        LOG.debug('ROSSKO: Запрос на сервер')
        rsko_answer = rossko.get_data(need_start=datetime(2026, 3, 1), need_end=datetime(2026, 3, 20))
    except AssertionError as ass:
        LOG.error(f"ROSSKO | Assertion: Проверка ответа; Ошибка: <{ass}>")
        return None
    except Exception as exc:
        LOG.critical(f"ROSSKO | Exception: Неизвестная ошибка! Ошибка: <{exc}>")
        raise
    else:
        LOG.info('ROSSKO: Запрос успешен')            

    ## Фильтрация
    try:
        LOG.debug('ROSSKO: Старт фильтрации')
        rsko_suc = rossko.filter_by_status(rsko_answer)
    except AssertionError as ass:
        LOG.error(f"ROSSKO | Assertion: Проверка ответа; Ошибка: <{ass}>")
        return None
    except Exception as exc:
        LOG.critical(f"ROSSKO | Exception: Неизвестная ошибка! Ошибка: <{exc}>")
        raise
    else:
        LOG.info('ROSSKO: Фильтрация завершена')
        return rsko_suc

def main():
    rsko = get_rosskoData()
    out = [agent for agent in (rsko, ) if agent]
    assert any(out)
    return tuple(out)

main()