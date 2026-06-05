# get_data.py
from datetime import date, timedelta
from pathlib import Path
from utilities.rosskoNprofit import RosskoAPI#, ProfitLigaAPI
from utilities._utils import isodate, logger, get_config, day_of_week
from utilities.dataobject import ProductList, write_plist, read_plist


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
        GET_DATA_LOGGER.info('ROSSKO: Получение товаров за весь промежуток')
        raw_products = rossko_api.get_orders(
            start=start_date.isoformat(),
            end=end_date.isoformat()
        )

        # Пути к pkl данным
        GET_DATA_LOGGER.debug('ROSSKO: Формирование путей для данных')
        _yesterday = Path(r"data\temp") / (day_of_week(-1)+'.pkl')
        _today = Path(r"data\temp") / (day_of_week()+'.pkl')

        # Запись данных за сегодняшний день
        GET_DATA_LOGGER.info('ROSSKO: Формирование данных для класса данных')
        new_data = ProductList.from_rossko(raw_products)
        write_plist(new_data, _today)

        # Получение данных за предыдущий
        GET_DATA_LOGGER.info('ROSSKO: Получение данных за вчерашний день')
        old_data: ProductList = read_plist(_yesterday)
    except Exception as e:
        GET_DATA_LOGGER.critical("ROSSKO | Неизвестная ошибка: %s", e)
        raise
    else:
        data: list[dict[str, float | str]] = []

        # Фильтрация, перепроверка данных
        GET_DATA_LOGGER.info('ROSSKO: Итерация и сверка результатов')
        for created_date, order_id, guid, statuses, (order_idx, product_idx) in new_data.difference(old_data, allow_statuses=(31, 36)):
            if statuses == (31, 36):
                continue

            raw_order: dict = raw_products[order_idx]

            old_created_date: str = isodate(raw_order["created_date"], "%d.%m.%Y %H:%M:%S")
            if old_created_date != created_date:
                GET_DATA_LOGGER.critical(err := f"ROSSKO | Дата не соответствует заявленной (raw: {old_created_date}; cls: {created_date})")
                raise ValueError(err)

            old_order_id: int = raw_order["id"]
            if old_order_id != order_id:
                GET_DATA_LOGGER.critical(err := f"ROSSKO | ID заказа не соответствует заявленной (raw: {old_order_id}; cls: {order_id})")
                raise ValueError(err)

            raw_product: dict = raw_order["parts"]["part"][product_idx]

            old_guid: str = raw_product["guid"]
            if old_guid != guid:
                GET_DATA_LOGGER.critical(err := f"ROSSKO | ID товара не соответствует заявленной (raw: {old_guid}; cls: {guid})")
                raise ValueError(err)

            data.append(good := dict(
                    name=raw_product["name"],
                    firm=raw_product["brand"],
                    code=raw_product["partnumber"],
                    count=float(raw_product["count"]),
                    price=float(raw_product["price"])
                )
            )
            GET_DATA_LOGGER.info(f'ROSSKO: Добавлен товар <{good}>')

        # Возврать ID агента и итератора готовых данных
        if data:
            return (8880, iter(data))
        return None

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
