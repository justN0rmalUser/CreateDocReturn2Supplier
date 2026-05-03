from back.get_data import main as Request
from back.request_db import main as Update

import sys
import logging as log


log.basicConfig(filename="logs\\global.log", encoding='utf-8')


def run():
    """Функция запуска"""
    # Получение данных с API
    try:
        data = Request()
    except AssertionError:
        log.warning('Пустой ответ в модуле "get_data"')
        sys.exit(0)
    except Exception as exc:
        log.critical(f'Критическая ошибка в модуле "get_data": {exc}')
        sys.exit(1)
    
    # Отправка данных в базу данных
    try:
        Update(contractorHeader=data) # True если успешно
    except AssertionError:
        log.warning("Не все данные закомиченны")
        sys.exit(0)
    except Exception as exc:
        log.critical(f"Непредвиденная ошибка: {exc}")
        sys.exit(1)


if __name__ == '__main__':
    log.info("Старт скрипта")
    run()
