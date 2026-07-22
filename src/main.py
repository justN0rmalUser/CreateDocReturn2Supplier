from .src import fetch, adapt

import sys
import os
import logging as log


log.basicConfig(filename="logs\\global.log", encoding='utf-8')
os.environ["CONFIG_PATH"] = "path\\to\\config"  #FIXME


def run():
    """Функция запуска"""
    # Получение данных с API
    try:
        data = fetch.run()
    except Exception as exc:
        log.critical(f'Критическая ошибка в модуле получения данных: {exc}')
        raise

    # Обработка информации
    try:
        info = adapt.run()
    except Exception as exc:
        log.critical(f'Критическая ошибка в модуле получения данных: {exc}')
        raise

    # Отправка данных в базу данных
    try:
        Update(contractorHeader=data) # True если успешно
    except AssertionError:
        log.warning("Не все данные закомиченны")
        raise
    except Exception as exc:
        log.critical(f"Непредвиденная ошибка: {exc}")
        raise


if __name__ == '__main__':
    log.info("Старт скрипта")
    run()
