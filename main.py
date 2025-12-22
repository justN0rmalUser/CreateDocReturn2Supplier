from back import get_data
from back import request_db
from back import update_format

import sys
import logging as log


log.basicConfig(filename="logs\\global.log", encoding='utf-8')


def run():
    try:
        update_format.main()
    except SystemExit:
        log.error("Исключение в модуле update_format!")
        raise

    try:
        rossko, profit = get_data.main()
        assert rossko[1] or profit[1]
    except AssertionError:
        log.warning("Нет новых данных")
        raise
    except SystemExit:
        log.error("Исключение в модуле get_data!")
        raise
    except Exception as exc:
        log.critical(f"Непредвиденная ошибка: {exc}")
        raise
    
    try:
        assert request_db.main((rossko, profit)) # True если успешно
    except AssertionError:
        log.warning("Не все данные закомиченны")
    except SystemExit:
        log.error("Исключение в модуле request_db!")
        raise
    except Exception as exc:
        log.critical(f"Непредвиденная ошибка: {exc}")
        raise


if __name__ == '__main__':
    log.info("Старт скрипта")
    try:
        run()
    except Exception:
        sys.exit(1)