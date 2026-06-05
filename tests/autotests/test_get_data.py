import importlib
import sys
import types
import unittest
from datetime import date as real_date
from unittest.mock import patch

from utilities.dataobject import ProductList


def install_external_dependency_stubs():
    zeep_module = types.ModuleType("zeep")
    zeep_module.__path__ = []
    helpers_module = types.ModuleType("zeep.helpers")

    class DummyClient:
        pass

    zeep_module.Client = DummyClient
    helpers_module.serialize_object = lambda value: value
    zeep_module.helpers = helpers_module
    sys.modules.setdefault("zeep", zeep_module)
    sys.modules.setdefault("zeep.helpers", helpers_module)

    autodealer_module = types.ModuleType("autodealerAPI")
    autodealer_module.__path__ = []
    utils_module = types.ModuleType("autodealerAPI.utils")
    utils_module.__path__ = []
    functions_module = types.ModuleType("autodealerAPI.utils.functions")
    functions_module.__path__ = []
    standard_module = types.ModuleType("autodealerAPI.utils.functions.standard")
    standard_module.std = lambda value: value

    autodealer_module.utils = utils_module
    utils_module.functions = functions_module
    functions_module.standard = standard_module

    sys.modules.setdefault("autodealerAPI", autodealer_module)
    sys.modules.setdefault("autodealerAPI.utils", utils_module)
    sys.modules.setdefault("autodealerAPI.utils.functions", functions_module)
    sys.modules.setdefault("autodealerAPI.utils.functions.standard", standard_module)


def import_get_data_module():
    try:
        return importlib.import_module("back.get_data")
    except ModuleNotFoundError as exc:
        if exc.name != "zeep" and not exc.name.startswith("autodealerAPI"):
            raise

        install_external_dependency_stubs()
        sys.modules.pop("utilities.rosskoNprofit", None)
        sys.modules.pop("back.get_data", None)
        return importlib.import_module("back.get_data")


get_data = import_get_data_module()


def raw_rossko_products():
    return [
        {
            "created_date": "02.06.2026 10:30:00",
            "id": 1001,
            "parts": {
                "part": [
                    {
                        "guid": "guid-1",
                        "status": 31,
                        "name": "Brake Pad",
                        "brand": "Acme",
                        "partnumber": "BP-1",
                        "count": "2",
                        "price": "125.50",
                    },
                    {
                        "guid": "guid-skip",
                        "status": 36,
                        "name": "Oil Filter",
                        "brand": "Acme",
                        "partnumber": "OF-1",
                        "count": "1",
                        "price": "75.25",
                    },
                ]
            },
        }
    ]


def old_products_for_success():
    return ProductList(
        {
            "2026-06-01": {
                900: {"skipped-min-day": {"status": 5, "path": (99, 99)}},
            },
            "2026-06-02": {
                1001: {
                    "guid-1": {"status": 5, "path": (0, 0)},
                    "guid-skip": {"status": 31, "path": (0, 1)},
                }
            },
        }
    )


class GetDataTestCase(unittest.TestCase):
    def test_get_rossko_data_fetches_writes_reads_and_returns_changed_rows(self):
        raw_products = raw_rossko_products()
        captured = {}

        class FakeRosskoAPI:
            def __init__(self, *, url, key_1, key_2):
                captured["api_init"] = {"url": url, "key_1": key_1, "key_2": key_2}

            def get_orders(self, *, start, end):
                captured["get_orders"] = {"start": start, "end": end}
                return raw_products

        def fake_write_plist(product_list, path):
            captured["written_product_list"] = product_list
            captured["write_path"] = path

        def fake_read_plist(path):
            captured["read_path"] = path
            return old_products_for_success()

        def fake_day_of_week(delta_days=0):
            return "Yesterday" if delta_days == -1 else "Today"

        with patch.object(get_data, "RosskoAPI", FakeRosskoAPI), \
             patch.object(
                 get_data,
                 "cfg",
                 {"Rossko": {"URL": "https://rossko.test", "first_secret": "first", "second_secret": "second"}},
             ), \
             patch.object(get_data, "write_plist", fake_write_plist), \
             patch.object(get_data, "read_plist", fake_read_plist), \
             patch.object(get_data, "day_of_week", fake_day_of_week):
            agent_id, rows_iter = get_data.get_rossko_data(
                start_date=real_date(2026, 5, 1),
                end_date=real_date(2026, 6, 2),
            )

        self.assertEqual(captured["api_init"], {"url": "https://rossko.test", "key_1": "first", "key_2": "second"})
        self.assertEqual(captured["get_orders"], {"start": "2026-05-01", "end": "2026-06-02"})
        self.assertEqual(captured["write_path"].name, "Today.pkl")
        self.assertEqual(captured["read_path"].name, "Yesterday.pkl")
        self.assertEqual(captured["written_product_list"].data, ProductList.from_rossko(raw_products).data)
        self.assertEqual(agent_id, 8880)
        self.assertEqual(
            list(rows_iter),
            [
                {
                    "name": "Brake Pad",
                    "firm": "Acme",
                    "code": "BP-1",
                    "count": 2.0,
                    "price": 125.5,
                }
            ],
        )

    def test_get_rossko_data_raises_assertion_when_no_rows_pass_filter(self):
        class FakeRosskoAPI:
            def __init__(self, *, url, key_1, key_2):
                pass

            def get_orders(self, *, start, end):
                return raw_rossko_products()

        with patch.object(get_data, "RosskoAPI", FakeRosskoAPI), \
             patch.object(
                 get_data,
                 "cfg",
                 {"Rossko": {"URL": "https://rossko.test", "first_secret": "first", "second_secret": "second"}},
             ), \
             patch.object(get_data, "write_plist", lambda product_list, path: None), \
             patch.object(get_data, "read_plist", lambda path: ProductList()), \
             patch.object(get_data, "day_of_week", lambda delta_days=0: "Yesterday" if delta_days == -1 else "Today"):
            with self.assertRaises(AssertionError):
                get_data.get_rossko_data(real_date(2026, 5, 1), real_date(2026, 6, 2))

    def test_get_rossko_data_reraises_api_initialization_errors(self):
        class BrokenRosskoAPI:
            def __init__(self, *, url, key_1, key_2):
                raise RuntimeError("rossko init failed")

        with patch.object(get_data, "RosskoAPI", BrokenRosskoAPI), \
             patch.object(
                 get_data,
                 "cfg",
                 {"Rossko": {"URL": "https://rossko.test", "first_secret": "first", "second_secret": "second"}},
             ):
            with self.assertRaisesRegex(RuntimeError, "rossko init failed"):
                get_data.get_rossko_data(real_date(2026, 5, 1), real_date(2026, 6, 2))

    def test_main_requests_last_63_days_and_returns_rossko_result(self):
        class FixedDate(real_date):
            @classmethod
            def today(cls):
                return cls(2026, 6, 5)

        rossko_result = object()
        captured = {}

        def fake_get_rossko_data(*, start_date, end_date):
            captured["date_range"] = (start_date, end_date)
            return rossko_result

        with patch.object(get_data, "date", FixedDate), \
             patch.object(get_data, "get_rossko_data", fake_get_rossko_data):
            result = get_data.main()

        self.assertEqual(captured["date_range"], (real_date(2026, 4, 3), real_date(2026, 6, 5)))
        self.assertEqual(result, (rossko_result, None))


if __name__ == "__main__":
    unittest.main()
