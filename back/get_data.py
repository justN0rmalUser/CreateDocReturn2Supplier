# get_data.py
from datetime import date, timedelta
from utilities.rosskoNprofit import RosskoAPI#, ProfitLigaAPI
from utilities._utils import logger, get_config

# --- Настройка логгирования ---
GET_DATA_LOGGER = logger(name="Getter", fpath="logs/get.log")
CFG = get_config()
DATE_OFFSET = date.today() - timedelta(days=int(CFG["DEFAULT"]["delta_days"]))


def get_rossko_data(start=DATE_OFFSET, end=DATE_OFFSET):
    """
    Получает и фильтрует данные от Rossko.
    Возвращает результат или None в случае ошибки.
    """
    try:
        GET_DATA_LOGGER.debug('ROSSKO: Инициализация класса')
        GET_DATA_LOGGER.debug('ROSSKO: Запрос на сервер')
        rossko_api = RosskoAPI(
            url=CFG["Rossko"]["URL"],
            key_1=CFG["Rossko"]["first_secret"],
            key_2=CFG["Rossko"]["second_secret"],
            start_date=start,
            end_date=end
        )
        GET_DATA_LOGGER.info('ROSSKO: Запрос успешен, итератор получен')

        summary = 0.0
        print(rossko_api, flush=True)
        for product in rossko_api:
            print(product, flush=True)
            summary += product["count"] * product["price"]
                
        return (8880, summary, rossko_api)

    except AssertionError as e:
        GET_DATA_LOGGER.error(f"ROSSKO | Assertion Error: {e}")
        return None
    except Exception as e:
        GET_DATA_LOGGER.critical(f"ROSSKO | Неизвестная ошибка: {e}")
        raise # Переподнимаем исключение, если это критическая ошибка, не связанная с бизнес-логикой


# def get_profit_data():
#     """
#     Получает и фильтрует данные от Profit Liga.
#     Возвращает кортеж (идентификатор, результат) или None в случае ошибки.
#     """
#     try:
#         GET_DATA_LOGGER.debug('PROFIT: Инициализация класса')
#         profit_api = ProfitLigaAPI(
#             url=CFG["Profit"]["URL"],
#             api_key=CFG["Profit"]["key"]
#         )

#         GET_DATA_LOGGER.debug('PROFIT: Запрос на сервер')
#         filtered_data = profit_api.get_filtered_orders()
#         GET_DATA_LOGGER.info('PROFIT: Запрос и фильтрация успешны')

#         # Возвращается кортеж, как в оригинальном коде
#         return (8876, filtered_data)

#     except AssertionError as e:
#         GET_DATA_LOGGER.error(f"PROFIT | Assertion Error: {e}")
#         return None
#     except Exception as e:
#         GET_DATA_LOGGER.critical(f"PROFIT | Неизвестная ошибка: {e}")
#         raise # Переподнимаем исключение, если это критическая ошибка


def main():
    """
    Главная функция для сбора данных от обоих API.
    Возвращает кортеж с успешными результатами.
    """
    start = date.fromisoformat(CFG["DEFAULT"]["start_date"])
    end = date.fromisoformat(CFG["DEFAULT"]["end_date"])
    print(start, end)

    rossko_data = get_rossko_data(start, end)
    # profit_data = get_profit_data()

    # successful_results = [res for res in (rossko_data, ) if res is not None]
    print(rossko_data[1], 'asd')
    if rossko_data[1] == 0 or rossko_data is None:
        raise AssertionError("Ни один из источников данных не вернул успешный результат.")
        
    return (rossko_data, None) # FIXME
