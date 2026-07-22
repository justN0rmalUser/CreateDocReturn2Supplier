from typing import Iterable, Self, overload
import os
from pathlib import Path
import configparser
from datetime import datetime, date, timedelta
import logging as log
import re


DATE_REGEX = r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"


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

    loggers_dict = log.Logger.manager.loggerDict
    try:
        if name in loggers_dict:
            # logging.getLogger безопасно вернет уже созданный объект логгера
            return log.getLogger(name)
        abstract_logger = log.getLogger(name)
        abstract_logger.setLevel(log.DEBUG)

        abstract_logger_hand = log.FileHandler(filename=fpath, encoding='utf-8')
        abstract_logger_hand.setFormatter(log.Formatter('[%(asctime)s] <%(name)s>: %(levelname)s | %(message)s', datefmt="%Y-%m-%d %H:%M:%S"))

        abstract_logger.addHandler(abstract_logger_hand)
    except Exception as exc:
        print(exc)
        raise
    else:
        return abstract_logger


def get_config(path="config.ini"):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


def validate_date_key(value: str) -> str:
    if re.fullmatch(DATE_REGEX, value) is None:
        raise ValueError("date key must have format YYYY-MM-dd")

    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date key must be a valid calendar date") from exc

    return value


def split_iso_date_range(start: str | date,
                         end: str | date) -> tuple[tuple[str, str], tuple[str, str]]:
    """Split an inclusive ISO date range into two fully covering halves."""
    start_date = (
        start
        if isinstance(start, date)
        else date.fromisoformat(validate_date_key(start))
    )
    end_date = (
        end
        if isinstance(end, date)
        else date.fromisoformat(validate_date_key(end))
    )

    if start_date > end_date:
        raise ValueError("start date must be less than or equal to end date")

    total_days = (end_date - start_date).days + 1
    if total_days < 2:
        raise ValueError("date range must contain at least two days")

    first_range_days = (total_days + 1) // 2
    first_end = start_date + timedelta(days=first_range_days - 1)
    second_start = first_end + timedelta(days=1)

    return (
        (start_date.isoformat(), first_end.isoformat()),
        (second_start.isoformat(), end_date.isoformat()),
    )


def isodate(stime: str, from_: str) -> str:
    return datetime.strptime(stime, from_).date().isoformat()


def day_of_week(delta_days: int = 0, *, postfix: str) -> str:
    week_days = (
        "Monday", "Tuesday",
        "Wednesday", "Thursday",
        "Friday", "Saturday",
        "Sunday"
    )
    target_date = date.today() + timedelta(days=delta_days)
    return week_days[target_date.weekday()] + postfix
