import configparser
import logging
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.utils import config, other


class ConfigTests(unittest.TestCase):
    def test_normalize_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "settings.toml"
            wrong = root / "settings.txt"
            folder = root / "folder.toml"
            target.write_text('[section]\nvalue = 3\n', encoding="utf-8")
            wrong.write_text("x", encoding="utf-8")
            folder.mkdir()

            self.assertEqual(config._normalize_config_path(str(target)), target)
            self.assertEqual(config._normalize_config_path(target), target)
            self.assertEqual(config.load_config(target), {"section": {"value": 3}})
            with patch.dict(os.environ, {"CONFIG_PATH": str(target)}):
                self.assertEqual(config.load_config(), {"section": {"value": 3}})
            with self.assertRaises(TypeError):
                config._normalize_config_path(None)
            with self.assertRaises(ValueError):
                config._normalize_config_path(folder)
            with self.assertRaises(ValueError):
                config._normalize_config_path(root / "missing.toml")
            with self.assertRaises(TypeError):
                config._normalize_config_path(wrong)

    def test_unreachable_ordered_exists_guard_with_path_double(self):
        class FakePath:
            def __init__(self, value):
                self.value = value

            def is_file(self):
                return True

            def exists(self):
                return False

        with patch.object(config, "Path", FakePath):
            with self.assertRaises(FileNotFoundError):
                config._normalize_config_path("missing.toml")


class OtherTests(unittest.TestCase):
    def test_set_path_logging_and_config_parser(self):
        with tempfile.TemporaryDirectory() as directory, patch("src.utils.other.os.makedirs") as makedirs, patch(
            "src.utils.other.datetime"
        ) as dt:
            dt.now.return_value.strftime.return_value = "22_07_2026"
            path = other.set_path_logging("fetch", "daily")
            self.assertEqual(path, os.path.join("all_data", "logs", "daily", "fetch_22_07_2026.log"))
            makedirs.assert_called_once_with(os.path.join("all_data", "logs", "daily"), exist_ok=True)

            ini = Path(directory) / "config.ini"
            ini.write_text("[section]\nvalue=yes\n", encoding="utf-8")
            cfg = other.get_config(ini)
            self.assertIsInstance(cfg, configparser.ConfigParser)
            self.assertEqual(cfg["section"]["value"], "yes")

    def test_logger_new_existing_and_error(self):
        with tempfile.TemporaryDirectory() as directory:
            name = "autotest-new-logger"
            created = other.logger(name=name, fpath=str(Path(directory) / "test.log"))
            self.assertEqual(created.name, name)
            self.assertIs(other.logger(name=name, fpath=Path(directory) / "unused.log"), created)
            for handler in list(created.handlers):
                handler.close()
                created.removeHandler(handler)
            logging.Logger.manager.loggerDict.pop(name, None)

        error_name = "autotest-broken-logger"
        with patch("src.utils.other.log.FileHandler", side_effect=OSError("denied")), patch("builtins.print") as printer:
            with self.assertRaises(OSError):
                other.logger(name=error_name, fpath="bad.log")
        printer.assert_called_once()
        logging.Logger.manager.loggerDict.pop(error_name, None)

    def test_dates_and_weekday(self):
        self.assertEqual(other.validate_date_key("2026-07-22"), "2026-07-22")
        with self.assertRaisesRegex(ValueError, "format"):
            other.validate_date_key("22-07-2026")
        with self.assertRaisesRegex(ValueError, "calendar"):
            other.validate_date_key("2026-02-31")

        self.assertEqual(
            other.split_iso_date_range("2026-01-01", "2026-01-04"),
            (("2026-01-01", "2026-01-02"), ("2026-01-03", "2026-01-04")),
        )
        self.assertEqual(
            other.split_iso_date_range(date(2026, 1, 1), date(2026, 1, 5)),
            (("2026-01-01", "2026-01-03"), ("2026-01-04", "2026-01-05")),
        )
        with self.assertRaisesRegex(ValueError, "less"):
            other.split_iso_date_range("2026-01-02", "2026-01-01")
        with self.assertRaisesRegex(ValueError, "two"):
            other.split_iso_date_range("2026-01-01", "2026-01-01")

        self.assertEqual(other.isodate("22.07.2026", "%d.%m.%Y"), "2026-07-22")
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 7, 20)
        with patch.object(other, "date", FixedDate):
            self.assertEqual(other.day_of_week(2, postfix="_x"), "Wednesday_x")


if __name__ == "__main__":
    unittest.main()
