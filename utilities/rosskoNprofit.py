# utilities/rosskoNprofit.py
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Literal, Iterator, OrderedDict, overload
from time import sleep

import requests 
from zeep import Client
from zeep.helpers import serialize_object
from autodealerAPI.utils.functions.standard import std

from ._utils import get_config, logger, split_iso_date_range, isodate


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
        GET_DATA_LOGGER.info("Статус запроса: %s; Информация: %s;",
                             data.get('success'), data.get('message'))

        if not data.get("success"):
            if data.get("message") != "Ничего не найдено":
                raise RuntimeError(f"API Rossko вернул статус False, ошибка: <{data.get('message')}>")
            else:
                raise AssertionError("Ничего не найдено")

        orders = data.get("OrdersList", {}).get("Order", [])
        GET_DATA_LOGGER.debug("Длина ответа: %i", len(orders))
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
            Дата, старт выборки заказов
        **end** : `str`
            Дата, конец выборки заказов

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
            if len(answer) >= 495 and start != end:
                GET_DATA_LOGGER.info("Ответ слишком большой, дробление запроса")
                raise ValueError
        except ValueError:
            first_half, second_half = split_iso_date_range(start, end)
            result += self.get_orders(*first_half)
            result += self.get_orders(*second_half)
        else:
            result += answer

        return result


class ProfitLigaAPI:
    """
    Класс для взаимодействия с API Profit Liga.
    Предоставляет методы для получения и фильтрации заказов.
    """
    def __init__(self, url: str, api_key: str, start: str, end: str):
        self.url = url
        self.api_key = api_key
        self.start_date = start
        self.end_date = end

    @overload
    def _make_request(self, page_num: int) -> tuple[int, list[dict]]: ...
    @overload
    def _make_request(self, page_num: int, *, with_pages: bool) -> tuple[int, list[dict], int]: ...

    def _make_request(self, page_num: int, *, with_pages: bool=False) -> tuple[int, list[dict]] | tuple[int, list[dict], int]:
        """Делает запрос на сервер

        Parameters
        ----------
        **page_num** : `int`
            Номер страницы во внутренней системе "Profit"
        **with_pages** : `bool`
            С количеством страниц

        Returns
        -------
        `tuple[int, list[dict]] | tuple[int, list[dict], int]`
            Результат запроса: [размер-страницы, данные, Опционально(количество-всех-страниц)]

        Raises
        ------
        `requests.RequestException`
            Ошикбка выполнения запроса
        `RuntimeError`
            Статус ответа не успешен 
        """
        params = {"secret": self.api_key, "page": page_num}
        try:
            response = requests.get(self.url, params=params)
            response.raise_for_status()
            sleep(0.5)
        except requests.RequestException as e:
            raise requests.RequestException(f"Ошибка при выполнении запроса к Profit Liga: {e}")
        else:
            answer = response.json()
            if (status := answer["status"]) != "success":
                raise RuntimeError(f"Статус не успешен: {status}")
            return ( (answer["pageSize"], answer["data"], answer["pages"]) 
                    if with_pages
                    else (answer["pageSize"], answer["data"]) )

    def validate_list(self, page: list[dict]):
        _date_pattern = r"%Y-%m-%d %H:%M:%S"

        # Получаем даты верхнюю и нижнюю
        top_of_page = isodate(page[0]["datetime"], _date_pattern)
        bot_of_page = isodate(page[-1]["datetime"], _date_pattern)

        # Если весь лист внутри диапазона
        if self.end_date >= top_of_page and self.start_date <= bot_of_page:
            return page

        # Ищем индекс первой даты, которая <= end_date (верхняя граница)
        start_idx = end_idx = None
        for i, item in enumerate(page):
            current_date = isodate(item["datetime"], _date_pattern)
            if self.end_date >= current_date >= self.start_date:
                if start_idx is None:
                    start_idx = end_idx = i
                else:
                    end_idx = i

        if start_idx is None:
            return []
        return page[start_idx:end_idx + 1]
    
    def get_orders(self) -> list[dict[str, str | float | int | dict]]:
        """Получает список всех товаров за проделенный промежуток

        Returns
        -------
        `list[dict[str, str | float | int | dict]]`
            Список заказов
        """
        _, data, count_pages = self._make_request(1, with_pages=True)
        result = self.validate_list(data)

        for page in range(2, count_pages):
            _, data = self._make_request(page)
            
            valid_data = self.validate_list(data)
            
            if result and not valid_data:
                break
            
            result += valid_data
        
        return result