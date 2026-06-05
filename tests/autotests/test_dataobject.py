import tempfile
import unittest
from pathlib import Path

import pydantic

from utilities.dataobject import ProductList, read_plist, write_plist


def plist_payload(day="2026-06-02", order=1001, guid="guid-1", status=31, path=(0, 0)):
    return {
        day: {
            order: {
                guid: {
                    "status": status,
                    "path": path,
                }
            }
        }
    }


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

    def test_from_rossko_builds_nested_data_and_paths(self):
        raw_products = [
            {
                "created_date": "02.06.2026 10:15:00",
                "id": "1001",
                "parts": {
                    "part": [
                        {"guid": "guid-1", "status": "31"},
                        {"guid": "guid-2", "status": 5},
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
                ("2026-06-02", 1001, "guid-1", 31, (0, 0)),
                ("2026-06-02", 1001, "guid-2", 5, (0, 1)),
                ("2026-06-03", 1002, "guid-3", 36, (1, 0)),
            ],
        )

    def test_add_merges_and_overwrites_existing_guid(self):
        plist = ProductList(plist_payload(status=5, path=(0, 0)))

        plist.add(plist_payload(status=31, path=(2, 3)))
        plist.add(ProductList(plist_payload(day="2026-06-03", order=1002, guid="guid-2", status=36)))

        self.assertEqual(plist.data["2026-06-02"][1001]["guid-1"], {"status": 31, "path": (2, 3)})
        self.assertEqual(plist.data["2026-06-03"][1002]["guid-2"], {"status": 36, "path": (0, 0)})

    def test_difference_yields_only_changed_allowed_statuses_after_min_old_day(self):
        old_products = ProductList(
            {
                "2026-06-01": {
                    900: {"skipped-min-day": {"status": 5, "path": (0, 0)}},
                },
                "2026-06-02": {
                    1001: {
                        "changed": {"status": 5, "path": (0, 0)},
                        "not-allowed": {"status": 5, "path": (0, 1)},
                        "same": {"status": 31, "path": (0, 2)},
                    }
                },
            }
        )
        new_products = ProductList(
            {
                "2026-06-02": {
                    1001: {
                        "changed": {"status": 31, "path": (2, 0)},
                        "not-allowed": {"status": 9, "path": (2, 1)},
                        "same": {"status": 31, "path": (2, 2)},
                    }
                }
            }
        )

        diff = list(new_products.difference(old_products, allow_statuses=(31, 36)))

        self.assertEqual(diff, [("2026-06-02", 1001, "changed", (5, 31), (2, 0))])

    def test_difference_validates_inputs_dates_and_allowed_statuses(self):
        current = ProductList(plist_payload(day="2026-06-01"))
        newer_old_products = ProductList(plist_payload(day="2026-06-02"))

        with self.assertRaises(TypeError):
            list(current.difference({}, allow_statuses=(31,)))

        with self.assertRaises(TypeError):
            list(current.difference(ProductList(), allow_statuses=[31]))

        with self.assertRaises(ValueError):
            list(current.difference(ProductList(), allow_statuses=()))

        with self.assertRaises(ValueError):
            list(current.difference(ProductList(), allow_statuses=(4,)))

        with self.assertRaises(ValueError):
            list(current.difference(newer_old_products, allow_statuses=(31,)))

    def test_write_and_read_plist_roundtrip_and_validate_paths(self):
        plist = ProductList(plist_payload())

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            target = tmp_path / "products.pkl"
            wrong_suffix = tmp_path / "products.txt"
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


if __name__ == "__main__":
    unittest.main()
