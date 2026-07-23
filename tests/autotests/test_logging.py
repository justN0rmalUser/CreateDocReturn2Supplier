import logging
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch


os.environ["CONFIG_PATH"] = str(Path(__file__).with_name("config.toml"))

from src.utils.logging import flush


class LoggingFlushTestCase(unittest.TestCase):
    def test_flush_removes_old_records_with_continuation_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "application.log"
            log_path.write_text(
                "log header\n"
                "[2026-07-01 10:00:00] <test>: ERROR | old\n"
                "Traceback (most recent call last):\n"
                "  old continuation\n"
                "[2026-07-03 10:00:00] <test>: INFO | cutoff\n"
                "[2026-07-04 10:00:00] <test>: INFO | new\n",
                encoding="utf-8",
            )

            removed = flush("2026-07-03", log_path)

            self.assertEqual(removed, 1)
            self.assertEqual(
                log_path.read_text(encoding="utf-8"),
                "log header\n"
                "[2026-07-03 10:00:00] <test>: INFO | cutoff\n"
                "[2026-07-04 10:00:00] <test>: INFO | new\n",
            )

    def test_flush_accepts_dates_and_handles_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.log"
            self.assertEqual(flush(date(2026, 7, 3), missing), 0)
            self.assertEqual(flush(datetime(2026, 7, 3, 12), missing), 0)

    def test_flush_replaces_file_used_by_registered_handler(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "application.log"
            logger = logging.getLogger(f"flush-open-file-{id(self)}")
            second_logger = logging.getLogger(f"flush-second-open-file-{id(self)}")
            logger.setLevel(logging.INFO)
            second_logger.setLevel(logging.INFO)
            logger.propagate = False
            second_logger.propagate = False
            handler = logging.FileHandler(log_path, encoding="utf-8")
            second_handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] <%(name)s>: %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            second_handler.setFormatter(handler.formatter)
            logger.addHandler(handler)
            second_logger.addHandler(second_handler)

            try:
                log_path.write_text(
                    "[2026-07-01 10:00:00] <test>: INFO | old\n"
                    "[2026-07-03 10:00:00] <test>: INFO | keep\n",
                    encoding="utf-8",
                )

                self.assertEqual(flush("2026-07-03", log_path), 1)
                logger.info("after flush")
                second_logger.info("after second handler")

                contents = log_path.read_text(encoding="utf-8")
                self.assertNotIn("| old", contents)
                self.assertIn("| keep", contents)
                self.assertIn("| after flush", contents)
                self.assertIn("| after second handler", contents)
            finally:
                logger.removeHandler(handler)
                second_logger.removeHandler(second_handler)
                handler.close()
                second_handler.close()
                logging.Logger.manager.loggerDict.pop(logger.name, None)
                logging.Logger.manager.loggerDict.pop(second_logger.name, None)

    def test_flush_validates_arguments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                flush("2026-02-30", Path(tmp_dir) / "test.log")
            with self.assertRaises(TypeError):
                flush(123, Path(tmp_dir) / "test.log")  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                flush(date.today(), object())  # type: ignore[arg-type]
            with self.assertRaises(IsADirectoryError):
                flush(date.today(), tmp_dir)

    def test_flush_failure_keeps_registered_handler_usable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "application.log"
            log_path.write_text(
                "[2026-07-01 10:00:00] <test>: INFO | old\n",
                encoding="utf-8",
            )
            logger = logging.getLogger(f"flush-failure-{id(self)}")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            handler = logging.FileHandler(log_path, encoding="utf-8")
            logger.addHandler(handler)

            try:
                with patch(
                    "src.utils.logging.Path.replace",
                    side_effect=PermissionError("denied"),
                ):
                    with self.assertRaises(PermissionError):
                        flush("2026-07-03", log_path)

                logger.info("still usable")
                self.assertIn(
                    "still usable",
                    log_path.read_text(encoding="utf-8"),
                )
                self.assertEqual(
                    list(Path(tmp_dir).glob(".application.log.*")),
                    [],
                )
            finally:
                logger.removeHandler(handler)
                handler.close()
                logging.Logger.manager.loggerDict.pop(logger.name, None)


if __name__ == "__main__":
    unittest.main()
