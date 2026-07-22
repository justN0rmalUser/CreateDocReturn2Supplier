import pickle
from pathlib import Path
from typing import Iterator, Literal

from .format import ProductList


SUPPLIER_STATUSES = {
    "ROSSKO": list(range(1, 4)) + list(range(5, 10)) + list(range(31, 37)),
    "PROFIT": list(range(1, 28))
}


def difference(
    old_plist: ProductList, 
    new_plist: ProductList, 
    allowed_statuses: tuple[int, ...]
) -> Iterator[tuple[str, int, str, tuple[int, int], tuple[int, int]]]:
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
    if not isinstance(old_plist, ProductList) or not isinstance(new_plist, ProductList):
        raise TypeError("Недопустимый тип входных данных")

    # Проверка соответствия агентов
    if old_plist.agent_id != new_plist.agent_id:
        raise ValueError("Поставщики должны быть идентичны")

    # Проверка типов входных данных
    if not isinstance(allowed_statuses, tuple):
        raise TypeError("Недопустимый тип входных данных")

    # Проверка дней
    if old_plist.max_day is not None and new_plist.max_day is not None:
        if old_plist.max_day > new_plist.max_day:
            raise ValueError("Максимальный день прошлого ProductList > максимального нынешнего")
    
    # Проверка статусов
    if not allowed_statuses:
        raise ValueError("Нет вообще никаких статусов")
    
    if (accepted_statuses := SUPPLIER_STATUSES.get(new_plist.agent_name)) is not None:
        if not set(allowed_statuses).issubset(accepted_statuses):
            raise ValueError("Недопустимые значения статусов")
    else:
        raise AttributeError("Допустимые статусы поставщика не найдены")

    for day, order, guid in old_plist.type_products:
        if old_plist.min_day == day:
            continue

        old_product_type = old_plist[day][order][guid]
        new_product_type = new_plist[day][order][guid]

        if len(old_product_type) == len(new_product_type):
            for old_product, new_product in zip(old_product_type, new_product_type):
                old_status, old_count, old_comment, old_path = old_product
                new_status, new_count, new_comment, new_path = new_product

                if (old_count == new_count and
                    old_comment == new_comment and
                    old_path[1] == new_path[1]):
                    if old_status != new_status and new_status in allowed_statuses:
                        yield day, order, guid, (old_status, new_status), new_path
                else:
                    #TODO логгирование аномалии с флагом warning
                    pass
        else:
            while True:
                # шаг по списку
                old_product = next(old_product_type, None)
                new_product = next(new_product_type, None)

                if old_product is None or new_product is None:
                    break
                else:
                    old_status, old_count, old_comment, (old_path_to_order, old_path_to_product) = old_product
                    new_status, new_count, new_comment, (new_path_to_order, new_path_to_product) = new_product

                diff_on = _create_diff_dict(old_product, new_product)

                if not diff_on["status"] and not diff_on["comment"] and not diff_on["count"]:
                    adjacent_product = next(new_product_type, None)

                    adj_status, adj_count, adj_comment, (adj_path_to_order, adj_path_to_product) = adjacent_product

                    diff_ca = _create_diff_dict(new_product, adjacent_product)
                    if not diff_ca["comment"] and diff_ca["status"] and (adj_path_to_product == new_path_to_product + 1): 
                        if adj_status in allowed_statuses:
                            yield day, order, guid, (new_status, adj_status), (adj_path_to_order, adj_path_to_product)
                            continue
                    elif diff_ca["comment"]:
                        old_product = next(old_product_type, None)
                        old_status, old_count, old_comment, (old_path_to_order, old_path_to_product) = old_product
                        
                        diff_oa = _create_diff_dict(old_product, adjacent_product)


                    
def _create_diff_dict(
    product: tuple[int, int, str, tuple[int, int]], 
    other_product: tuple[int, int, str, tuple[int, int]]
) -> dict[Literal["status", "count", "comment", "rel_path"], bool]:
    old_status, old_count, old_comment, (old_path_to_order, old_path_to_product) = product
    new_status, new_count, new_comment, (new_path_to_order, new_path_to_product) = other_product

    return  {
                "status": old_status != new_status,
                "count": old_count != new_count,
                "comment": old_comment != new_comment,
                "rel_path": old_path_to_product != new_path_to_product
            }


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
