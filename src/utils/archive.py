from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
import json
import os
from pathlib import Path
import pickle
import tempfile
from typing import Any, IO, TypeAlias


PathLike: TypeAlias = str | os.PathLike[str]
ArchiveDate: TypeAlias = date | datetime | str
Writer: TypeAlias = Callable[[Any, IO[Any]], None]


_ARCHIVE_SUFFIXES = frozenset({".json", ".pkl"})


def _normalize_date(value: ArchiveDate | None) -> date:
    """Return an archive date, accepting ISO ``YYYY-MM-DD`` strings."""
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("archive date must have format YYYY-MM-DD") from exc
    raise TypeError("archive date must be a date, datetime, ISO string, or None")


def _supplier_directory(archive_dir: PathLike, supplier: str) -> Path:
    """Build a safe supplier directory below the configured archive root."""
    if not isinstance(supplier, str):
        raise TypeError("supplier must be a string")
    if not supplier or supplier in {".", ".."}:
        raise ValueError("supplier must be a non-empty directory name")

    supplier_path = Path(supplier)
    if supplier_path.name != supplier or supplier_path.is_absolute():
        raise ValueError("supplier must be a single directory name")

    try:
        root = Path(archive_dir)
    except TypeError as exc:
        raise TypeError("archive_dir must be path-like") from exc
    return root / supplier


def _write_archive(
    data: Any,
    *,
    supplier: str,
    archive_date: ArchiveDate | None,
    archive_dir: PathLike,
    suffix: str,
    mode: str,
    writer: Writer,
) -> Path:
    """Write an archive atomically and return its final path."""
    supplier_dir = _supplier_directory(archive_dir, supplier)
    supplier_dir.mkdir(parents=True, exist_ok=True)
    target = supplier_dir / f"{_normalize_date(archive_date).isoformat()}{suffix}"

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode=mode,
            dir=supplier_dir,
            prefix=f".{target.name}.",
            delete=False,
            encoding="utf-8" if "b" not in mode else None,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer(data, temporary_file)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.replace(target)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return target


def archive_json(
    data: Any,
    supplier: str,
    archive_date: ArchiveDate | None = None,
    *,
    archive_dir: PathLike,
    json_default: Callable[[Any], Any] | None = None,
) -> Path:
    """Serialize a supplier response to a dated JSON archive.

    ``json_default`` can adapt response-specific values without coupling this
    module to a supplier SDK.  Existing archives for the same supplier and date
    are replaced atomically.
    """

    def write_json(value: Any, file: IO[Any]) -> None:
        json.dump(
            value,
            file,
            ensure_ascii=False,
            indent=2,
            default=json_default,
        )

    return _write_archive(
        data,
        supplier=supplier,
        archive_date=archive_date,
        archive_dir=archive_dir,
        suffix=".json",
        mode="w",
        writer=write_json,
    )


def archive_pkl(
    data: Any,
    supplier: str,
    archive_date: ArchiveDate | None = None,
    *,
    archive_dir: PathLike,
    protocol: int = pickle.HIGHEST_PROTOCOL,
) -> Path:
    """Serialize processed supplier data to a dated pickle archive."""

    def write_pickle(value: Any, file: IO[Any]) -> None:
        pickle.dump(value, file, protocol=protocol)

    return _write_archive(
        data,
        supplier=supplier,
        archive_date=archive_date,
        archive_dir=archive_dir,
        suffix=".pkl",
        mode="wb",
        writer=write_pickle,
    )


def flush(
    before: ArchiveDate,
    *,
    archive_dir: PathLike,
) -> tuple[Path, ...]:
    """Delete supported archive files dated earlier than ``before``.

    Only ``.json`` and ``.pkl`` files whose stem is a valid ISO date are
    considered.  Unrelated files are left untouched.  The returned tuple lists
    deleted paths, which makes cleanup observable for callers and tests.
    """
    cutoff = _normalize_date(before)
    try:
        root = Path(archive_dir)
    except TypeError as exc:
        raise TypeError("archive_dir must be path-like") from exc

    if not root.exists():
        return ()
    if not root.is_dir():
        raise NotADirectoryError(f"archive root is not a directory: {root}")

    deleted: list[Path] = []
    for supplier_dir in root.iterdir():
        if not supplier_dir.is_dir():
            continue
        for candidate in supplier_dir.iterdir():
            if not candidate.is_file() or candidate.suffix not in _ARCHIVE_SUFFIXES:
                continue
            try:
                candidate_date = date.fromisoformat(candidate.stem)
            except ValueError:
                continue
            if candidate_date < cutoff:
                candidate.unlink()
                deleted.append(candidate)

    return tuple(sorted(deleted))


__all__ = ["archive_json", "archive_pkl", "flush"]
