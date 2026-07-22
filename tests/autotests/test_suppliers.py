import os
import unittest
from datetime import date
from unittest.mock import Mock, call, patch

import requests

os.environ.setdefault("path_to_config", "config.toml")

from src.fetch.supplier_pattern import Supplier
from src.fetch.suppliers import profit as profit_module
from src.fetch.suppliers.profit import ProfitLigaAPI
from src.fetch.suppliers.rossko import RosskoAPI


def profit_row(day):
    return {"datetime": f"{day} 10:00:00"}


class SupplierPatternTests(unittest.TestCase):
    def test_abstract_method_body(self):
        self.assertIsNone(Supplier.pull_data(object(), "2026-01-01", "2026-01-02"))


class ProfitTests(unittest.TestCase):
    def setUp(self):
        self.api = ProfitLigaAPI("https://profit.test", "secret")

    @unittest.expectedFailure
    def test_default_api_key_uses_configured_key(self):
        api = ProfitLigaAPI()
        self.assertEqual(api.api_key, profit_module.cfg["Suppliers"]["profit"]["key"])

    @patch("src.fetch.suppliers.profit.sleep")
    @patch("src.fetch.suppliers.profit.requests.get")
    def test_make_request_success_variants(self, get, sleep):
        response = Mock()
        response.json.return_value = {
            "status": "success", "pageSize": 2, "data": [{"id": 1}], "pages": 4,
        }
        get.return_value = response

        self.assertEqual(self.api._make_request(1), (2, [{"id": 1}]))
        self.assertEqual(self.api._make_request(2, with_pages=True), (2, [{"id": 1}], 4))
        get.assert_called_with("https://profit.test", params={"secret": "secret", "page": 2})
        self.assertEqual(sleep.call_count, 2)

    @patch("src.fetch.suppliers.profit.requests.get")
    def test_make_request_errors(self, get):
        get.side_effect = requests.RequestException("offline")
        with self.assertRaisesRegex(requests.RequestException, "Profit Liga"):
            self.api._make_request(1)

        response = Mock()
        response.json.return_value = {"status": "error"}
        get.side_effect = None
        get.return_value = response
        with patch("src.fetch.suppliers.profit.sleep"):
            with self.assertRaisesRegex(RuntimeError, "error"):
                self.api._make_request(1)

    def test_validate_list_all_subset_and_empty(self):
        page = [profit_row("2026-06-05"), profit_row("2026-06-04"), profit_row("2026-06-03")]
        self.assertIs(self.api.validate_list(page, "2026-06-03", "2026-06-05"), page)
        self.assertEqual(
            self.api.validate_list(page, "2026-06-04", "2026-06-04"),
            [profit_row("2026-06-04")],
        )
        self.assertEqual(
            self.api.validate_list(page, "2026-06-03", "2026-06-04"),
            [profit_row("2026-06-04"), profit_row("2026-06-03")],
        )
        self.assertEqual(self.api.validate_list(page, "2026-07-01", "2026-07-02"), [])

    def test_pull_data_collects_pages_and_stops(self):
        pages = {
            (1, True): (1, [profit_row("2026-06-05")], 4),
            (2, False): (1, [profit_row("2026-06-04")]),
            (3, False): (1, [profit_row("2026-01-01")]),
        }
        with patch.object(self.api, "_make_request", side_effect=lambda page, with_pages=False: pages[(page, with_pages)]):
            result = self.api.pull_data("2026-06-03", "2026-06-05")
        self.assertEqual(result, [profit_row("2026-06-05"), profit_row("2026-06-04")])

        pages[(1, True)] = (1, [profit_row("2026-01-01")], 3)
        pages[(2, False)] = (1, [profit_row("2026-06-04")])
        with patch.object(self.api, "_make_request", side_effect=lambda page, with_pages=False: pages[(page, with_pages)]):
            self.assertEqual(self.api.pull_data("2026-06-03", "2026-06-05"), [profit_row("2026-06-04")])

    @unittest.expectedFailure
    def test_pull_data_includes_last_reported_page(self):
        pages = {
            (1, True): (1, [profit_row("2026-06-05")], 3),
            (2, False): (1, [profit_row("2026-06-04")]),
            (3, False): (1, [profit_row("2026-06-03")]),
        }
        with patch.object(
            self.api,
            "_make_request",
            side_effect=lambda page, with_pages=False: pages[(page, with_pages)],
        ):
            result = self.api.pull_data("2026-06-03", "2026-06-05")
        self.assertEqual(
            result,
            [profit_row("2026-06-05"), profit_row("2026-06-04"), profit_row("2026-06-03")],
        )


class RosskoTests(unittest.TestCase):
    def setUp(self):
        self.api = RosskoAPI("https://rossko.test", "one", "two")

    def test_fetch_validates_range_and_response_errors(self):
        with self.assertRaisesRegex(ValueError, "32"):
            self.api._fetch_orders_for_date("2026-01-01", "2026-02-02")

        client = Mock()
        with patch("src.fetch.suppliers.rossko.Client", return_value=client), patch(
            "src.fetch.suppliers.rossko.serialize_object", return_value={"success": False, "message": "boom"}
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                self.api._fetch_orders_for_date("2026-01-01", "2026-01-02")

        with patch("src.fetch.suppliers.rossko.Client", return_value=client), patch(
            "src.fetch.suppliers.rossko.serialize_object", return_value={"success": False, "message": "Ничего не найдено"}
        ):
            with self.assertRaisesRegex(AssertionError, "Ничего"):
                self.api._fetch_orders_for_date("2026-01-01", "2026-01-02")

    def test_fetch_returns_list_for_list_and_single_order(self):
        for order, expected in [([{"id": 1}], [{"id": 1}]), ({"id": 2}, [{"id": 2}])]:
            client = Mock()
            with self.subTest(order=order), patch(
                "src.fetch.suppliers.rossko.Client", return_value=client
            ) as client_factory, patch(
                "src.fetch.suppliers.rossko.serialize_object",
                return_value={"success": True, "OrdersList": {"Order": order}},
            ):
                self.assertEqual(
                    self.api._fetch_orders_for_date("2026-01-01", "2026-01-02"), expected
                )
            client_factory.assert_called_once_with("https://rossko.test")
            client.service.GetOrders.assert_called_once_with(
                KEY1="one",
                KEY2="two",
                start_date="2026-01-01",
                end_date="2026-01-02",
                limit=500,
            )

    def test_pull_data_direct_and_split_paths(self):
        with patch.object(self.api, "_fetch_orders_for_date", return_value=[{"id": 1}]):
            self.assertEqual(self.api.pull_data("2026-01-01", "2026-01-02"), [{"id": 1}])

        self.api.get_orders = Mock(side_effect=[[{"id": 1}], [{"id": 2}]])
        with patch.object(self.api, "_fetch_orders_for_date", return_value=[{}] * 495):
            result = self.api.pull_data("2026-01-01", "2026-01-04")
        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(
            self.api.get_orders.call_args_list,
            [
                call("2026-01-01", "2026-01-02"),
                call("2026-01-03", "2026-01-04"),
            ],
        )

        self.api.get_orders = Mock(side_effect=[[{"id": 3}], [{"id": 4}]])
        with patch.object(self.api, "_fetch_orders_for_date", side_effect=ValueError("split")):
            result = self.api.pull_data(date(2026, 1, 1), date(2026, 1, 4))
        self.assertEqual(result, [{"id": 3}, {"id": 4}])

    @unittest.expectedFailure
    def test_pull_data_splits_using_implemented_fetch_method(self):
        with patch.object(
            self.api,
            "_fetch_orders_for_date",
            side_effect=[[{}] * 495, [{"id": 1}], [{"id": 2}]],
        ):
            result = self.api.pull_data("2026-01-01", "2026-01-04")
        self.assertEqual(result, [{"id": 1}, {"id": 2}])


if __name__ == "__main__":
    unittest.main()
