"""Утилиты для конфига"""

import os
from typing import Any, TypeAlias
import tomllib
from pathlib import Path


PathLike: TypeAlias = str | os.PathLike[str]


def _normalize_config_path(_fp, *, enabled_check_exists: bool = True):
    """Проверка файлового пути

    Parameters
    ----------
    _fp : `Any`
        Проверка на `Path` или `str`
    enabled_check_exists : `bool`
        Возможность отключить проверку на существование

    Returns
    -------
    Path
        Возвращает нормализованный путь к конфигу

    Raises
    ------
    `TypeError`
        Входная переменная не соответствует необходимому типу данных (`Path | str`)
    `ValueError`
        Данный путь не указывает на файл
    `FileNotFoundError`
        Файла-конфига не существует
    `TypeError`
        Тип файла не соответствует необходимому стандарту (.toml)
    """
    if not isinstance(_fp, (str, Path)):
        raise TypeError("Недопустимый тип данных для переменной пути!")
    
    fp = _fp if isinstance(_fp, Path) else Path(_fp)
    
    if not fp.is_file():
        raise ValueError("Данный путь не указывает на файл!")
    if not fp.exists() and enabled_check_exists:
        raise FileNotFoundError("Файла-конфига не существует!")
    if not fp.suffix == ".toml":
        raise TypeError("Тип файла не соответствует необходимому стандарту (.toml)")
        
    return fp


def load_config(file_path: PathLike | Path | None = None) -> dict[str, Any]:
    """Выгрузка конфигурации

    Parameters
    ----------
    file_path : `str | Path`
        Путь к файлу с конфигом;

    Returns
    -------
    `dict[str, Any]`
        Выгруженная конфигурация в виде python-объекта;
    """
    # Проверка входных параметров
    if file_path is None:
        file_path = os.environ.get("CONFIG_PATH")

    fpath = _normalize_config_path(file_path)

    # Выгрузка
    with open(fpath, "rb") as FILE:
        return tomllib.load(FILE)


__all__ = ["load_config"]