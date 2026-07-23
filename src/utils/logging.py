import logging
import os
from functools import cached_property
from pathlib import Path
from typing import TypeAlias

from .config import load_config


cfg = load_config()

PathLike: TypeAlias = str | os.PathLike[str]
LogFormat: TypeAlias = logging.Formatter

SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")


def _success(
    self: logging.Logger,
    message: object,
    *args: object,
    **kwargs: object,
) -> None:
    if self.isEnabledFor(SUCCESS):
        self._log(SUCCESS, message, args, **kwargs)


# logging.Logger не предоставляет пользовательские уровни автоматически.
if not hasattr(logging.Logger, "success"):
    logging.Logger.success = _success  # type: ignore[attr-defined]


class _ColoredLevelFormatter(logging.Formatter):
    """Форматтер, окрашивающий только имя уровня."""

    RESET = "\033[0m"
    COLORS = {
        logging.DEBUG: "\033[90m",       # серый
        logging.INFO: "\033[36m",        # cyan
        SUCCESS: "\033[32m",             # зелёный
        logging.WARNING: "\033[33m",     # жёлтый
        logging.ERROR: "\033[38;5;203m", # розово-красный
        logging.CRITICAL: "\033[91m",    # алый
    }

    @classmethod
    def from_formatter(cls, formatter: logging.Formatter) -> "_ColoredLevelFormatter":
        return cls(
            fmt=formatter._style._fmt,
            datefmt=formatter.datefmt,
            style=formatter._style.default_format[0],
            validate=False,
            defaults=getattr(formatter, "_defaults", None),
        )

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        color = self.COLORS.get(record.levelno)
        if color:
            record.levelname = f"{color}{original_levelname}{self.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


class Logger:
    def __init__(
        self,
        name: str,
        *,
        logs_dir: PathLike | Path,
    ):
        self._name = name
        self._dir = Path(logs_dir)
        self._logger: logging.Logger | None = None

    def __getattr__(self, name: str):
        logger = self.__dict__.get("_logger")
        if logger is None:
            raise RuntimeError("Экземпляр логгера ещё не инициализирован")
        return getattr(logger, name)

    @cached_property
    def name(self) -> str:
        return self._name

    @cached_property
    def filepath(self) -> Path:
        return self._dir / Path(self.name).with_suffix(".log")

    @classmethod
    def new(
        cls,
        name: str,
        *,
        level: int = logging.INFO,
        format: LogFormat = LogFormat('[%(asctime)s] <%(name)s>: %(levelname)s | %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    ):
        logger = cls(
            name,
            logs_dir=cfg["Logging"]["path"],
        )
        logger._create_logger_instance(level, format)
        return logger

    @classmethod
    def get(cls, name: str):
        logger = cls(
            name,
            logs_dir=cfg["Logging"]["path"],
        )
        logger._get_logger_instance()
        return logger

    def _create_logger_instance(
        self,
        level: int,
        log_format: logging.Formatter,
    ) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(self.name)
        logger.setLevel(level)
        logger.propagate = False

        # Повторное создание логгера не должно дублировать каждую строку.
        for handler in tuple(logger.handlers):
            if getattr(handler, "_custom_logger_handler", False):
                logger.removeHandler(handler)
                handler.close()

        file_handler = logging.FileHandler(self.filepath, encoding="utf-8")
        file_handler.setFormatter(log_format)
        file_handler._custom_logger_handler = True  # type: ignore[attr-defined]

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(_ColoredLevelFormatter.from_formatter(log_format))
        console_handler._custom_logger_handler = True  # type: ignore[attr-defined]

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        self._logger = logger
        self.level = level

    def _get_logger_instance(self) -> None:
        logger = logging.Logger.manager.loggerDict.get(self.name)
        if not isinstance(logger, logging.Logger):
            raise KeyError(f'Логгера "{self.name}" не существует')

        self._logger = logger
        self.level = logger.level
