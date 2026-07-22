import logging as log
import os
from datetime import date, timedelta
from pathlib import Path

os.environ["path_to_config"] = "config.toml"  #FIXME

from . import adapt, fetch, update
from .utils import archive, config


log.basicConfig(filename="logs\\global.log", encoding='utf-8')

cfg = config.load_config()
ARCHIVE_JSON_PATH = Path(cfg["Backup"]["archive"]["server_answers"])
ARCHIVE_PKL_PATH = Path(cfg["Backup"]["archive"]["product_difference_checkup"])


def run():
    """Функция запуска"""
    # Получение данных с API
    try:
        raw_data = fetch.run()
    except Exception as exc:
        log.critical(f'Критическая ошибка в модуле получения данных: {exc}')
        raise

    # Обработка информации
    try:
        data = adapt.run(raw_data)
    except Exception as exc:
        log.critical(f'Критическая ошибка в модуле получения данных: {exc}')
        raise

    # Отправка данных в базу данных
    try:
        update.run(data)
    except AssertionError:
        log.warning("Не все данные закомиченны")
        raise
    except Exception as exc:
        log.critical(f"Непредвиденная ошибка: {exc}")
        raise


if __name__ == '__main__':
    log.info("Старт скрипта")
    log.info("Очистка старых логов")
    
    log_delay = date.today() - timedelta(cfg["Logging"]["log_day_delay"])
    
    archive.flush(log_delay, ARCHIVE_JSON_PATH)
    archive.flush(log_delay, ARCHIVE_PKL_PATH)

    run()
