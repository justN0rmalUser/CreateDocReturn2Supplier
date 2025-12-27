import os
from pathlib import Path
import sys
import time
from datetime import datetime, date
import logging as log


def set_path_logging(prefix: str, dir_name: str) -> str:
    """
    Возвращает путь к новому лог-файлу с уникальным именем по дате и времени.
    Пример: all_data/logs/get_logs/get_20240607_153045.log
    Можно указать префикс для разных хэндлеров.
    """
    log_dir = os.path.join('all_data', 'logs', dir_name)
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%d_%m_%Y')
    log_filename = f"{prefix}_{timestamp}.log"
    log_path = os.path.join(log_dir, log_filename)
    return log_path

def logger(*, name: str, fpath: Path | str):
    if not isinstance(fpath, Path):
        fpath = Path(fpath)

    try:
        abstract_logger = log.getLogger(name)
        abstract_logger.setLevel(log.DEBUG)

        abstract_logger_hand = log.FileHandler(filename=fpath, encoding='utf-8')
        abstract_logger_hand.setFormatter(log.Formatter('[%(asctime)s] %(levelname)s | %(message)s'))

        abstract_logger.addHandler(abstract_logger_hand)
    except Exception as exc:
        print(exc)
        raise
    else:
        return abstract_logger

def std(word: str) -> str:
    if isinstance(word, str):
        return word.upper().replace('-', '').replace(' ', '').replace('.', '').replace('/', '').replace(',', '').strip()
    
