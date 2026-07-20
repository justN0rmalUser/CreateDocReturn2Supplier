import pickle
import tempfile
import unittest
from pathlib import Path

import pydantic

from utilities.dataobject import ProductList, read_plist, write_plist


def plist_payload(day="2026-06-02", order=1001, guid="guid-1", status=31, path=(0, 0), comment=None):
    return {
        day: {
            order: {
                guid: [(status, path, comment)],
            }
        }
    }


def rossko_product_list(data):
    product_list = ProductList(data)
    product_list.agent_name = "ROSSKO"
    return product_list


class ProductListTestCase(unittest.TestCase):
    def test_empty_product_list_has_no_date_bounds(self):
        plist = ProductList()

        self.assertEqual(plist.data, {})
        self.assertIsNone(plist.min_day)
        self.assertIsNone(plist.max_day)
        self.assertEqual(list(plist.products), [])

    def test_init_validates_date_keys(self):
        with self.assertRaises(pydantic.ValidationError):
            ProductList(plist_payload(day="2026-02-31"))

    def test_from_rossko_builds_nested_data_and_keeps_duplicate_guids(self):
        raw_products = [
            {
                "created_date": "02.06.2026 10:15:00",
                "id": "1001",
                "parts": {
                    "part": [
                        {"guid": "same-guid", "status": "31"},
                        {"guid": "same-guid", "status": 5},
                    ]
                },
            },
            {
                "created_date": "03.06.2026 09:00:00",
                "id": 1002,
                "parts": {
                    "part": [
                        {"guid": "guid-3", "status": "36"},
                    ]
                },
            },
        ]

        plist = ProductList.from_rossko(raw_products)

        self.assertEqual(plist.min_day, "2026-06-02")
        self.assertEqual(plist.max_day, "2026-06-03")
        self.assertEqual(
            list(plist.products),
            [
                ("2026-06-02", 1001, "same-guid", 31, (0, 0), None),
                ("2026-06-02", 1001, "same-guid", 5, (0, 1), None),
                ("2026-06-03", 1002, "guid-3", 36, (1, 0), None),
            ],
        )

    def test_add_appends_existing_guid(self):
        plist = ProductList(plist_payload(status=5, path=(0, 0)))

        plist.add(plist_payload(status=31, path=(2, 3)))
        plist.add(ProductList(plist_payload(day="2026-06-03", order=1002, guid="guid-2", status=36)))

        self.assertEqual(plist.data["2026-06-02"][1001]["guid-1"], [(5, (0, 0), None), (31, (2, 3), None)])
        self.assertEqual(plist.data["2026-06-03"][1002]["guid-2"], [(36, (0, 0), None)])

    def test_difference_yields_only_changed_allowed_statuses_after_min_old_day(self):
        old_products = rossko_product_list(
            {
                "2026-06-01": {
                    900: {"skipped-min-day": [(5, (0, 0), None)]},
                },
                "2026-06-02": {
                    1001: {
                        "changed": [(5, (0, 0), None)],
                        "not-allowed": [(5, (0, 1), None)],
                        "same": [(31, (0, 2), None)],
                    }
                },
            }
        )
        new_products = rossko_product_list(
            {
                "2026-06-02": {
                    1001: {
                        "changed": [(31, (2, 0), None)],
                        "not-allowed": [(9, (2, 1), None)],
                        "same": [(31, (2, 2), None)],
                    }
                }
            }
        )

        diff = list(new_products.difference(old_products, allow_statuses=(31, 36)))

        self.assertEqual(diff, [("2026-06-02", 1001, "changed", (5, 31), (2, 0))])

    def test_difference_links_appended_partial_return_to_old_product(self):
        old_products = rossko_product_list({
            "2026-06-01": {900: {"skip": [(31, (0, 0), None)]}},
            "2026-06-02": {1001: {"same-guid": [(2, (0, 0), "client")]}},
        })
        new_products = rossko_product_list({
            "2026-06-02": {
                1001: {
                    "same-guid": [
                        (2, (2, 4), "client"),
                        (31, (2, 5), "client"),
                    ]
                }
            }
        })

        self.assertEqual(
            list(new_products.difference(old_products, allow_statuses=(31, 36))),
            [("2026-06-02", 1001, "same-guid", (2, 31), (2, 5))],
        )

    def test_difference_links_partial_return_inserted_between_existing_products(self):
        old_products = rossko_product_list({
            "2026-06-01": {900: {"skip": [(31, (0, 0), None)]}},
            "2026-06-02": {
                1001: {"same-guid": [(2, (0, 0), "first"), (2, (0, 1), "second")]}
            },
        })
        new_products = rossko_product_list({
            "2026-06-02": {
                1001: {
                    "same-guid": [
                        (2, (2, 4), "first"),
                        (36, (2, 5), "first"),
                        (2, (2, 6), "second"),
                    ]
                }
            }
        })

        self.assertEqual(
            list(new_products.difference(old_products, allow_statuses=(31, 36))),
            [("2026-06-02", 1001, "same-guid", (2, 36), (2, 5))],
        )

    def test_difference_validates_inputs_dates_statuses_and_guid_identity(self):
        current = rossko_product_list(plist_payload(day="2026-06-01"))
        newer_old_products = rossko_product_list(plist_payload(day="2026-06-02"))
        mismatched_guid_current = rossko_product_list(plist_payload(day="2026-06-02", guid="new-guid"))
        mismatched_guid_old = rossko_product_list(
            {
                "2026-06-01": {900: {"skipped-min-day": [(5, (0, 0), None)]}},
                "2026-06-02": {1001: {"old-guid": [(5, (0, 0), None)]}},
            }
        )

        with self.assertRaises(TypeError):
            list(current.difference({}, allow_statuses=(31,)))

        with self.assertRaises(TypeError):
            list(current.difference(ProductList(), allow_statuses=[31]))

        with self.assertRaises(ValueError):
            empty = ProductList()
            empty.agent_name = "ROSSKO"
            list(current.difference(empty, allow_statuses=()))

        with self.assertRaises(ValueError):
            empty = ProductList()
            empty.agent_name = "ROSSKO"
            list(current.difference(empty, allow_statuses=(4,)))

        with self.assertRaises(ValueError):
            list(current.difference(newer_old_products, allow_statuses=(31,)))

        with self.assertRaises(KeyError):
            list(mismatched_guid_current.difference(mismatched_guid_old, allow_statuses=(31,)))

    def test_write_and_read_plist_roundtrip_and_validate_paths(self):
        plist = ProductList(plist_payload())

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            target = tmp_path / "products.pkl"
            wrong_suffix = tmp_path / "products.txt"
            non_product_pickle = tmp_path / "not_product.pkl"
            wrong_suffix.write_text("", encoding="utf-8")

            write_plist(plist, target)
            restored = read_plist(target)

            self.assertIsInstance(restored, ProductList)
            self.assertEqual(restored.data, plist.data)

            with self.assertRaises(TypeError):
                write_plist({}, target)

            with self.assertRaises(ValueError):
                write_plist(plist, wrong_suffix)

            with self.assertRaises(TypeError):
                read_plist(123)

            with self.assertRaises(FileNotFoundError):
                read_plist(tmp_path / "missing.pkl")

            with self.assertRaises(ValueError):
                read_plist(wrong_suffix)

            with non_product_pickle.open("wb") as fpkl:
                pickle.dump({"not": "ProductList"}, fpkl)

            with self.assertRaises(TypeError):
                read_plist(non_product_pickle)

    def test_read_and_write_reject_legacy_product_data(self):
        legacy = ProductList()
        legacy._data = {
            "2026-06-02": {1001: {0: ("guid-1", 31, (0, 0))}}
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "legacy.pkl"

            with self.assertRaises(pydantic.ValidationError):
                write_plist(legacy, path)

            with path.open("wb") as fpkl:
                pickle.dump(legacy, fpkl)

            with self.assertRaises(pydantic.ValidationError):
                read_plist(path)

if __name__ == "__main__":
    unittest.main()
