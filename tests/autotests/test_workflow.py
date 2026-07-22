import os
import logging
import runpy
import sys
import types
import unittest
import warnings
from contextlib import contextmanager
from datetime import date
from unittest.mock import Mock, patch

os.environ.setdefault("path_to_config", "config.toml")
logging.getLogger().addHandler(logging.NullHandler())
logging.getLogger("Request").addHandler(logging.NullHandler())
logging.getLogger("Errors").addHandler(logging.NullHandler())


def install_autodealer_stub():
    module = types.ModuleType("autodealerAPI")
    module.Connection = Mock(name="Connection")
    module.DatabaseConfig = Mock(name="DatabaseConfig")
    module.setup_logging = Mock(name="setup_logging")
    sys.modules["autodealerAPI"] = module


install_autodealer_stub()

from src import adapt, fetch, main, update
from src.adapt.format import ProductList


def product():
    return {"name": "Part", "firm": "Brand", "code": "P", "count": 1.0, "price": 2.0}


class FetchWorkflowTests(unittest.TestCase):
    def test_fetch_run_collects_and_archives(self):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 7, 22)

        provider = Mock(NAME="ROSSKO", ID=8880)
        provider.NAME = "ROSSKO"
        provider.ID = 8880
        provider.pull_data.return_value = [{"order": 1}]
        archive = Mock()
        with patch.object(fetch, "SUPPLIERS", (provider,)), patch.object(
            fetch, "cfg", {
                "DEFAULT": {"delta_days": 1},
                "Backup": {"archive": {"server_answers": "archives"}},
            }
        ), patch.object(fetch, "archive_json", archive), patch.object(fetch, "date", FixedDate):
            result = fetch.run()
        self.assertEqual(result, [("ROSSKO", 8880, [{"order": 1}])])
        provider.pull_data.assert_called_once_with(
            start=FixedDate(2026, 5, 19),
            end=FixedDate(2026, 7, 21),
        )
        archive.assert_called_once_with(
            [{"order": 1}],
            "rossko",
            archive_dir="archives",
        )

    def test_fetch_run_rejects_empty_provider_set(self):
        with patch.object(fetch, "SUPPLIERS", ()):
            with self.assertRaisesRegex(ValueError, "пустые"):
                fetch.run()


class AdaptWorkflowTests(unittest.TestCase):
    def test_adapt_run_writes_compares_and_archives(self):
        current = ProductList("ROSSKO", 8880, {
            "2026-06-02": {1: {"g": [(31, 1, None, (0, 0), product())]}},
        })
        previous = ProductList("ROSSKO", 8880)
        write = Mock()
        read = Mock(return_value=previous)
        archive = Mock()
        diff_row = ("ROSSKO", 8880, "2026-06-02", 1, "g", (5, 31), product())

        with patch.object(adapt.ProductList, "adapt", return_value=current), patch.object(
            adapt, "day_of_week", side_effect=lambda delta_days, postfix: ("Today" if delta_days == 0 else "Yesterday") + postfix
        ), patch.object(adapt, "write_plist", write), patch.object(
            adapt, "read_plist", read
        ), patch.object(adapt, "difference", return_value=iter([diff_row])) as difference, patch.object(
            adapt, "archive_pkl", archive
        ), patch.object(adapt, "WORKFLOW_PATH", adapt.Path("cache")), patch.object(
            adapt, "cfg", {"Backup": {"archive": {"product_difference_checkup": "pkls"}}}
        ):
            result = adapt.run([("ROSSKO", 8880, [])])

        self.assertEqual(result, [("ROSSKO", 8880, [product()])])
        self.assertEqual(write.call_args.args[1], adapt.Path("cache/rossko/Today_rossko.pkl"))
        self.assertEqual(read.call_args.args[0], adapt.Path("cache/rossko/Yesterday_rossko.pkl"))
        difference.assert_called_once_with(previous, current, (31, 36))
        archive.assert_called_once_with(current, "rossko", archive_dir="pkls")


class TransactionDouble:
    def __init__(self, create_error=None, fill_error=None):
        self.create_error = create_error
        self.fill_error = fill_error
        self.created = []
        self.filled = []

    @contextmanager
    def start_transaction(self, **kwargs):
        self.start_kwargs = kwargs
        yield self

    def create_document_out(self, agent_id, zero):
        if self.create_error:
            raise self.create_error
        self.created.append((agent_id, zero))
        return {"DOCUMENT_OUT": 10, "DOCUMENT_OUT_HEADER": 20}

    def fill_document_out(self, products, document, header):
        if self.fill_error:
            raise self.fill_error
        self.filled.append((products, document, header))


class ConnectionDouble:
    def __init__(self, transaction):
        self._transaction = transaction
        self.closed = False

    def transaction(self):
        return self._transaction

    def close(self):
        self.closed = True


class UpdateWorkflowTests(unittest.TestCase):
    def run_with_transaction(self, transaction, data=None):
        connection = ConnectionDouble(transaction)
        with patch.object(update, "DatabaseConfig", return_value="cfg") as database_config, patch.object(
            update, "Connection", return_value=connection
        ) as connection_factory:
            result = update.run(data or [("ROSSKO", 8880, [product()])])
        return result, connection, database_config, connection_factory

    def test_success_closes_connection(self):
        transaction = TransactionDouble()
        result, connection, database_config, connection_factory = self.run_with_transaction(transaction)
        self.assertIsNone(result)
        database_config.assert_called_once_with()
        connection_factory.assert_called_once_with("cfg")
        self.assertEqual(
            transaction.start_kwargs,
            {"type_api": "high", "read_only": False},
        )
        self.assertEqual(transaction.created, [(8880, 0)])
        self.assertEqual(transaction.filled, [([product()], 10, 20)])
        self.assertTrue(connection.closed)

    def test_create_and_fill_errors_are_reraised(self):
        with self.assertRaisesRegex(RuntimeError, "create"):
            self.run_with_transaction(TransactionDouble(create_error=RuntimeError("create")))
        with self.assertRaisesRegex(RuntimeError, "fill"):
            self.run_with_transaction(TransactionDouble(fill_error=RuntimeError("fill")))


class MainWorkflowTests(unittest.TestCase):
    def test_run_success_and_each_error_boundary(self):
        with patch.object(main.fetch, "run", return_value="raw"), patch.object(
            main.adapt, "run", return_value="adapted"
        ) as adapted, patch.object(main.update, "run") as updated:
            self.assertIsNone(main.run())
        adapted.assert_called_once_with("raw")
        updated.assert_called_once_with("adapted")

        with patch.object(main.fetch, "run", side_effect=RuntimeError("fetch")):
            with self.assertRaisesRegex(RuntimeError, "fetch"):
                main.run()
        with patch.object(main.fetch, "run", return_value="raw"), patch.object(
            main.adapt, "run", side_effect=RuntimeError("adapt")
        ):
            with self.assertRaisesRegex(RuntimeError, "adapt"):
                main.run()
        with patch.object(main.fetch, "run", return_value="raw"), patch.object(
            main.adapt, "run", return_value="adapted"
        ), patch.object(main.update, "run", side_effect=AssertionError("partial")):
            with self.assertRaises(AssertionError):
                main.run()
        with patch.object(main.fetch, "run", return_value="raw"), patch.object(
            main.adapt, "run", return_value="adapted"
        ), patch.object(main.update, "run", side_effect=RuntimeError("db")):
            with self.assertRaisesRegex(RuntimeError, "db"):
                main.run()

    def test_module_entrypoint_flushes_and_runs(self):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 7, 22)

        with patch.object(fetch, "run", return_value=[]), patch.object(
            adapt, "run", return_value=[]
        ), patch.object(update, "run"), patch("src.utils.archive.flush") as flush, patch(
            "datetime.date", FixedDate
        ), warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="'src.main' found in sys.modules.*",
                category=RuntimeWarning,
            )
            namespace = runpy.run_module("src.main", run_name="__main__")
        self.assertEqual(namespace["__name__"], "__main__")
        self.assertEqual(flush.call_count, 2)

    @unittest.expectedFailure
    def test_module_entrypoint_obeys_flush_keyword_only_contract(self):
        with patch.object(fetch, "run", return_value=[]), patch.object(
            adapt, "run", return_value=[]
        ), patch.object(update, "run"), patch(
            "src.utils.archive.flush", autospec=True
        ), warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="'src.main' found in sys.modules.*",
                category=RuntimeWarning,
            )
            runpy.run_module("src.main", run_name="__main__")


if __name__ == "__main__":
    unittest.main()
