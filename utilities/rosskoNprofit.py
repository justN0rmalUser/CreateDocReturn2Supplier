# utilities/rosskoNprofit.py
import json
import logging
import requests
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Literal, Iterator
from zeep import Client
from zeep.helpers import serialize_object
from time import sleep

from autodealerAPI.utils.functions.standard import std
from ._utils import get_config, logger

cfg = get_config()
DATE = date.today() - timedelta(days=int(cfg["DEFAULT"]["delta_days"]))

# Настройка логгера для ошибок данных
GET_DATA_LOGGER = logger(name="Getter", fpath="logs/get.log")
ERRDATA_LOGGER = logging.getLogger("Errors")
ERRDATA_LOGGER.addHandler(logging.FileHandler("logs/corrupt_data.log", encoding="utf-8"))
ERRDATA_LOGGER.setLevel(logging.WARNING)


def log_missing_data_error(supplier_name: str, part_info: dict, brand: Optional[str], code: Optional[str], status: int):
    """Логирует ошибки отсутствия ключевых данных."""
    part_name = part_info.get("name", "Неизвестно")
    brand_str = brand if brand else "НЕ НАЙДЕН"
    code_str = code if code else "НЕ НАЙДЕН"
    message = (
        f"Модуль: roskoNprofit | Поставщик: {supplier_name} | "
        f"Тип ошибки: Отсутствие кода или бренда; "
        f"У товара <{part_name}> | Статус: <{status}> | "
        f"Производитель: <{brand_str}> | Код товара: <{code_str}>"
    )
    ERRDATA_LOGGER.warning(message)


class RosskoAPI:
    """
    Класс для взаимодействия с API Rossko.
    Предоставляет методы для получения и фильтрации заказов.
    """
    def __init__(self, url: str, key_1: str, key_2: str, start_date: date, end_date: date):
        if start_date > end_date:
            GET_DATA_LOGGER.error(err := "Стартовая дата больше конечной")
            raise ValueError(err)
        GET_DATA_LOGGER.info(f"Выборка даты: {start_date, end_date}")
        self.url = url
        self.key_1 = key_1
        self.key_2 = key_2
        self.start_date = start_date
        self.end_date = end_date
        self._cache: List[Dict[str, str | int | float]] = []

    def _fetch_orders_for_date(self, current_date: date) -> List[Dict[str, str | int | float]]:
        """Выполняет SOAP-запрос и возвращает структурированный список заказов."""
        client = Client(self.url)
        GET_DATA_LOGGER.info(f"Запрос на дату: {current_date}")
        raw_response = client.service.GetOrders(
            KEY1=self.key_1, 
            KEY2=self.key_2, 
            start_date=current_date, 
            end_date=current_date, 
            limit = 200
        )

        data = serialize_object(raw_response)
        GET_DATA_LOGGER.info(f"Статус запроса: {data.get("success")}; Информация: {data.get("message")}")

        if not data.get("success") and data.get("message") != "Ничего не найдено":
            raise RuntimeError(f"API Rossko вернул статус False, ошибка: <{data.get("message")}>")
            
        orders = data.get("OrdersList", {})

        if not orders:
            return []
        
        orders = orders.get("Order", {})
        return orders if isinstance(orders, list) else [orders]

    def __iter__(self) -> Iterator[Dict[str, str | int | float]]:
        """Реализует ленивую загрузку с однократным кэшированием."""
        try:
            if any(self._cache):
                GET_DATA_LOGGER.info("Итерация с кэша")
                yield from self._cache
            else:
                current_date = self.start_date
                GET_DATA_LOGGER.info("Старт запросов")
                while current_date <= self.end_date:
                    sleep(0.5)
                    raw_orders = self._fetch_orders_for_date(current_date)

                    current_date += timedelta(days=1)

                    if not raw_orders:
                        GET_DATA_LOGGER.warning("Ответ пустой!")
                        continue

                    for item in self.filter_successful_orders(raw_orders):
                        GET_DATA_LOGGER.info(f"Объект: {item}")
                        self._cache.append(item)
                        yield item
        except Exception as exc:
            # Сброс кэша гарантирует корректную перезагрузку при следующем вызове
            self._cache = None
            GET_DATA_LOGGER.critical(f"Неизвестная проблема: {exc}")
            print(f"Проблема: {exc}")
            raise

    def filter_successful_orders(self, raw_orders: List[dict]) -> tuple[Dict[str, dict]]:
        """
        Фильтрует заказы по статусу (успешные и возможные откаты).
        Возвращает словарь с уникальными товарами.
        """
        returned_items = {}
        
        for order in raw_orders:
            parts = order.get("parts", {}).get("part")
            if not parts:
                continue

            # parts может быть словарем для одного элемента
            if isinstance(parts, dict):
                parts = [parts]

            for part in parts:
                GET_DATA_LOGGER.info(f"Полученные данные: {part}")
                guid = part["guid"]
                name = part["name"]
                brand = part['brand']
                code = part['partnumber']
                price = std.numeric(part['price'])
                count = std.numeric(part['count'])

                # Статус -1 используется для обозначения проблем с брендом/кодом
                status = int(part.get("status")) if brand and code else -1
                
                if status in (31, 36):  # Успешные или возможный откат
                    if guid not in returned_items:
                        returned_items[guid] = {"name": name, "firm": brand, "code": code, "count": count, "price": price}
                    else:
                        returned_items[guid]["count"] += count
                elif 31 < status < 36:
                    log_missing_data_error("Rossko", part, brand, code, status)        
        return tuple(returned_items.values())
    
    def get_sum(self) -> float:
        summary = 0.0
        for product in self:
            print(product, flush=True)
            summary += product["count"] * product["price"]
        return float(summary)
        


# class ProfitLigaAPI:
#     """
#     Класс для взаимодействия с API Profit Liga.
#     Предоставляет методы для получения и фильтрации заказов.
#     """
#     def __init__(self, url: str, api_key: str):
#         self.url = url
#         self.api_key = api_key

#     def _make_request(self, page_num: int) -> dict:
#         """Выполняет GET-запрос к API Profit Liga."""
#         params = {"secret": self.api_key, "page": page_num}
#         try:
#             response = requests.get(self.url, params=params)
#             response.raise_for_status()
#             return response.json()
#         except requests.RequestException as e:
#             raise RuntimeError(f"Ошибка при выполнении запроса к Profit Liga: {e}")


#     def _should_fetch_next_page(self, page_data: List[dict], page_size: int) -> bool:
#         """Определяет, нужно ли запрашивать следующую страницу."""
#         top_date = datetime.strptime(page_data[0]['delivery_date'], "%Y-%m-%d").date()
#         end_date = datetime.strptime(page_data[page_size - 1]['delivery_date'], "%Y-%m-%d").date()
#         if top_date < DATE:
#             return False
#         if DATE <= end_date:
#             return True
#         # Если дата находится между первым и последним элементом страницы
#         return top_date >= DATE > end_date


#     def _is_target_date_on_page(self, page_data: List[dict], page_size: int) -> bool:
#         """Проверяет, содержится ли целевая дата на текущей странице."""
#         top_date = datetime.strptime(page_data[0]['delivery_date'], "%Y-%m-%d").date()
#         end_date = datetime.strptime(page_data[page_size - 1]['delivery_date'], "%Y-%m-%d").date()
#         return top_date >= DATE >= end_date


#     def get_filtered_orders(self) -> Dict[Tuple[str, str], Tuple[float, float]]:
#         """
#         Получает все страницы и фильтрует заказы по дате и статусу.
#         Возвращает словарь в формате {(brand, code): (price, count)}.
#         """
#         all_relevant_orders = []
#         current_page = 1
        
#         while True:
#             response = self._make_request(current_page)
            
#             if response.get("status") != "success":
#                 raise AssertionError(f"Статус ответа от Profit Liga не 'success': {response.get('status')}")
            
#             page_data = response.get("data", [])
#             if not page_data:
#                 break

#             page_size = int(response.get("pageSize", 0))
#             if not page_size or len(page_data) != page_size:
#                  # Если страница короче, чем ожидалось, это конец
#                  if not self._is_target_date_on_page(page_data, len(page_data)):
#                      break
#                  # Иначе добавляем и выходим
#                  all_relevant_orders.extend(page_data)
#                  break

#             if self._is_target_date_on_page(page_data, page_size):
#                 all_relevant_orders.extend(page_data)
            
#             if not self._should_fetch_next_page(page_data, page_size):
#                 break
            
#             current_page += 1
#             # Задержка для соблюдения ограничений API
#             import time
#             time.sleep(2.7)

#         if not all_relevant_orders:
#             raise AssertionError("Не найдено страниц с заказами на целевую дату от Profit Liga")

#         # Фильтрация по статусу и дате доставки
#         filtered_products = {}
#         for order in all_relevant_orders:
#             delivery_date = datetime.strptime(order['delivery_date'], "%Y-%m-%d").date()
#             if delivery_date == DATE:
#                 for product in order.get("products", []):
#                     if product.get("status_id") == "20":  # Успешный статус
#                         raw_brand = product.get('brand', '')
#                         raw_article = product.get('article', '')
                        
#                         brand = fmt_firm.get(std(raw_brand))
#                         code = fmt_code.get(std(raw_article))
                        
#                         try:
#                             price = float(product.get('price', '0'))
#                             count = float(product.get('quantity', '0'))
#                         except ValueError:
#                             ERRDATA_LOGGER.warning(
#                                 f"Модуль: roskoNprofit | Поставщик: Profit Liga | "
#                                 f"Тип ошибки: Некорректное числовое значение; "
#                                 f"У товара <{product.get('description', 'Неизвестно')}> | "
#                                 f"Код: <{code if code else 'НЕ НАЙДЕН'}>"
#                                 f"Производитель: <{brand if brand else 'НЕ НАЙДЕН'}>"
#                             )
#                             continue
                        
#                         if brand and code:
#                             key = (brand, code)
#                             if key in filtered_products:
#                                 # Если товар уже есть, суммируем количество
#                                 old_price, old_count = filtered_products[key]
#                                 if old_price == price:
#                                     filtered_products[key] = (old_price, old_count + count)
#                                 else:
#                                     # Цены различаются, возможно, разные поставки. Логично перезаписать?
#                                     # Или логировать? Пока перезаписываем, как в оригинальном коде.
#                                     filtered_products[key] = (price, old_count + count)
#                             else:
#                                 filtered_products[key] = (price, count)
#                         else:
#                             ERRDATA_LOGGER.warning(
#                                 f"Модуль: roskoNprofit | Поставщик: Profit Liga | "
#                                 f"Тип ошибки: Отсутствие кода или бренда; "
#                                 f"У товара <{product.get('description', 'Неизвестно')}> | "
#                                 f"Код: <{code if code else 'НЕ НАЙДЕН'}> | "
#                                 f"Производитель: <{brand if brand else 'НЕ НАЙДЕН'}>"
#                             )

#         if not filtered_products:
#             raise AssertionError("После фильтрации не найдено подходящих товаров от Profit Liga")

#         return filtered_products