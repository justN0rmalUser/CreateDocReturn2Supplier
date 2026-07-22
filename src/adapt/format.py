from __future__ import annotations

from pathlib import Path
from typing import Annotated, Iterator, TypeAlias, Self

import pydantic

from .src.utils.other import validate_date_key, isodate, logger


fetch_data_log = logger(name="dataobject", fpath=Path(r"C:\Program Files\_Scripts\Create_ReturnNomeclature\logs\dataobject.log"))
fetch_data_log.propagate = False


DateKey: TypeAlias = Annotated[str, pydantic.AfterValidator(validate_date_key)]
OrderID: TypeAlias = int
Guid: TypeAlias = str


ProductData: TypeAlias = dict[
    DateKey, dict[
        OrderID, dict[
            Guid, list[ tuple[int, int, str | None, tuple[int, int]], ... ]
        ]
    ]
]

PDATA_ADAPTER = pydantic.TypeAdapter(ProductData)

ROSSKO_ACCEPTED_VALUES = (
    list(range(1, 4)) +
    list(range(5, 10)) +
    list(range(31, 37))
)

PROFIT_ACCEPTED_VALUES = list(range(1, 28))


class ProductList:
    def __init__(self, agent_name: str, agent_id: int, data: ProductData | None = None):        
        self._data: ProductData | dict = (
            PDATA_ADAPTER.validate_python(data)
            if data is not None
            else {}
        )
        
        self.agent_name = agent_name
        self.agent_id = agent_id

    @classmethod
    def from_rossko(cls, data: list[tuple[str, int, list[dict]]]) -> Self:
        """Получение данных на основе api Rossko

        Parameters
        ----------
        **data** : `list[tuple[str, int, list[dict]]]`
            Преобразованный json в список товаров

        Returns
        -------
        `Self`
            Экземпляр класса `ProductList`
        """
        fetch_data_log.info("Получение данных из ROSSKO")

        agent_name, agent_id, fetched_data = data
        plist = cls(agent_name, agent_id)

        for order_idx, order in enumerate(fetched_data):
            for part_idx, part in enumerate(order["parts"]["part"]):
                cur_date:   str = isodate(order["created_date"], "%d.%m.%Y %H:%M:%S")
                order_id:   int = int(order["id"])
                guid:       str = part["guid"]
                status:     int = int(part["status"])
                count:      int = int(part["count"])
                comment:    str | None = part["comment"]


                plist.merge({
                    cur_date: {
                        order_id: {
                            guid: (status, count, comment, (order_idx, part_idx))
                        }
                    }
                })
        return plist
    
    @classmethod
    def from_profit(cls, data: list[dict]) -> Self:
        """Получение данных на основе api Profit-Liga

        Parameters
        ----------
        **data** : `list[dict]`
            Преобразованный json в список товаров

        Returns
        -------
        `Self`
            Экземпляр класса `ProductList`
        """
        fetch_data_log.info("Получение данных из PROFIT-LIGA")

        agent_name, agent_id, fetched_data = data
        plist = cls(agent_name, agent_id)

        for order_idx, order in enumerate(fetched_data):
            for part_idx, part in enumerate(order["products"]):
                cur_date:   str = isodate(order["datetime"], "%Y-%m-%d %H:%M:%S")
                order_id:   int = int(order["order_id"])
                guid:       str = part["article_id"]
                status:     int = int(part["status_id"])
                count:      int = int(part["quantity"])
                comment:    str | None = part["comment"]

                plist.merge({
                    cur_date: {
                        order_id: {
                            guid: (status, count, comment, (order_idx, part_idx))
                        }
                    }
                })
        return plist

    @classmethod
    def adapt(cls, data: tuple[str, int, list[dict]]) -> Self:
        adapter = {
            "ROSSKO": cls.from_rossko,
            "PROFIT": cls.from_profit
        }

        agent_name, agent_id, fetched_data = data

        init_func = adapter.get(agent_name)

        if init_func is not None:
            return init_func(data)
        raise ValueError("Неизвестный поставщик")

    @property
    def data(self) -> ProductData:
        """Данные в полном объеме -> Данные (`ProductData`)"""
        return self._data

    @property
    def min_day(self) -> str | None:
        """Минимальный день списка -> Дата в формате **YYYY-MM-DD** (`str`)"""
        return min(self.data) if self.data != {} else None

    @property
    def max_day(self) -> str | None:
        """Максимальный день списка -> Дата в формате **YYYY-MM-DD** (`str`)"""
        return max(self.data) if self.data != {} else None

    @property
    def type_products(self) -> Iterator[tuple[DateKey, OrderID, Guid], ...]:
        """Возвращает итератор на все типы товаров в заказе с полным путем

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid], ...]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_]
        """
        # Итерация по всем значениям
        for day, day_dict in self.data.items():
            for order, order_dict in day_dict.items():
                for guid in order_dict:
                    yield day, order, guid

    @property
    def products(self) -> Iterator[tuple[DateKey, OrderID, int, Guid, int, tuple[int, int]]]:
        """Возвращает итератор на все товары с полным путем

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid, int, tuple[int, int]]]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_, _статус_, (_индекс заказа_, _индекс товара в заказе_)]
        """
        # Итерация по всем значениям
        for day, order, guid in self.type_products:
            for item in self.data[day][order][guid]:
                status, count, comment, path = item
                yield day, order, guid, status, count, comment, path

    def add(
        self,
        day: DateKey,
        order: int,
        guid: str,
        status: int,
        count: int,
        comment: str,
        path: tuple[int, int]
    ) -> None:
        """Добавление нового товара в список

        Parameters
        ----------
        **day** : `DateKey`
            Дата-ключ;   к нему обращаются или он создается
        **order** : `int`
            ID заказа;   к нему обращаются или он создается
        **guid** : `str`
            ID товара;   к нему обращаются или он создается
        **status** : `int`
            Статус т-ра; он создается
        **path** : `tuple[int, int]`
            Путь т-ра относительно ответа сервера; он создается
        """
        if self.data.get(day) is None:
            fetch_data_log.debug(f"Дата-ключ не найден, создается новый: <{day}>")
            self._data[day] = {}

        if self.data[day].get(order) is None:
            fetch_data_log.debug(f"ID заказа в {day} как ключ не найден, создается новый: <{order}>")
            self._data[day][order] = {}

        if self.data[day][order].get(guid) is None:
            fetch_data_log.debug(f"ID товара в {order} как ключ не найден, создается новый: <{guid}>")
            self._data[day][order][guid] = []

        self._data[day][order][guid].append((status, count, comment, path))

    def merge(self, data: ProductList | ProductData) -> None:
        """Слияние списков

        Parameters
        ----------
        data : `ProductList | ProductData`
            Данные, с которыми производится слияние
        """
        data = (
            data
            if isinstance(data, ProductList)
            else ProductList(self.agent_name, self.agent_id, data)
        )

        for inner in data.products:
            self.add(*inner)

    def __add__(self, other):
        self.merge(other)
        return ProductList(self.data)

    def __radd__(self, other):
        return self.__add__(other)

    def difference(
        self,
        old_product: ProductList,
        *,
        allow_statuses: tuple[int] | tuple[int, ...]
    ) -> Iterator[tuple[DateKey, OrderID, Guid, tuple[int, int], tuple[int, int]]]:
        """Находит товары, которые поменяли свой статус

        Parameters
        ----------
        **old_product** : `ProductList`
            Список товаров за предыдущий день
        **allow_statuses** : `tuple[int]`
            Список допустимых статусов, по умолчанию

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid, tuple[int, int], tuple[int, int]]]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_, (старый _статус_, новый _статус_), (_индекс заказа_, _индекс товара в заказе_)]

        Raises
        ------
        `TypeError`
            Недопустимый тип входных данных
        `Exception`
            Максимальный день прошлого ProductList > нынешнего максимального
        `ValueError`
            Полученные статусы не соответствуют допустимым
        """
        # Проверка типов входных данных
        if not isinstance(old_product, ProductList) or not isinstance(allow_statuses, tuple):
            raise TypeError("Недопустимый тип входных данных")

        # Проверка дней
        if old_product.max_day is not None and self.max_day is not None:
            if old_product.max_day > self.max_day:
                raise ValueError("Максимальный день прошлого ProductList > максимального нынешнего")

        # Проверка статусов
        if not allow_statuses:
            raise ValueError("Нет вообще никаких статусов")
        if not (set(allow_statuses).issubset(ROSSKO_ACCEPTED_VALUES) or set(allow_statuses).issubset(PROFIT_ACCEPTED_VALUES)):
            raise ValueError("Недопустимые значения")

        # Перебор подходящих товаров
        for product in old_product.products:
            day, order, item_idx, old_guid, old_status, _ = product

            if old_product.min_day != day:
                guid, new_status, path = self.data[day][order][item_idx]
                if guid != old_guid:
                    fetch_data_log.error(errmsg := f"Товар не один и тот же: {day, order, item_idx, old_guid} | {guid}")
                    raise ValueError(errmsg)
            else:
                continue

            statuses = (old_status, new_status)

            if old_status != new_status and new_status in allow_statuses:
                fetch_data_log.info("Готовые данные для обработки: %s", data := (day, order, guid, statuses, path))
                yield data

