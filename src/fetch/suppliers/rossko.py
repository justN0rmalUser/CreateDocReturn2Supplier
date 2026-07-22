from datetime import date
from typing import OrderedDict

from zeep import Client
from zeep.helpers import serialize_object

from ..supplier_pattern import Supplier
from ...utils.config import load_config
from ...utils.other import split_iso_date_range


cfg = load_config()


class RosskoAPI(Supplier):
    """Класс для взаимодействия с API Rossko.
    Предоставляет методы для получения и фильтрации заказов."""

    NAME = "ROSSKO"
    ID = 8880

    def __init__(
        self,
        url: str = cfg["Suppliers"]["rossko"]["URL"],
        key_1: str = cfg["Suppliers"]["rossko"]["first_secret"],
        key_2: str = cfg["Suppliers"]["rossko"]["second_secret"]
    ):
        self.url = url
        self.key_1 = key_1
        self.key_2 = key_2

    def _fetch_orders_for_date(
        self,
        start: str,
        end: str
    ) -> list[OrderedDict[str, str | int | float]]:
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
        raw_response = client.service.GetOrders(
            KEY1=self.key_1,  KEY2=self.key_2,
            start_date=start, end_date=end,
            limit=500
        )

        data = serialize_object(raw_response)

        if not data.get("success"):
            if data.get("message") != "Ничего не найдено":
                raise RuntimeError(f"API Rossko вернул статус False, ошибка: <{data.get('message')}>")
            else:
                raise AssertionError("Ничего не найдено")

        orders = data.get("OrdersList", {}).get("Order", [])
        return orders if isinstance(orders, list) else [orders]

    def pull_data(
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
                raise ValueError
        except ValueError:
            first_half, second_half = split_iso_date_range(start, end)
            result += self.get_orders(*first_half)
            result += self.get_orders(*second_half)
        else:
            result += answer

        return result
        
