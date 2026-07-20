import importlib
import sys
import types
import unittest
from datetime import date as real_date
from unittest.mock import Mock, mock_open, patch

from utilities.dataobject import ProductList


def install_external_dependency_stubs():
    zeep_module = types.ModuleType("zeep")
    helpers_module = types.ModuleType("zeep.helpers")
    zeep_module.Client = object
    helpers_module.serialize_object = lambda value: value
    zeep_module.helpers = helpers_module

    autodealer_module = types.ModuleType("autodealerAPI")
    utils_module = types.ModuleType("autodealerAPI.utils")
    functions_module = types.ModuleType("autodealerAPI.utils.functions")
    standard_module = types.ModuleType("autodealerAPI.utils.functions.standard")
    standard_module.std = lambda value: value
    autodealer_module.__path__ = []
    utils_module.__path__ = []
    functions_module.__path__ = []
    autodealer_module.utils = utils_module
    utils_module.functions = functions_module
    functions_module.standard = standard_module

    sys.modules.update({
        "zeep": zeep_module,
        "zeep.helpers": helpers_module,
        "autodealerAPI": autodealer_module,
        "autodealerAPI.utils": utils_module,
        "autodealerAPI.utils.functions": functions_module,
        "autodealerAPI.utils.functions.standard": standard_module,
    })


def import_get_data_module():
    install_external_dependency_stubs()
    sys.modules.pop("utilities.rosskoNprofit", None)
    sys.modules.pop("back.get_data", None)
    return importlib.import_module("back.get_data")


get_data = import_get_data_module()


def fake_day_of_week(delta_days=0, postfix=""):
    day = "Yesterday" if delta_days == -1 else "Today"
    return day + postfix


def raw_rossko_products():
    return [{
        "created_date": "02.06.2026 10:30:00",
        "id": 1001,
        "parts": {"part": [
            {
                "guid": "guid-1", "status": 31, "comment": "client",
                "name": "Brake Pad", "brand": "Acme", "partnumber": "BP-1",
                "count": "2", "price": "125.50",
            },
            {
                "guid": "guid-skip", "status": 36,
                "name": "Oil Filter", "brand": "Acme", "partnumber": "OF-1",
                "count": "1", "price": "75.25",
            },
        ]},
    }]


def raw_profit_products():
    return [{
        "datetime": "2026-06-02 10:30:00",
        "order_id": 2001,
        "products": [{
            "article_id": "article-1", "status_id": 20, "comment": "client",
            "description": "Brake Disc", "brand": "ProfitBrand", "article": "BD-1",
            "quantity": "3", "price": "250.75",
        }],
    }]


def old_products(agent, day, order, records):
    product_list = ProductList({
        "2026-06-01": {1: {"skip": [(1, (99, 99), None)]}},
        day: {order: records},
    })
    product_list.agent_name = agent
    return product_list


class GetDataTestCase(unittest.TestCase):
    def setUp(self):
        self.logger = Mock()
        self.open_mock = mock_open()
        self.day_patch = patch.object(get_data, "day_of_week", fake_day_of_week)
        self.open_patch = patch("builtins.open", self.open_mock)
        self.dump_patch = patch.object(get_data.json, "dump")
        self.day_patch.start()
        self.open_patch.start()
        self.json_dump = self.dump_patch.start()
        self.addCleanup(self.day_patch.stop)
        self.addCleanup(self.open_patch.stop)
        self.addCleanup(self.dump_patch.stop)

    def test_get_rossko_data_builds_rows_and_skips_31_to_36(self):
        raw = raw_rossko_products()
        api = Mock()
        api.get_orders.return_value = raw
        old = old_products(
            "ROSSKO", "2026-06-02", 1001,
            {"guid-1": [(5, (0, 0), "client")], "guid-skip": [(31, (0, 1), None)]},
        )

        with patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
             patch.object(get_data, "RosskoAPI", return_value=api) as api_class, \
             patch.object(get_data, "write_plist") as write_mock, \
             patch.object(get_data, "read_plist", return_value=old) as read_mock:
            result = get_data.get_rossko_data(real_date(2026, 5, 1), real_date(2026, 6, 2))

        agent_id, rows = result
        self.assertEqual(agent_id, 8880)
        self.assertEqual(list(rows), [{
            "name": "Brake Pad", "firm": "Acme", "code": "BP-1",
            "count": 2.0, "price": 125.5,
        }])
        api_class.assert_called_once_with(
            url=get_data.cfg["Rossko"]["URL"],
            key_1=get_data.cfg["Rossko"]["first_secret"],
            key_2=get_data.cfg["Rossko"]["second_secret"],
        )
        api.get_orders.assert_called_once_with(start="2026-05-01", end="2026-06-02")
        self.json_dump.assert_called_once_with(raw, self.open_mock(), ensure_ascii=False, indent=4)
        self.assertEqual(write_mock.call_args.args[1].name, "Today_rossko.pkl")
        self.assertEqual(read_mock.call_args.args[0].name, "Yesterday_rossko.pkl")

    def test_get_profit_data_builds_rows(self):
        raw = raw_profit_products()
        api = Mock()
        api.get_orders.return_value = raw
        old = old_products(
            "PROFIT", "2026-06-02", 2001,
            {"article-1": [(5, (0, 0), "client")]},
        )

        with patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
             patch.object(get_data, "ProfitLigaAPI", return_value=api) as api_class, \
             patch.object(get_data, "write_plist") as write_mock, \
             patch.object(get_data, "read_plist", return_value=old) as read_mock:
            result = get_data.get_profit_data(real_date(2026, 5, 1), real_date(2026, 6, 2))

        agent_id, rows = result
        self.assertEqual(agent_id, 8876)
        self.assertEqual(list(rows), [{
            "name": "Brake Disc", "firm": "ProfitBrand", "code": "BD-1",
            "count": 3.0, "price": 250.75,
        }])
        api_class.assert_called_once_with(
            url=get_data.cfg["Profit"]["URL"], api_key=get_data.cfg["Profit"]["key"],
            start="2026-05-01", end="2026-06-02",
        )
        api.get_orders.assert_called_once_with()
        self.assertEqual(write_mock.call_args.args[1].name, "Today_profit.pkl")
        self.assertEqual(read_mock.call_args.args[0].name, "Yesterday_profit.pkl")

    def test_sources_return_none_when_previous_snapshot_is_missing(self):
        rossko_api = Mock()
        rossko_api.get_orders.return_value = raw_rossko_products()
        profit_api = Mock()
        profit_api.get_orders.return_value = raw_profit_products()

        for function, api_name, api in (
            (get_data.get_rossko_data, "RosskoAPI", rossko_api),
            (get_data.get_profit_data, "ProfitLigaAPI", profit_api),
        ):
            with self.subTest(function=function.__name__), \
                 patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
                 patch.object(get_data, api_name, return_value=api), \
                 patch.object(get_data, "write_plist"), \
                 patch.object(get_data, "read_plist", side_effect=FileNotFoundError):
                self.assertIsNone(function(real_date(2026, 5, 1), real_date(2026, 6, 2)))

    def test_sources_return_none_when_difference_is_empty(self):
        class EmptyProductList:
            def difference(self, old, *, allow_statuses):
                return iter(())

        cases = (
            (get_data.get_rossko_data, "RosskoAPI", "from_rossko", raw_rossko_products()),
            (get_data.get_profit_data, "ProfitLigaAPI", "from_profit", raw_profit_products()),
        )
        for function, api_name, constructor, raw in cases:
            api = Mock()
            api.get_orders.return_value = raw
            with self.subTest(function=function.__name__), \
                 patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
                 patch.object(get_data, api_name, return_value=api), \
                 patch.object(get_data.ProductList, constructor, return_value=EmptyProductList()), \
                 patch.object(get_data, "write_plist"), \
                 patch.object(get_data, "read_plist", return_value=object()):
                self.assertIsNone(function(real_date(2026, 5, 1), real_date(2026, 6, 2)))

    def test_sources_reraise_initialization_and_collection_errors(self):
        cases = (
            (get_data.get_rossko_data, "RosskoAPI"),
            (get_data.get_profit_data, "ProfitLigaAPI"),
        )
        for function, api_name in cases:
            with self.subTest(source=api_name, stage="init"), \
                 patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
                 patch.object(get_data, api_name, side_effect=RuntimeError("init failed")):
                with self.assertRaisesRegex(RuntimeError, "init failed"):
                    function(real_date(2026, 5, 1), real_date(2026, 6, 2))

            api = Mock()
            api.get_orders.side_effect = RuntimeError("request failed")
            with self.subTest(source=api_name, stage="request"), \
                 patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
                 patch.object(get_data, api_name, return_value=api):
                with self.assertRaisesRegex(RuntimeError, "request failed"):
                    function(real_date(2026, 5, 1), real_date(2026, 6, 2))

    def test_rossko_validates_date_order_and_guid_from_difference(self):
        cases = (
            (("2026-06-03", 1001, "guid-1", (5, 31), (0, 0)), "Дата"),
            (("2026-06-02", 9999, "guid-1", (5, 31), (0, 0)), "ID"),
            (("2026-06-02", 1001, "wrong-guid", (5, 31), (0, 0)), "ID"),
        )
        for item, message in cases:
            with self.subTest(item=item):
                self._assert_validation_error(
                    function=get_data.get_rossko_data,
                    api_name="RosskoAPI",
                    constructor="from_rossko",
                    raw=raw_rossko_products(),
                    difference_item=item,
                    message=message,
                )

    def test_profit_validates_date_order_and_guid_from_difference(self):
        cases = (
            (("2026-06-03", 2001, "article-1", (5, 20), (0, 0)), "Дата"),
            (("2026-06-02", 9999, "article-1", (5, 20), (0, 0)), "ID"),
            (("2026-06-02", 2001, "wrong-guid", (5, 20), (0, 0)), "ID"),
        )
        for item, message in cases:
            with self.subTest(item=item):
                self._assert_validation_error(
                    function=get_data.get_profit_data,
                    api_name="ProfitLigaAPI",
                    constructor="from_profit",
                    raw=raw_profit_products(),
                    difference_item=item,
                    message=message,
                )

    def test_main_requests_previous_63_days_from_both_sources(self):
        class FixedDate(real_date):
            @classmethod
            def today(cls):
                return cls(2026, 6, 5)

        rossko_result = object()
        profit_result = object()
        with patch.object(get_data, "date", FixedDate), \
             patch.object(get_data, "get_rossko_data", return_value=rossko_result) as rossko_mock, \
             patch.object(get_data, "get_profit_data", return_value=profit_result) as profit_mock, \
             patch.object(get_data, "GET_DATA_LOGGER", self.logger):
            result = get_data.main()

        expected = {"start_date": real_date(2026, 4, 2), "end_date": real_date(2026, 6, 4)}
        rossko_mock.assert_called_once_with(**expected)
        profit_mock.assert_called_once_with(**expected)
        self.assertEqual(result, (rossko_result, profit_result))

    def _assert_validation_error(self, *, function, api_name, constructor, raw, difference_item, message):
        api = Mock()
        api.get_orders.return_value = raw
        fake_product_list = Mock()
        fake_product_list.difference.return_value = iter((difference_item,))

        with patch.object(get_data, "GET_DATA_LOGGER", self.logger), \
             patch.object(get_data, api_name, return_value=api), \
             patch.object(get_data.ProductList, constructor, return_value=fake_product_list), \
             patch.object(get_data, "write_plist"), \
             patch.object(get_data, "read_plist", return_value=object()):
            with self.assertRaisesRegex(ValueError, message):
                function(real_date(2026, 5, 1), real_date(2026, 6, 2))


if __name__ == "__main__":
    unittest.main()
