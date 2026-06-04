from __future__ import annotations

from pathlib import Path
from typing import Annotated, Iterator, TypeAlias, Self
from typing_extensions import TypedDict
import pickle

import pydantic

from ._utils import validate_date_key, isodate


DateKey: TypeAlias = Annotated[str, pydantic.AfterValidator(validate_date_key)]
OrderID: TypeAlias = int
Guid: TypeAlias = str
class GuidInner(TypedDict):
    status: int
    path: tuple[int, int]


ProductData: TypeAlias = dict[
    DateKey, dict[
        OrderID, dict[
            Guid, GuidInner
        ]
    ]
]

PDATA_ADAPTER = pydantic.TypeAdapter(ProductData)

ACCEPTED_VALUES = (
    list(range(1, 4)) +
    list(range(5, 10)) +
    list(range(31, 37))
)


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
                            order_id: {guid: {"status": status, "path": (order_idx, part_idx)}}
                        }
                    }
                )
        return plist

    @staticmethod
    def to_plist_format(data: list[dict]) -> dict:
        result = {}
        for order in data:
            cur_date: str = isodate(order["created_date"], "%d.%m.%Y %H:%M:%S")
            if not result.get(cur_date):
                result[cur_date] = {}

            order_id: int = int(order["id"])
            if not result.get(order_id):
                result[cur_date][order_id] = {}

            for part in order["parts"]["part"]:
                guid = part["guid"]
                result[cur_date][order_id][guid] = part
        return result

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
    def products(self) -> Iterator[tuple[DateKey, OrderID, Guid, int, tuple[int, int]]]:
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
                for guid, guid_dict in order_dict.items():
                    status = guid_dict["status"]
                    path = guid_dict["path"]
                    yield day, order, guid, status, path

    def _update(
        self,
        day: DateKey,
        order: int,
        guid: str,
        status: int,
        path: tuple[int, int],
        *,  must_overwrite: bool = True
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
        **must_overwrite** : `Optional[bool]`
            Перезаписывать ли статус товара, by default True
        """
        if self.data.get(day) is None:
            self._data[day] = {}

        if self.data[day].get(order) is None:
            self._data[day][order] = {}

        if must_overwrite:
            self._data[day][order][guid] = GuidInner(status=status, path=path)
        else:
            if self.data[day][order].get(guid) is None:
                self._data[day][order][guid] = GuidInner(status=status, path=path)

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

        for day, order, guid, status, path in data.products:
            self._update(day, order, guid, status, path)

    def __add__(self, other):
        self.add(other)
        return ProductList(self.data)

    def __radd__(self, other):
        return self.__add__(other)

    def difference(
        self,
        old_product: ProductList,
        *,
        allow_statuses: tuple[int] | tuple[int, ...] = (31, 36)
    ) -> Iterator[tuple[DateKey, OrderID, Guid, tuple[int, int], tuple[int, int]]]:
        """Находит товары, которые поменяли свой статус

        Parameters
        ----------
        **product_list** : `ProductList`
            Список товаров за предыдущий день
        **valid_statuses** : `tuple[int]`
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
        if allow_statuses != (31, 36):
            if not allow_statuses:
                raise ValueError("Нет вообще никаких статусов")
            if not set(allow_statuses).issubset(ACCEPTED_VALUES):
                raise ValueError("Недопустимые значения")

        # Перебор подходящих товаров
        for product in old_product.products:
            day, order, guid, old_status, _ = product

            if old_product.min_day != day:
                _guid_inner = self.data[day][order][guid]

                new_status = _guid_inner["status"]
                path = _guid_inner["path"]

                statuses = (old_status, new_status)
            else:
                continue

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
    """
    if not isinstance(path, (str, Path)):
        raise TypeError("Недопустимый тип переменной для чтения")

    path = path if isinstance(path, Path) else Path(path)

    if not path.exists():
        raise FileNotFoundError("Такого пути не существует")

    if path.suffix != ".pkl":
        raise ValueError("Расширение файла должно быть .pkl")

    with open(path, 'rb') as fpkl:
        return pickle.load(fpkl)
