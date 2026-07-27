import logging
import os
import re
import tempfile
from datetime import date, datetime
from functools import cached_property
from pathlib import Path
from typing import TypeAlias

from .config import load_config


cfg = load_config()

PathLike: TypeAlias = str | os.PathLike[str]
LogFormat: TypeAlias = logging.Formatter
LogDate: TypeAlias = date | datetime | str

DEFAULT_FORMAT = LogFormat('[%(asctime)s] <%(name)s>: %(levelname)s | %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
_RECORD_DATE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})(?:[ T][^\]]*)?\]")

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


def _normalize_date(value: LogDate) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("delay must have format YYYY-MM-DD") from exc
    raise TypeError("delay must be a date, datetime, or ISO string")


def _file_handlers_for(path: Path) -> tuple[logging.FileHandler, ...]:
    """Return registered file handlers that currently target ``path``."""
    target = os.path.normcase(str(path.resolve(strict=False)))
    loggers = [logging.getLogger()]
    loggers.extend(
        logger
        for logger in tuple(logging.Logger.manager.loggerDict.values())
        if isinstance(logger, logging.Logger)
    )

    result: list[logging.FileHandler] = []
    seen: set[int] = set()
    for logger in loggers:
        for handler in logger.handlers:
            if not isinstance(handler, logging.FileHandler):
                continue
            if id(handler) in seen:
                continue

            handler_path = os.path.normcase(
                str(Path(handler.baseFilename).resolve(strict=False))
            )
            if handler_path == target:
                seen.add(id(handler))
                result.append(handler)

    return tuple(result)


def flush(delay: LogDate, log_path: PathLike) -> int:
    """Remove log records dated earlier than ``delay``.

    Continuation lines (for example, a traceback) belong to the dated record
    immediately before them and are removed together with that record. Lines
    that do not belong to any dated record are preserved. The return value is
    the number of removed records.
    """
    cutoff = _normalize_date(delay)
    try:
        path = Path(log_path)
    except TypeError as exc:
        raise TypeError("log_path must be path-like") from exc

    if not path.exists():
        return 0
    if not path.is_file():
        raise IsADirectoryError(f"log path is not a file: {path}")

    handlers = _file_handlers_for(path)
    temporary_path: Path | None = None
    for handler in handlers:
        handler.acquire()

    try:
        for handler in handlers:
            handler.flush()

        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        retained: list[str] = []
        keep_current_record = True
        removed = 0

        for line in lines:
            match = _RECORD_DATE.match(line)
            if match is not None:
                try:
                    record_date = date.fromisoformat(match.group(1))
                except ValueError:
                    keep_current_record = True
                else:
                    keep_current_record = record_date >= cutoff
                    if not keep_current_record:
                        removed += 1

            if keep_current_record:
                retained.append(line)

        if removed == 0:
            return 0

        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
            encoding="utf-8",
            newline="",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.writelines(retained)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # Windows does not allow replacing a file while FileHandler keeps it
        # open. Closing only the streams keeps the handlers registered; their
        # next emit reopens the replaced file.
        for handler in handlers:
            if handler.stream is not None:
                handler.stream.close()
                handler.stream = None

        temporary_path.replace(path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    finally:
        for handler in reversed(handlers):
            handler.release()

    return removed


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
        filename: str | None = None
    ):
        self._name = name
        self._filename = filename
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
        if self._filename is None:
            return self._dir / Path(self.name).with_suffix(".log")
        return self._dir / Path(self._filename).with_suffix(".log")

    @classmethod
    def new(
        cls,
        name: str,
        filename: str | None = None,
        *,
        level: int = logging.INFO,
        format: LogFormat = DEFAULT_FORMAT
    ):
        logger = cls(
            name,
            logs_dir=cfg["Logging"]["path"],
            filename=filename
        )
        logger._create_logger_instance(level, format)
        return logger

    @classmethod
    def get(cls, name: str):
        logger = cls(
            name,
            logs_dir=cfg["Logging"]["path"],
            filename=None
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

    def close(self) -> None:
        if self._logger is None:
            return

        handlers = self._logger.handlers.copy()
        for handler in handlers:
            self._logger.removeHandler(handler)
            handler.close()

        self._logger = None


__all__ = ["DEFAULT_FORMAT", "Logger", "SUCCESS", "flush"]
