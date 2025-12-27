from back import get_data
from back import request_db
from back import update_format

import sys
import logging as log


log.basicConfig(filename="logs\\global.log", encoding='utf-8')


def run():
    """Функция запуска"""
    # Унификация и преобразование в удобный формат
    try:
        update_format.main()
    except SystemExit:
        log.error("Исключение в модуле update_format!")
        raise

    # Получение данных с API
    try:
        data = get_data.main()
    except AssertionError:
        log.warning('Пустой ответ в модуле "get_data"')
        sys.exit(0)
    except Exception as exc:
        log.critical(f'Критическая ошибка в модуле "get_data": {exc}')
        sys.exit(1)
    
    # Отправка данных в базу данных
    try:
        assert request_db.main(contractorHeader=data) # True если успешно
    except AssertionError:
        log.warning("Не все данные закомиченны")
        sys.exit(0)
    except Exception as exc:
        log.critical(f"Непредвиденная ошибка: {exc}")
        sys.exit(1)


if __name__ == '__main__':
    log.info("Старт скрипта")
    run()
