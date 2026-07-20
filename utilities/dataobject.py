from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Iterator, TypeAlias, Self, Literal
import pickle

import pydantic

from ._utils import validate_date_key, isodate, logger


fetch_data_log = logger(name="dataobject", fpath=Path(r"C:\Program Files\_Scripts\Create_ReturnNomeclature\logs\dataobject.log"))
fetch_data_log.propagate = False


DateKey: TypeAlias = Annotated[str, pydantic.AfterValidator(validate_date_key)]
OrderID: TypeAlias = int
Guid: TypeAlias = str


ProductData: TypeAlias = dict[
    DateKey, dict[
        OrderID, dict[
            Guid, list[tuple[int, tuple[int, int], str | None], ]
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
        fetch_data_log.debug("Создание класса...")
        
        self._data: ProductData | dict = (
            PDATA_ADAPTER.validate_python(data)
            if data is not None
            else {}
        )
        self.agent_name: Literal["ROSSKO", "PROFIT"] = None
        
        get_data_msg = "Данные получены успешно!" if self._data != {} else "Входящие данные пустые (по умолчанию)"
        fetch_data_log.info(get_data_msg)

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
        fetch_data_log.info("Получение данных из ROSSKO")
        plist = cls()
        for order_idx, order in enumerate(data):
            for part_idx, part in enumerate(order["parts"]["part"]):
                cur_date:   str = isodate(order["created_date"], "%d.%m.%Y %H:%M:%S")
                order_id:   int = int(order["id"])
                guid:       str = part["guid"]
                status:     int = int(part["status"])
                comment:    str | None = part.get("comment")

                plist.add({
                    cur_date: {
                        order_id: {
                            guid: [(status, (order_idx, part_idx), comment)]
                        }
                    }
                })

        plist.agent_name = "ROSSKO"
        return plist
    
    @classmethod
    def from_profit(cls, data: list[dict]) -> Self:
        fetch_data_log.info("Получение данных из PROFIT-LIGA")
        plist = cls()
        for order_idx, order in enumerate(data):
            for part_idx, part in enumerate(order["products"]):
                cur_date:   str = isodate(order["datetime"], "%Y-%m-%d %H:%M:%S")
                order_id:   int = int(order["order_id"])
                guid:       str = part["article_id"]
                status:     int = int(part["status_id"])
                comment:    str | None = part.get("comment")

                plist.add({
                    cur_date: {
                        order_id: {
                            guid: [(status, (order_idx, part_idx), comment)]
                        }
                    }
                })

        plist.agent_name = "PROFIT"
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
    def type_products(self) -> Iterator[tuple[DateKey, OrderID, Guid]]:
        """Итератор на типы товаров в заказе

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid]]
            _description_
        """
        for day, day_dict in self.data.items():
            for order, order_dict in day_dict.items():
                for guid in order_dict:
                    yield day, order, guid

    @property
    def products(self) -> Iterator[tuple[DateKey, OrderID, Guid, int, tuple[int, int], str | None]]:
        """Возвращает итератор на все товары с полным путем

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid, int, tuple[int, int]]]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_, _статус_, (_индекс заказа_, _индекс товара в заказе_)]
        """
        # Итерация по всем значениям
        for day, order, guid in self.type_products:
            for status, path, comment in self.data[day][order][guid]:
                fetch_data_log.info("Данные шага итератора: %s", data := (day, order, guid, status, path, comment))
                yield data

    def _update(
        self,
        day: DateKey,
        order: int,
        guid: str,
        status: int,
        path: tuple[int, int],
        comment: str | None
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
            fetch_data_log.debug(f"GUID товара в {order} как ключ не найден, создается новый: <{guid}>")
            self._data[day][order][guid] = []

        self._data[day][order][guid].append((status, path, comment))
        fetch_data_log.info(f"Товар добавлен: {day}:{order}:{guid}:{(status, path, comment)}")

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

        # Проверка на соответствие агентов
        if old_product.agent_name != self.agent_name:
            raise ValueError("Имя поставщиков должно быть одинаковое")

        # Проверка дней
        if old_product.max_day is not None and self.max_day is not None:
            if old_product.max_day > self.max_day:
                raise ValueError("Максимальный день прошлого ProductList > максимального нынешнего")

        # Проверка статусов
        if not allow_statuses:
            raise ValueError("Нет вообще никаких статусов")
        if self.agent_name == "ROSSKO" and not set(allow_statuses).issubset(ROSSKO_ACCEPTED_VALUES):
            raise ValueError("Недопустимые значения")
        if self.agent_name == "PROFIT" and not set(allow_statuses).issubset(PROFIT_ACCEPTED_VALUES):
            raise ValueError("Недопустимые значения")

        # Перебор подходящих товаров
        for product in old_product.type_products:
            day, order, guid = product
            old_record = old_product.data[day][order][guid]

            if old_product.min_day != day:
                record = self.data[day][order][guid]
            else:
                continue

            # Статус и комментарий являются устойчивой частью записи. Путь не
            # участвует в сравнении: сервер сдвигает индексы после вставки
            # строки частично возвращенного товара.
            old_keys = [(status, comment) for status, _, comment in old_record]
            keys = [(status, comment) for status, _, comment in record]
            matcher = SequenceMatcher(a=old_keys, b=keys, autojunk=False)

            def changed_data(old_idx: int, new_idx: int):
                old_status = old_record[old_idx][0]
                status, path, _ = record[new_idx]
                if old_status != status and status in allow_statuses:
                    statuses = (old_status, status)
                    data = (day, order, guid, statuses, path)
                    fetch_data_log.info("Готовые данные для обработки: %s", data)
                    return data
                return None

            for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
                if tag == "equal" or tag == "delete":
                    continue

                old_count = old_end - old_start
                new_count = new_end - new_start
                paired_count = min(old_count, new_count)

                # Обычная смена статуса существующих экземпляров товара.
                for offset in range(paired_count):
                    if data := changed_data(old_start + offset, new_start + offset):
                        yield data

                # Лишние элементы в новом ответе — строки, которые сервер
                # добавил сразу после исходного товара при частичном возврате.
                for new_idx in range(new_start + paired_count, new_end):
                    source_idx = old_start + paired_count - 1
                    if source_idx < 0:
                        source_idx = 0
                    elif source_idx >= len(old_record):
                        source_idx = len(old_record) - 1

                    if data := changed_data(source_idx, new_idx):
                        fetch_data_log.info(
                            "Добавленная строка товара связана с исходной: old=%s, new=%s",
                            old_record[source_idx],
                            record[new_idx],
                        )
                        yield data



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

    # В pkl записывается только актуальная структура ProductData.
    PDATA_ADAPTER.validate_python(data.data)
    with open(path, 'wb') as fpkl:
        pickle.dump(data, fpkl)
        fetch_data_log.info(f"Файл \"{path.name}\" - записан")


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
        PDATA_ADAPTER.validate_python(obj.data)
        fetch_data_log.info(f"Файл \"{path.name}\" - прочитан")
        return obj
