from __future__ import annotations

from pathlib import Path
from typing import Annotated, Iterator, TypeAlias, Self
import pickle

import pydantic

from ._utils import validate_date_key, isodate


DateKey: TypeAlias = Annotated[str, pydantic.AfterValidator(validate_date_key)]
OrderID: TypeAlias = int
Guid: TypeAlias = str


ProductData: TypeAlias = dict[
    DateKey, dict[
        OrderID, dict[
            int, tuple[Guid, int, tuple[int, int]]
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
    def __init__(self, data: ProductData | None = None):
        self._data: ProductData | dict = (
            PDATA_ADAPTER.validate_python(data)
            if data is not None
            else {}
        )

    @classmethod
    def from_rossko(cls, data: list[dict]) -> Self:
        """Получение данных на основе api Rossko

        Parameters
        ----------
        **data** : `list[dict]`
            Преобразованный json в список товаров

        Returns
        -------
        `Self`
            Экземпляр класса `ProductList`
        """
        plist = cls()
        for order_idx, order in enumerate(data):
            for part_idx, part in enumerate(order["parts"]["part"]):
                cur_date:   str = isodate(order["created_date"], "%d.%m.%Y %H:%M:%S")
                order_id:   int = int(order["id"])
                guid:       str = part["guid"]
                status:     int = int(part["status"])

                plist.add({
                    cur_date: {
                        order_id: {
                            part_idx: (guid, status, (order_idx, part_idx))
                        }
                    }
                })
        return plist
    
    @classmethod
    def from_profit(cls, data: list[dict]) -> Self:
        plist = cls()
        for order_idx, order in enumerate(data):
            for part_idx, part in enumerate(order["products"]):
                cur_date:       str = isodate(order["datetime"], "%Y-%m-%d %H:%M:%S")
                order_id:       int = int(order["order_id"])
                pos_product_id: int = int(part["id"])
                guid:           str = part["article_id"]
                status:         int = int(part["status_id"])

                plist.add({
                    cur_date: {
                        order_id: {
                            pos_product_id: (guid, status, (order_idx, part_idx))
                        }
                    }
                })
        return plist

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
    def products(self) -> Iterator[tuple[DateKey, OrderID, int, Guid, int, tuple[int, int]]]:
        """Возвращает итератор на все товары с полным путем

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid, int, tuple[int, int]]]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_, _статус_, (_индекс заказа_, _индекс товара в заказе_)]
        """
        # Итерация по всем значениям
        for day, day_dict in self.data.items():
            for order, order_dict in day_dict.items():
                for item_idx, item in order_dict.items():
                    guid, status, path = item
                    yield day, order, item_idx, guid, status, path

    def _update(
        self,
        day: DateKey,
        order: int,
        idx_item: int,
        guid: str,
        status: int,
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
            self._data[day] = {}

        if self.data[day].get(order) is None:
            self._data[day][order] = {}

        self._data[day][order][idx_item] = (guid, status, path)

    def add(self, data: ProductList | ProductData) -> None:
        """Слияние списков

        Parameters
        ----------
        data : `ProductList | ProductData`
            Данные, с которыми производится слияние
        """
        data = (
            data
            if isinstance(data, ProductList)
            else ProductList(data)
        )

        for inner in data.products:
            self._update(*inner)

    def __add__(self, other):
        self.add(other)
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
                    raise ValueError(f"Товар не один и тот же: {day, order, old_guid} | {guid}")
            else:
                continue

            statuses = (old_status, new_status)

            if old_status != new_status and new_status in allow_statuses:
                yield day, order, guid, statuses, path


def write_plist(data: ProductList, path: Path | str) -> None:
    """Запись `ProductList` в .pkl формат

    Parameters
    ----------
    **data** : `ProductList`
        Класс данных, который надо записать
    **path** : `Path | str`
        Полный/относительный путь куда сохранять

    Raises
    ------
    `TypeError`
        Недопустимый тип входной переменной
    `ValueError`
        Расширение файла не "**.pkl**"
    """
    if not isinstance(path, (str, Path)) or not isinstance(data, ProductList):
        raise TypeError("Недопустимый тип входной переменной")

    path = path if isinstance(path, Path) else Path(path)

    if path.suffix != ".pkl":
        raise ValueError("Расширение файла должно быть .pkl")

    with open(path, 'wb') as fpkl:
        pickle.dump(data, fpkl)


def read_plist(path: Path | str) -> ProductList:
    """Получение класса `ProductList` из файла

    Parameters
    ----------
    **path** : `Path | str`
        Полный путь до файла

    Returns
    -------
    `ProductList`
        Класс с данными

    Raises
    ------
    `TypeError`
        Недопустимый тип входной переменной
    `ValueError`
        Расширение файла не "**.pkl**"
    `FileNotFoundError`
        Файл не найден (скорее всего это первый прогон)
    """
    if not isinstance(path, (str, Path)):
        raise TypeError("Недопустимый тип переменной для чтения")

    path = path if isinstance(path, Path) else Path(path)

    if not path.exists():
        raise FileNotFoundError("Такого пути не существует")

    if path.suffix != ".pkl":
        raise ValueError("Расширение файла должно быть .pkl")

    with open(path, 'rb') as fpkl:
        obj = pickle.load(fpkl)
        if not isinstance(obj, ProductList):
            raise TypeError("Объект не является \"ProductList\"")
        return obj
