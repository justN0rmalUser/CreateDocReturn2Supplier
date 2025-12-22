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
        success, failure, summa = get_data.main()
        assert success
        assert summa
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
        assert request_db.main(success, summa) # True если успешно
    except AssertionError:
        log.warning("Не все данные закомиченны")
        raise
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
    except:
        sys.exit(1)