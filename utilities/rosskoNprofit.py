# utilities/rosskoNprofit.py
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Literal, Iterator, OrderedDict
from time import sleep

from zeep import Client
from zeep.helpers import serialize_object
from autodealerAPI.utils.functions.standard import std

from ._utils import get_config, logger, split_iso_date_range


cfg = get_config()
DATE = date.today() - timedelta(days=int(cfg["DEFAULT"]["delta_days"]))

# Настройка логгера для ошибок данных
GET_DATA_LOGGER = logger(name="Getter", fpath="logs/get.log")


class RosskoAPI:
    """Класс для взаимодействия с API Rossko.
    Предоставляет методы для получения и фильтрации заказов."""

    def __init__(self,
                 url: str,
                 key_1: str,
                 key_2: str):
        self.url = url
        self.key_1 = key_1
        self.key_2 = key_2
        self._cache: List[OrderedDict[str, str | int | float]] = []

    def _fetch_orders_for_date(self,
                               start: str,
                               end: str):
        """Отправляет SOAP-запрос на сервер Rossko на API "GetOrders" и возвращает структурированный список заказов.

        Args:
        ----
            **start** (`date | str`): Дата с которой будут возвращены ответы
            **end** (`date | str`): Дата по которую будут возвращены ответы

        Raises:
        ------
            `RuntimeError`: Неизвестная ошибка в ответе

        Returns:
        -------
            `List[OrderedDict[str, str | int | float]]`: Список данных
        """
        if (date.fromisoformat(end) - date.fromisoformat(start)).days >= 32:
            raise ValueError("Слишком большой промежуток времени, больше 32 дней")

        client = Client(self.url)
        GET_DATA_LOGGER.info("Запрос на дату: %s -> %s", start, end)
        raw_response = client.service.GetOrders(
            KEY1=self.key_1,  KEY2=self.key_2,
            start_date=start, end_date=end,
            limit=500
        )

        data = serialize_object(raw_response)
        GET_DATA_LOGGER.info("Статус запроса: %s; Информация: %s",
                             data.get('success'), data.get('message'))

        if not data.get("success"):
            if data.get("message") != "Ничего не найдено":
                raise RuntimeError("API Rossko вернул статус False, ошибка: <%s>",
                                   data.get('message'))

        orders = data.get("OrdersList", {}).get("Order", [])
        return orders if isinstance(orders, list) else [orders]

    def get_orders(
        self,
        start: str,
        end: str
    ) -> list[dict[str, str | float | int | dict]]:
        """Получает все заказы за указанный промежуток

        Parameters
        ----------
        **start** : `str`
            iso дата
        **end** : `str`
            iso дата

        Returns
        -------
        `list[dict[str, float | int | str]]`
            Список всех значений за период
        """
        result = []
        try:
            answer = self._fetch_orders_for_date(
                start,
                end
            )
            if len(answer) == 500 and start != end:
                raise ValueError
        except ValueError:
            first_half, second_half = split_iso_date_range(start, end)
            result += self.get_orders(*first_half)
            result += self.get_orders(*second_half)
        else:
            result += answer

        return result


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
