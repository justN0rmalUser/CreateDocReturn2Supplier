import configparser
import json

import requests
from zeep import Client
from zeep.helpers import serialize_object

from datetime import date, timedelta, datetime

from utilities._utils import std, logger
from utilities.fmt import fmt_firm, fmt_code


LOG = logger(name="Getter", fpath="logs\\get.log")
ERRDATA = logger(name="Errors", fpath="logs\\corrupt_data.log")

cfg = configparser.ConfigParser()
cfg.read("config.ini")

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
        # Запись в файл
        with open("js_res.json", 'w', encoding='utf-8') as js:
            json.dump(result, js, ensure_ascii=False, indent=4)

        output = json.loads(json.dumps(result, ensure_ascii=False, indent=4))
        assert output, "Ответ пустой"
        assert output["success"], "Значение успешности запроса в выходе = False"
        return output
    
    def filter_by_status(self, orders: dict):
        """Фильтрация заказов по статусу"""
        success = {}

        orders_list = orders.get("OrdersList", {}).get("Order")
        for order_index in orders_list:
            for part in order_index.get("parts", {}).get("part"):
                status = int(part.get("status"))
                # Успешные случаи
                if status in (31, 36):  
                    
                    brand = fmt_firm.get(std(part['brand'])) 
                    code = fmt_code.get(std(part['partnumber']))
                    price = float(part['price'].replace(',', '.'))
                    count = float(part['count'])
                    
                    if brand and code:
                        success[(brand, code)] = (price, count)
                    else:
                        ERRDATA.warning(f"""Модуль: get_data | Поставщик: Rossko | Тип ошибки: Отсутствие кода или бренда;
                                        У товара <{part["name"]}>
                                        Статус: <{status}> | Производитель: <{brand if brand else "НЕ НАЙДЕН"}> | Код товара: <{code if code else "НЕ НАЙДЕН"}>""")

                # Неуспешные случаи
                if status in range(32, 36): 
                    brand = part['brand'] 
                    code = part['partnumber']
                    ERRDATA.info(f"""Модуль: get_data | Поставщик: Rossko | Тип ошибки: Неподходящий случай
                                 У товара <{part["name"]}>
                                 Статус: <{status}> | Производитель: <{brand}> | Код товара: <{code}>""")
        assert success, "Никакие данные не подходят"
        return success


class ProfitLiga:
    def __init__(self, Url: str, API_KEY: str):
        self.URL = Url
        self.Key = API_KEY


    def _request(self, pageNum: int):
        params = {
            "secret": self.Key,
            "page": pageNum
        }
        output = requests.get(self.URL, params=params)
        assert output.status_code in range(200, 300), "Статус ответа не двухсотый"
        return output.json()
        
    def _can_be_next(self, page, pageSize: int) -> bool | None:
        top_of_page = datetime.strptime(page[0]['delivery_date'], "%Y-%m-%d").date()
        end_of_page = datetime.strptime(page[pageSize-1]['delivery_date'], "%Y-%m-%d").date()
        if top_of_page >= DATE > end_of_page:
            return False
        if top_of_page < DATE:
            return False
        if DATE <= end_of_page:
            return True
    
    def _thats_go_in(self, page, pageSize: int) -> bool | None:
        top_of_page = datetime.strptime(page[0]['delivery_date'], "%Y-%m-%d").date()
        end_of_page = datetime.strptime(page[pageSize-1]['delivery_date'], "%Y-%m-%d").date()
        return True if top_of_page >= DATE >= end_of_page else False
            

    def get_data(self):
        # Выход
        pages = []
        # Параметры цикла
        page = self._request(pageNum=1)
        count_of_pages = int(page["pages"]) + 1

        assert page, "Ответ пустой"
        assert page["status"] == "success", "Статус тела ответа - неудовлетворительный"
        for current_page in range(1, count_of_pages):
            # Пространство имен
            page = self._request(pageNum=current_page)
            # Рабочие данные
            size = int(page["pageSize"])
            data = page["data"]
            
            if self._thats_go_in(data, size):
                pages.append(data)
            if not self._can_be_next(data, size):
                break
        assert pages, "Нет подходящих страниц"
        return tuple(pages)
        
    def filter(self, pages: tuple[dict, ...]):
        result = {}
        for page in pages:
            for order in page:
                delivery_date = datetime.strptime(order['delivery_date'], "%Y-%m-%d").date()
                if delivery_date == DATE:
                    for good in order["products"]:
                        if good["status_id"] == "20":

                            brand = fmt_firm.get(std(good['brand']))
                            code = fmt_code.get(std(good['article']))
                            price = float(good['price'])
                            count = float(good['quantity'])

                            if brand and code:
                                result[(brand, code)] = (price, count)
                            else:
                                ERRDATA.warning(f"""Модуль: get_data | Поставщик: Rossko | Тип ошибки: Отсутствие кода или бренда:
                                                У товара <{good["description"]}>
                                                Код: <{code if code else "НЕ НАЙДЕН"}> | Производитель: <{brand if brand else "НЕ НАЙДЕН"}>""")
        assert result, "Пустой выход, никакие товары не добавлены"
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
        rsko_answer = rossko.get_data()
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

def get_profitData():
    # Объявление
    try:
        LOG.debug('PROFIT: Создание класса')
        profit = ProfitLiga(
            Url=    cfg["Profit"]["URL"],
            API_KEY=cfg["Profit"]["key"]
        )
    except Exception as exc:
        LOG.critical(f"PROFIT: Неизвестная ошибка! Ошибка: <{exc}>")
        raise

    # Череда методов
    ## Запрос на сервер
    try:
        LOG.debug('PROFIT: Запрос на сервер')
        pages_of_orders = profit.get_data()
    except AssertionError as ass:
        LOG.error(f'PROFIT | Assertion: Проверка ответа; Ошибка: <{ass}>')
        return None
    except Exception as exc:
        LOG.critical(f'PROFIT | Exception: Неизвестная ошибка! Ошибка: <{exc}>')
        raise
    else:
        LOG.info('PROFIT: Запрос успешен')

    ## Фильтрация данных в формат
    try:
        LOG.debug('PROFIT: Старт фильтрации')
        prof_suc = profit.filter(pages_of_orders)
    except AssertionError as ass:
        LOG.error(f'PROFIT | Assertion: Проверка ответа; Ошибка: <{ass}>')
        return None
    except Exception as exc:
        LOG.critical(f'PROFIT | Exception: Неизвестная ошибка! Ошибка: <{exc}>')
        raise
    else:
        LOG.info('PROFIT: Фильтрация завершена')
        return prof_suc


def main():
    rsko = get_rosskoData()
    prof = get_profitData()
    assert rsko or prof
    return (8880, rsko), (8876, prof)