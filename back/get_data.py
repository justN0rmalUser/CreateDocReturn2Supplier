# get_data.py
from datetime import date, timedelta
from pathlib import Path
from utilities.rosskoNprofit import RosskoAPI#, ProfitLigaAPI
from utilities._utils import isodate, logger, get_config, day_of_week
from utilities.dataobject import ProductList, write_plist, read_plist
from functools import partial

# --- Настройка логгирования ---
GET_DATA_LOGGER = logger(name="Getter", fpath="logs/get.log")
cfg = get_config()


def get_rossko_data(start_date: date, end_date: date):
    """
    Получает и фильтрует данные от Rossko.
    Возвращает результат или None в случае ошибки.
    """
    try:
        GET_DATA_LOGGER.debug('ROSSKO: Инициализация класса')
        rossko_api = RosskoAPI(
            url=cfg["Rossko"]["URL"],
            key_1=cfg["Rossko"]["first_secret"],
            key_2=cfg["Rossko"]["second_secret"]
        )
    except Exception as e:
        GET_DATA_LOGGER.critical("ROSSKO | Неизвестная ошибка: %s", e)
        raise  # Переподнимаем исключение, если это критическая ошибка, не связанная с бизнес-логикой

    try:
        # Получение товаров за весь промежуток
        raw_products = rossko_api.get_orders(
            start=start_date.isoformat(),
            end=end_date.isoformat()
        )

        # Пути к pkl данным
        _yesterday = Path(r"data\temp") / (day_of_week(-1)+'.pkl')
        _today = Path(r"data\temp") / (day_of_week()+'.pkl')

        # Запись данных за сегодняшний день
        new_data = ProductList.from_rossko(raw_products)
        write_plist(new_data, _today)

        # Получение данных за предыдущий
        old_data: ProductList = read_plist(_yesterday)
    except Exception as e:
        GET_DATA_LOGGER.critical("ROSSKO | Неизвестная ошибка: %s", e)
        raise
    else:
        data: list[dict[str, float | str]] = []

        # Фильтрация, перепроверка данных
        for created_date, order_id, guid, statuses, (idx_order, idx_product) in new_data.difference(old_data):
            if statuses == (31, 36):
                continue

            order: dict = raw_products[idx_order]

            old_created_date: str = isodate(order["created_date"], "%d.%m.%Y %H:%M:%S")
            if old_created_date != created_date:
                GET_DATA_LOGGER.critical(err := f"ROSSKO | Дата не соответствует заявленной (raw: {old_created_date}; cls: {created_date})")
                raise ValueError(err)

            old_order_id: int = order["id"]
            if old_order_id != order_id:
                GET_DATA_LOGGER.critical(err := f"ROSSKO | ID заказа не соответствует заявленной (raw: {old_order_id}; cls: {order_id})")
                raise ValueError(err)

            product = order["parts"]["part"][idx_product]

            old_guid: str = product["guid"]
            if old_guid != guid:
                GET_DATA_LOGGER.critical(err := f"ROSSKO | ID товара не соответствует заявленной (raw: {old_guid}; cls: {guid})")
                raise ValueError(err)

            data.append(dict(
                    name=product["name"],
                    firm=product["brand"],
                    code=product["partnumber"],
                    count=float(product["count"]),
                    price=float(product["count"])
                )
            )

        # Возврать ID агента и итератора готовых данных
        return (8880, iter(data))


def main():
    """
    Главная функция для сбора данных от обоих API.
    Возвращает кортеж с успешными результатами.
    """
    end = date.today()
    start = end - timedelta(days=63)

    # Rossko
    rossko_data = get_rossko_data(
        start_date=start,
        end_date=end
    )

    return (rossko_data, None) # FIXME
