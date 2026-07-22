from __future__ import annotations

from pathlib import Path
from typing import Annotated, Iterator, Self, TypeAlias, TypedDict

import pydantic

from ..utils.other import isodate, logger, validate_date_key


fetch_data_log = logger(
    name="dataobject",
    fpath=Path(
        r"C:\Program Files\_Scripts\Create_ReturnNomeclature\logs\dataobject.log"
    ),
)
fetch_data_log.propagate = False


DateKey: TypeAlias = Annotated[str, pydantic.AfterValidator(validate_date_key)]
OrderID: TypeAlias = int
Guid: TypeAlias = str


class UnifiedProduct(TypedDict):
    name: str
    firm: str
    code: str
    count: float
    price: float


ProductEntry: TypeAlias = tuple[
    int,
    int,
    str | None,
    tuple[int, int],
    UnifiedProduct,
]

ProductData: TypeAlias = dict[
    DateKey, dict[
        OrderID, dict[
            Guid, list[ProductEntry]
        ]
    ],
]

PDATA_ADAPTER = pydantic.TypeAdapter(ProductData)


class ProductList:
    def __init__(
        self,
        agent_name: str,
        agent_id: int,
        data: ProductData | None = None,
    ) -> None:
        self._data: ProductData | dict = (
            PDATA_ADAPTER.validate_python(data)
            if data is not None
            else {}
        )

        self.agent_name = agent_name
        self.agent_id = agent_id

    @classmethod
    def from_rossko(cls, data: tuple[str, int, list[dict]]) -> Self:
        """Получение данных на основе api Rossko

        Parameters
        ----------
        **data** : `tuple[str, int, list[dict]]`
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
                cur_date = isodate(
                    order["created_date"],
                    "%d.%m.%Y %H:%M:%S",
                )
                order_id = int(order["id"])
                guid = part["guid"]
                status = int(part["status"])
                count = int(part["count"])
                comment = part["comment"]
                product = UnifiedProduct(
                    name=part["name"],
                    firm=part["brand"],
                    code=part["partnumber"],
                    count=float(part["count"]),
                    price=float(part["price"]),
                )

                plist.add(
                    cur_date,
                    order_id,
                    guid,
                    status,
                    count,
                    comment,
                    (order_idx, part_idx),
                    product,
                )
        return plist

    @classmethod
    def from_profit(cls, data: tuple[str, int, list[dict]]) -> Self:
        """Получение данных на основе api Profit-Liga

        Parameters
        ----------
        **data** : `tuple[str, int, list[dict]]`
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
                cur_date = isodate(
                    order["datetime"],
                    "%Y-%m-%d %H:%M:%S",
                )
                order_id = int(order["order_id"])
                guid = part["article_id"]
                status = int(part["status_id"])
                count = int(part["quantity"])
                comment = part["comment"]
                product = UnifiedProduct(
                    name=part["description"],
                    firm=part["brand"],
                    code=part["article"],
                    count=float(part["quantity"]),
                    price=float(part["price"]),
                )

                plist.add(
                    cur_date,
                    order_id,
                    guid,
                    status,
                    count,
                    comment,
                    (order_idx, part_idx),
                    product,
                )
        return plist

    @classmethod
    def adapt(cls, data: tuple[str, int, list[dict]]) -> Self:
        adapter = {
            "ROSSKO": cls.from_rossko,
            "PROFIT": cls.from_profit,
        }

        agent_name, _, _ = data

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
    def type_products(self) -> Iterator[tuple[DateKey, OrderID, Guid]]:
        """Возвращает итератор на все типы товаров в заказе с полным путем

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid]]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_]
        """
        # Итерация по всем значениям
        for day, day_dict in self.data.items():
            for order, order_dict in day_dict.items():
                for guid in order_dict:
                    yield day, order, guid

    @property
    def products(
        self,
    ) -> Iterator[
        tuple[
            DateKey,
            OrderID,
            Guid,
            int,
            int,
            str | None,
            tuple[int, int],
            UnifiedProduct,
        ]
    ]:
        """Возвращает итератор на все товары с полным путем

        Yields
        ------
        Iterator[tuple[DateKey, OrderID, Guid, int, int, str | None,
        tuple[int, int], UnifiedProduct]]
            Список товаров
            [_дата_, _ID заказа_, _ID товара_, _статус_,
            _количество_, _комментарий_, _путь_, _товар_]
        """
        # Итерация по всем значениям
        for day, order, guid in self.type_products:
            for item in self.data[day][order][guid]:
                status, count, comment, path, product = item
                yield day, order, guid, status, count, comment, path, product

    def add(
        self,
        day: DateKey,
        order: int,
        guid: str,
        status: int,
        count: int,
        comment: str | None,
        path: tuple[int, int],
        product: UnifiedProduct,
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
        **count** : `int`
            Количество товара
        **comment** : `str | None`
            Комментарий к товару
        **path** : `tuple[int, int]`
            Путь т-ра относительно ответа сервера; он создается
        **product** : `UnifiedProduct`
            Данные товара в унифицированном формате
        """
        if self.data.get(day) is None:
            fetch_data_log.debug(f"Дата-ключ не найден, создается новый: <{day}>")
            self._data[day] = {}

        if self.data[day].get(order) is None:
            fetch_data_log.debug(
                "ID заказа в %s как ключ не найден, создается новый: <%s>",
                day,
                order,
            )
            self._data[day][order] = {}

        if self.data[day][order].get(guid) is None:
            fetch_data_log.debug(
                "ID товара в %s как ключ не найден, создается новый: <%s>",
                order,
                guid,
            )
            self._data[day][order][guid] = []

        self._data[day][order][guid].append(
            (status, count, comment, path, product)
        )

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
        return ProductList(self.agent_name, self.agent_id, self.data)

    def __radd__(self, other):
        return self.__add__(other)
