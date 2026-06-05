import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


def install_external_dependency_stubs():
    zeep_module = types.ModuleType("zeep")
    helpers_module = types.ModuleType("zeep.helpers")

    class DummyClient:
        pass

    zeep_module.Client = DummyClient
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

    sys.modules["zeep"] = zeep_module
    sys.modules["zeep.helpers"] = helpers_module
    sys.modules["autodealerAPI"] = autodealer_module
    sys.modules["autodealerAPI.utils"] = utils_module
    sys.modules["autodealerAPI.utils.functions"] = functions_module
    sys.modules["autodealerAPI.utils.functions.standard"] = standard_module


def import_rossko_module():
    install_external_dependency_stubs()
    sys.modules.pop("utilities.rosskoNprofit", None)
    return importlib.import_module("utilities.rosskoNprofit")


rossko_module = import_rossko_module()


class RosskoAPITestCase(unittest.TestCase):
    def setUp(self):
        self.api = rossko_module.RosskoAPI(url="https://rossko.test/wsdl", key_1="first", key_2="second")
        self.logger = Mock()
        self.logger.info = Mock()

    def test_init_stores_connection_settings_and_cache(self):
        self.assertEqual(self.api.url, "https://rossko.test/wsdl")
        self.assertEqual(self.api.key_1, "first")
        self.assertEqual(self.api.key_2, "second")
        self.assertEqual(self.api._cache, [])

    def test_fetch_orders_for_date_rejects_ranges_of_32_days_or_more_before_request(self):
        with patch.object(rossko_module, "Client") as client_mock:
            with self.assertRaises(ValueError):
                self.api._fetch_orders_for_date("2026-01-01", "2026-02-02")

        client_mock.assert_not_called()

    def test_fetch_orders_for_date_returns_list_orders_and_calls_soap_with_credentials(self):
        raw_response = object()
        orders = [{"id": 1}, {"id": 2}]
        get_orders_call = Mock(return_value=raw_response)
        fake_client = types.SimpleNamespace(service=types.SimpleNamespace(GetOrders=get_orders_call))
        client_constructor = Mock(return_value=fake_client)

        with patch.object(rossko_module, "GET_DATA_LOGGER", self.logger), \
             patch.object(rossko_module, "Client", client_constructor), \
             patch.object(
                 rossko_module,
                 "serialize_object",
                 Mock(return_value={"success": True, "message": None, "OrdersList": {"Order": orders}}),
             ):
            result = self.api._fetch_orders_for_date("2026-01-01", "2026-01-31")

        self.assertEqual(result, orders)
        client_constructor.assert_called_once_with("https://rossko.test/wsdl")
        get_orders_call.assert_called_once_with(
            KEY1="first",
            KEY2="second",
            start_date="2026-01-01",
            end_date="2026-01-31",
            limit=500,
        )
        self.assertEqual(self.logger.info.call_count, 2)

    def test_fetch_orders_for_date_wraps_single_order_in_list(self):
        single_order = {"id": 1}

        with patch.object(rossko_module, "GET_DATA_LOGGER", self.logger), \
             patch.object(rossko_module, "Client", self._client_returning(object())), \
             patch.object(
                 rossko_module,
                 "serialize_object",
                 Mock(return_value={"success": True, "message": None, "OrdersList": {"Order": single_order}}),
             ):
            result = self.api._fetch_orders_for_date("2026-01-01", "2026-01-01")

        self.assertEqual(result, [single_order])

    def test_fetch_orders_for_date_returns_empty_list_when_response_has_no_orders(self):
        with patch.object(rossko_module, "GET_DATA_LOGGER", self.logger), \
             patch.object(rossko_module, "Client", self._client_returning(object())), \
             patch.object(
                 rossko_module,
                 "serialize_object",
                 Mock(return_value={"success": True, "message": None}),
             ):
            result = self.api._fetch_orders_for_date("2026-01-01", "2026-01-01")

        self.assertEqual(result, [])

    def test_fetch_orders_for_date_raises_assertion_for_not_found_response(self):
        not_found_message = "Ничего не найдено"

        with patch.object(rossko_module, "GET_DATA_LOGGER", self.logger), \
             patch.object(rossko_module, "Client", self._client_returning(object())), \
             patch.object(
                 rossko_module,
                 "serialize_object",
                 Mock(return_value={"success": False, "message": not_found_message}),
             ):
            with self.assertRaises(AssertionError):
                self.api._fetch_orders_for_date("2026-01-01", "2026-01-01")

    def test_fetch_orders_for_date_raises_runtime_error_for_failed_response(self):
        with patch.object(rossko_module, "GET_DATA_LOGGER", self.logger), \
             patch.object(rossko_module, "Client", self._client_returning(object())), \
             patch.object(
                 rossko_module,
                 "serialize_object",
                 Mock(return_value={"success": False, "message": "bad credentials"}),
             ):
            with self.assertRaisesRegex(RuntimeError, "bad credentials"):
                self.api._fetch_orders_for_date("2026-01-01", "2026-01-01")

    def test_get_orders_returns_direct_fetch_result(self):
        self.api._fetch_orders_for_date = Mock(return_value=[{"id": 1}])

        result = self.api.get_orders("2026-01-01", "2026-01-31")

        self.assertEqual(result, [{"id": 1}])
        self.api._fetch_orders_for_date.assert_called_once_with("2026-01-01", "2026-01-31")

    def test_get_orders_does_not_split_500_orders_for_single_day(self):
        orders = [{"id": idx} for idx in range(500)]
        self.api._fetch_orders_for_date = Mock(return_value=orders)

        result = self.api.get_orders("2026-01-01", "2026-01-01")

        self.assertEqual(result, orders)

    def test_get_orders_splits_when_fetch_raises_value_error(self):
        self.api._fetch_orders_for_date = Mock(
            side_effect=[
                ValueError("range too large"),
                [{"id": "first-half"}],
                [{"id": "second-half"}],
            ]
        )

        with patch.object(
            rossko_module,
            "split_iso_date_range",
            Mock(return_value=(("2026-01-01", "2026-01-16"), ("2026-01-17", "2026-01-31"))),
        ) as split_mock:
            result = self.api.get_orders("2026-01-01", "2026-01-31")

        self.assertEqual(result, [{"id": "first-half"}, {"id": "second-half"}])
        split_mock.assert_called_once_with("2026-01-01", "2026-01-31")
        self.assertEqual(
            self.api._fetch_orders_for_date.call_args_list,
            [
                unittest.mock.call("2026-01-01", "2026-01-31"),
                unittest.mock.call("2026-01-01", "2026-01-16"),
                unittest.mock.call("2026-01-17", "2026-01-31"),
            ],
        )

    def test_get_orders_splits_when_500_orders_return_for_date_range(self):
        full_page = [{"id": idx} for idx in range(500)]
        self.api._fetch_orders_for_date = Mock(
            side_effect=[
                full_page,
                [{"id": "first-half"}],
                [{"id": "second-half"}],
            ]
        )

        with patch.object(
            rossko_module,
            "split_iso_date_range",
            Mock(return_value=(("2026-01-01", "2026-01-16"), ("2026-01-17", "2026-01-31"))),
        ) as split_mock:
            result = self.api.get_orders("2026-01-01", "2026-01-31")

        self.assertEqual(result, [{"id": "first-half"}, {"id": "second-half"}])
        split_mock.assert_called_once_with("2026-01-01", "2026-01-31")

    @staticmethod
    def _client_returning(raw_response):
        get_orders_call = Mock(return_value=raw_response)
        fake_client = types.SimpleNamespace(service=types.SimpleNamespace(GetOrders=get_orders_call))
        return Mock(return_value=fake_client)


if __name__ == "__main__":
    unittest.main()
