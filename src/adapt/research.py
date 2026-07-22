import pickle
from functools import cache
from pathlib import Path
from typing import Iterator, TypeAlias
from os import makedirs

from .format import ProductEntry, ProductList, UnifiedProduct


SUPPLIER_STATUSES = {
    "ROSSKO": list(range(1, 4)) + list(range(5, 10)) + list(range(31, 37)),
    "PROFIT": list(range(1, 28)),
}

ResearchResult: TypeAlias = tuple[
    str,
    int,
    str,
    int,
    str,
    tuple[int, int],
    UnifiedProduct,
]


def difference(
    old_plist: ProductList,
    new_plist: ProductList,
    allowed_statuses: tuple[int, ...],
) -> Iterator[ResearchResult]:
    """Находит товары, которые поменяли свой статус

    Parameters
    ----------
    **old_plist** : `ProductList`
        Список товаров за предыдущий день
    **new_plist** : `ProductList`
        Список товаров за сегодняшний день
    **allowed_statuses** : `tuple[int, ...]`
        Список допустимых статусов

    Yields
    ------
    Iterator[ResearchResult]
        Список товаров
        [_имя заказчика_, _ID заказчика_, _дата_, _ID заказа_, _ID товара_, (старый _статус_, новый _статус_), _товар_]

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
    if not isinstance(old_plist, ProductList) or not isinstance(
        new_plist, ProductList
    ):
        raise TypeError("Недопустимый тип входных данных")

    # Проверка соответствия агентов
    if old_plist.agent_id != new_plist.agent_id:
        raise ValueError("Поставщики должны быть идентичны")
    
    agent_name = new_plist.agent_name
    agent_id = new_plist.agent_id

    # Проверка типов входных данных
    if not isinstance(allowed_statuses, tuple):
        raise TypeError("Недопустимый тип входных данных")

    # Проверка дней
    if old_plist.max_day is not None and new_plist.max_day is not None:
        if old_plist.max_day > new_plist.max_day:
            raise ValueError(
                "Максимальный день прошлого ProductList > "
                "максимального нынешнего"
            )

    # Проверка статусов
    if not allowed_statuses:
        raise ValueError("Нет вообще никаких статусов")

    accepted_statuses = SUPPLIER_STATUSES.get(agent_name)
    if accepted_statuses is not None:
        if not set(allowed_statuses).issubset(accepted_statuses):
            raise ValueError("Недопустимые значения статусов")
    else:
        raise AttributeError("Допустимые статусы поставщика не найдены")

    for day, order, guid in old_plist.type_products:
        if old_plist.min_day == day:
            continue

        old_product_type = old_plist.data[day][order][guid]
        new_product_type = new_plist.data[day][order][guid]

        if len(old_product_type) == len(new_product_type):
            for old_product, new_product in zip(
                old_product_type,
                new_product_type,
            ):
                old_status, old_count, old_comment, old_path, _ = old_product
                (
                    new_status,
                    new_count,
                    new_comment,
                    new_path,
                    new_data,
                ) = new_product

                if (
                    old_count == new_count
                    and old_comment == new_comment
                ):
                    if _is_return_transition(
                        agent_name,
                        old_status,
                        new_status,
                        allowed_statuses,
                    ):
                        yield (
                            agent_name, 
                            agent_id, 
                            day, 
                            order, 
                            guid, 
                            (old_status, new_status), 
                            new_data
                        )
                else:
                    # TODO логгирование аномалии с флагом warning
                    pass
        else:
            alignment = _align_product_type(old_product_type, new_product_type)
            if alignment is None:
                # TODO логгирование аномалии с флагом warning
                continue

            for old_product, new_product, partial_return in alignment:
                old_status = old_product[0]
                new_status, _, _, _, new_data = new_product

                # Полный возврат: статус изменился у исходной
                # позиции.
                if _is_return_transition(
                    agent_name,
                    old_status,
                    new_status,
                    allowed_statuses,
                ):
                    yield (
                        agent_name, 
                        agent_id, 
                        day, 
                        order, 
                        guid, 
                        (old_status, new_status), 
                        new_data
                    )

                # Частичный возврат: после исходной позиции
                # появилась дополнительная запись.
                if partial_return is not None:
                    partial_status, _, _, _, partial_data = partial_return
                    if _is_return_transition(
                        agent_name,
                        old_status,
                        partial_status,
                        allowed_statuses,
                    ):
                        yield (
                            agent_name,
                            agent_id,
                            day,
                            order,
                            guid,
                            (old_status, partial_status),
                            partial_data,
                        )


def _is_return_transition(
    agent_name: str,
    old_status: int,
    new_status: int,
    allowed_statuses: tuple[int, ...],
) -> bool:
    return (
        old_status != new_status
        and new_status in allowed_statuses
        and not (agent_name == "ROSSKO" and (old_status, new_status) == (31, 36))
    )


def _align_product_type(
    old_products: list[ProductEntry],
    new_products: list[ProductEntry],
) -> list[tuple[ProductEntry, ProductEntry, ProductEntry | None]] | None:
    """Сопоставляет старые позиции с новыми и отделяет частичные возвраты."""

    @cache
    def align(
        old_idx: int,
        new_idx: int,
    ) -> tuple[tuple[int, int, int | None], ...] | None:
        if old_idx == len(old_products):
            return () if new_idx == len(new_products) else None
        if new_idx >= len(new_products):
            return None

        old_product = old_products[old_idx]
        new_product = new_products[new_idx]

        # Путь может смещаться после вставок, а статус — меняться
        # при полном возврате. Исходную позицию определяют
        # неизменные количество и комментарий.
        if old_product[1:3] != new_product[1:3]:
            return None

        adjacent_idx = new_idx + 1
        if adjacent_idx < len(new_products):
            adjacent_product = new_products[adjacent_idx]
            if _is_partial_return(old_product, new_product, adjacent_product):
                tail = align(old_idx + 1, new_idx + 2)
                if tail is not None:
                    return ((old_idx, new_idx, adjacent_idx),) + tail

        tail = align(old_idx + 1, new_idx + 1)
        if tail is None:
            return None
        return ((old_idx, new_idx, None),) + tail

    indexes = align(0, 0)
    if indexes is None:
        return None

    return [
        (
            old_products[old_idx],
            new_products[new_idx],
            new_products[partial_idx] if partial_idx is not None else None,
        )
        for old_idx, new_idx, partial_idx in indexes
    ]


def _is_partial_return(
    old_product: ProductEntry,
    new_product: ProductEntry,
    adjacent_product: ProductEntry,
) -> bool:
    old_status = old_product[0]
    new_status, new_count, new_comment, new_path, _ = new_product
    (
        adjacent_status,
        adjacent_count,
        adjacent_comment,
        adjacent_path,
        _,
    ) = adjacent_product

    return (
        old_status == new_status
        and adjacent_status != new_status
        and adjacent_count < new_count
        and adjacent_comment == new_comment
        and adjacent_path[0] == new_path[0]
        and adjacent_path[1] == new_path[1] + 1
    )


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
    if not path.parent.exists():
        makedirs(path.parent)

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
