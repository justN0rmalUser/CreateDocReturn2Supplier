import pickle
from pathlib import Path

from .format import ProductList


SUPPLIER_STATUSES = {
    "ROSSKO": list(range(1, 4)) + list(range(5, 10)) + list(range(31, 37)),
    "PROFIT": list(range(1, 28))
}


def difference(old_plist: ProductList, new_plist: ProductList, allow_statuses: tuple[int, ...]):
    """Находит товары, которые поменяли свой статус

    Parameters
    ----------
    **old_plist** : `ProductList`
        Список товаров за предыдущий день
    **new_plist** : `ProductList`
        Список товаров за сегодняшний день
    **allow_statuses** : `tuple[int, ...]`
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

    if old_plist.agent_id != new_plist.agent_id:
        raise ValueError("Поставщики должны быть идентичны")

    if not isinstance(allow_statuses, tuple):
        raise TypeError("Недопустимый тип входных данных")

    # Проверка дней
    if old_plist.max_day is not None and new_plist.max_day is not None:
        if old_plist.max_day > new_plist.max_day:
            raise ValueError("Максимальный день прошлого ProductList > максимального нынешнего")
    
    # Проверка статусов
    if not allow_statuses:
        raise ValueError("Нет вообще никаких статусов")
    
    if (accepted_statuses := SUPPLIER_STATUSES.get(new_plist.agent_name)) is not None:
        if not set(allow_statuses).issubset(accepted_statuses):
            raise ValueError("Недопустимые значения статусов")
    else:
        raise AttributeError("Допустимые статусы поставщика не найдены")

    


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
