# utilities/rosskoNprofit.py
import json
import logging
import requests
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple, Any
from zeep import Client
from zeep.helpers import serialize_object

from .fmt import fmt_firm, fmt_code
from ._utils import std, get_config

cfg = get_config()
DATE = date.today() - timedelta(days=int(cfg["DEFAULT"]["delta_days"]))

# Настройка логгера для ошибок данных
ERRDATA_LOGGER = logging.getLogger("Errors")
ERRDATA_LOGGER.addHandler(logging.FileHandler("logs/corrupt_data.log"))
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
    def __init__(self, url: str, key_1: str, key_2: str):
        self.url = url
        self.key_1 = key_1
        self.key_2 = key_2

    def _make_request(self) -> dict:
        """Выполняет SOAP-запрос к API Rossko."""
        try:
            client = Client(self.url)
            raw_result = client.service.GetOrders(
                KEY1=self.key_1, 
                KEY2=self.key_2, 
                start_date=DATE, 
                end_date=DATE
            )
            # Преобразование результата Zeep в словарь Python
            json_str = json.dumps(serialize_object(raw_result), ensure_ascii=False, indent=4)
            return json.loads(json_str)
        except Exception as e:
            raise RuntimeError(f"Ошибка при выполнении запроса к Rossko: {e}")

    def get_raw_orders(self) -> List[dict]:
        """Получает список заказов из API."""
        response = self._make_request()
        if not response.get("success"):
            raise AssertionError("Значение успешности запроса в ответе от Rossko = False")

        orders_list = response.get("OrdersList", {}).get("Order")
        if not orders_list:
            raise AssertionError("Список заказов в ответе от Rossko пустой")
        return orders_list

    def filter_successful_orders(self, raw_orders: List[dict]) -> Dict[str, dict]:
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
                guid = part.get("guid")
                raw_brand = part.get('brand', '')
                raw_code = part.get('partnumber', '')
                
                brand = fmt_firm.get(std(raw_brand))
                code = fmt_code.get(std(raw_code))
                
                try:
                    price = float(part.get('price', '0').replace(',', '.'))
                    count = float(part.get('count', '0'))
                except ValueError:
                    log_missing_data_error("Rossko", part, brand, code, -1)
                    continue

                # Статус -1 используется для обозначения проблем с брендом/кодом
                status = int(part.get("status")) if brand and code else -1
                
                if status == 36 or 31 <= status < 34:  # Успешные или возможный откат
                    if guid not in returned_items:
                        returned_items[guid] = {"brand": brand, "partnumber": code, "count": count, "price": price}
                    else:
                        existing_item = returned_items[guid]
                        if existing_item["price"] == price:
                            existing_item["count"] += count
                else:
                    log_missing_data_error("Rossko", part, brand, code, status)
        
        if not returned_items:
            raise AssertionError("После фильтрации не найдено подходящих заказов от Rossko")
        
        return {"8880": returned_items}


class ProfitLigaAPI:
    """
    Класс для взаимодействия с API Profit Liga.
    Предоставляет методы для получения и фильтрации заказов.
    """
    def __init__(self, url: str, api_key: str):
        self.url = url
        self.api_key = api_key

    def _make_request(self, page_num: int) -> dict:
        """Выполняет GET-запрос к API Profit Liga."""
        params = {"secret": self.api_key, "page": page_num}
        try:
            response = requests.get(self.url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Ошибка при выполнении запроса к Profit Liga: {e}")

    def _should_fetch_next_page(self, page_data: List[dict], page_size: int) -> bool:
        """Определяет, нужно ли запрашивать следующую страницу."""
        top_date = datetime.strptime(page_data[0]['delivery_date'], "%Y-%m-%d").date()
        end_date = datetime.strptime(page_data[page_size - 1]['delivery_date'], "%Y-%m-%d").date()
        if top_date < DATE:
            return False
        if DATE <= end_date:
            return True
        # Если дата находится между первым и последним элементом страницы
        return top_date >= DATE > end_date

    def _is_target_date_on_page(self, page_data: List[dict], page_size: int) -> bool:
        """Проверяет, содержится ли целевая дата на текущей странице."""
        top_date = datetime.strptime(page_data[0]['delivery_date'], "%Y-%m-%d").date()
        end_date = datetime.strptime(page_data[page_size - 1]['delivery_date'], "%Y-%m-%d").date()
        return top_date >= DATE >= end_date

    def get_filtered_orders(self) -> Dict[Tuple[str, str], Tuple[float, float]]:
        """
        Получает все страницы и фильтрует заказы по дате и статусу.
        Возвращает словарь в формате {(brand, code): (price, count)}.
        """
        all_relevant_orders = []
        current_page = 1
        
        while True:
            response = self._make_request(current_page)
            
            if response.get("status") != "success":
                raise AssertionError(f"Статус ответа от Profit Liga не 'success': {response.get('status')}")
            
            page_data = response.get("data", [])
            if not page_data:
                break

            page_size = int(response.get("pageSize", 0))
            if not page_size or len(page_data) != page_size:
                 # Если страница короче, чем ожидалось, это конец
                 if not self._is_target_date_on_page(page_data, len(page_data)):
                     break
                 # Иначе добавляем и выходим
                 all_relevant_orders.extend(page_data)
                 break

            if self._is_target_date_on_page(page_data, page_size):
                all_relevant_orders.extend(page_data)
            
            if not self._should_fetch_next_page(page_data, page_size):
                break
            
            current_page += 1
            # Задержка для соблюдения ограничений API
            import time
            time.sleep(2.7)

        if not all_relevant_orders:
            raise AssertionError("Не найдено страниц с заказами на целевую дату от Profit Liga")

        # Фильтрация по статусу и дате доставки
        filtered_products = {}
        for order in all_relevant_orders:
            delivery_date = datetime.strptime(order['delivery_date'], "%Y-%m-%d").date()
            if delivery_date == DATE:
                for product in order.get("products", []):
                    if product.get("status_id") == "20":  # Успешный статус
                        raw_brand = product.get('brand', '')
                        raw_article = product.get('article', '')
                        
                        brand = fmt_firm.get(std(raw_brand))
                        code = fmt_code.get(std(raw_article))
                        
                        try:
                            price = float(product.get('price', '0'))
                            count = float(product.get('quantity', '0'))
                        except ValueError:
                            ERRDATA_LOGGER.warning(
                                f"Модуль: roskoNprofit | Поставщик: Profit Liga | "
                                f"Тип ошибки: Некорректное числовое значение; "
                                f"У товара <{product.get('description', 'Неизвестно')}> | "
                                f"Код: <{code if code else 'НЕ НАЙДЕН'}>"
                                f"Производитель: <{brand if brand else 'НЕ НАЙДЕН'}>"
                            )
                            continue
                        
                        if brand and code:
                            key = (brand, code)
                            if key in filtered_products:
                                # Если товар уже есть, суммируем количество
                                old_price, old_count = filtered_products[key]
                                if old_price == price:
                                    filtered_products[key] = (old_price, old_count + count)
                                else:
                                    # Цены различаются, возможно, разные поставки. Логично перезаписать?
                                    # Или логировать? Пока перезаписываем, как в оригинальном коде.
                                    filtered_products[key] = (price, old_count + count)
                            else:
                                filtered_products[key] = (price, count)
                        else:
                            ERRDATA_LOGGER.warning(
                                f"Модуль: roskoNprofit | Поставщик: Profit Liga | "
                                f"Тип ошибки: Отсутствие кода или бренда; "
                                f"У товара <{product.get('description', 'Неизвестно')}> | "
                                f"Код: <{code if code else 'НЕ НАЙДЕН'}> | "
                                f"Производитель: <{brand if brand else 'НЕ НАЙДЕН'}>"
                            )

        if not filtered_products:
            raise AssertionError("После фильтрации не найдено подходящих товаров от Profit Liga")

        return filtered_products