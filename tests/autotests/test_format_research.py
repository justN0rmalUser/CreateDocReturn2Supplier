import pickle
import os
import logging
import tempfile
import unittest
from pathlib import Path

import pydantic

os.environ.setdefault("path_to_config", "config.toml")
logging.getLogger("dataobject").addHandler(logging.NullHandler())

from src.adapt.format import ProductList
from src.adapt.research import (
    _align_product_type,
    _is_partial_return,
    _is_return_transition,
    difference,
    read_plist,
    write_plist,
)


def product(name="part", count=2.0):
    return {
        "name": name,
        "firm": "brand",
        "code": "code",
        "count": count,
        "price": 10.5,
    }


def entry(status=5, count=2, comment=None, path=(0, 0), name="part"):
    return status, count, comment, path, product(name, float(count))


def plist(name="ROSSKO", agent_id=1, data=None):
    return ProductList(name, agent_id, data)


class ProductListTests(unittest.TestCase):
    def test_empty_validation_bounds_and_adapt_dispatch(self):
        empty = plist()
        self.assertEqual(empty.data, {})
        self.assertIsNone(empty.min_day)
        self.assertIsNone(empty.max_day)
        self.assertEqual(list(empty.type_products), [])
        self.assertEqual(list(empty.products), [])

        with self.assertRaises(pydantic.ValidationError):
            plist(data={"2026-02-31": {}})
        with self.assertRaisesRegex(ValueError, "Неизвестный"):
            ProductList.adapt(("OTHER", 1, []))

    def test_from_rossko_and_profit(self):
        rossko = ProductList.adapt((
            "ROSSKO",
            8880,
            [{
                "created_date": "02.06.2026 10:15:00",
                "id": "1001",
                "parts": {"part": [{
                    "guid": "same-guid", "status": "31", "count": "2",
                    "comment": None, "name": "Pad", "brand": "Acme",
                    "partnumber": "P-1", "price": "12.5",
                }, {
                    "guid": "same-guid", "status": 5, "count": 1,
                    "comment": "ok", "name": "Disc", "brand": "Acme",
                    "partnumber": "D-1", "price": 20,
                }]},
            }],
        ))
        self.assertEqual(rossko.min_day, "2026-06-02")
        self.assertEqual(rossko.max_day, "2026-06-02")
        self.assertEqual(len(list(rossko.products)), 2)
        self.assertEqual(rossko.data["2026-06-02"][1001]["same-guid"][0][4]["name"], "Pad")

        profit = ProductList.adapt((
            "PROFIT",
            8876,
            [{
                "datetime": "2026-06-03 09:00:00",
                "order_id": "2002",
                "products": [{
                    "article_id": "a-1", "status_id": "20", "quantity": "3",
                    "comment": "return", "description": "Bearing",
                    "brand": "Maker", "article": "B-1", "price": "7.25",
                }],
            }],
        ))
        row = list(profit.products)[0]
        self.assertEqual(row[:7], ("2026-06-03", 2002, "a-1", 20, 3, "return", (0, 0)))
        self.assertEqual(row[7]["price"], 7.25)

    def test_add_merge_add_and_reverse_add(self):
        left = plist()
        left.add("2026-06-02", 1, "g", *entry())
        left.add("2026-06-02", 1, "g", *entry(31, path=(0, 1)))

        other = plist(data={"2026-06-03": {2: {"h": [entry(36)]}}})
        left.merge(other)
        left.merge({"2026-06-04": {3: {"i": [entry(9)]}}})
        added = left + {"2026-06-05": {4: {"j": [entry(8)]}}}
        reversed_added = left.__radd__({"2026-06-06": {5: {"k": [entry(7)]}}})

        self.assertEqual(len(left.data["2026-06-02"][1]["g"]), 2)
        self.assertIn("2026-06-05", added.data)
        self.assertIn("2026-06-06", reversed_added.data)


class ResearchTests(unittest.TestCase):
    def test_difference_validates_inputs(self):
        current = plist(data={"2026-06-02": {1: {"g": [entry()]}}})
        self.assertEqual(list(difference(plist(), plist(), (31,))), [])
        cases = [
            ((object(), current, (31,)), TypeError),
            ((current, plist(agent_id=2), (31,)), ValueError),
            ((current, current, [31]), TypeError),
            ((current, current, ()), ValueError),
            ((current, current, (4,)), ValueError),
            ((plist("OTHER", data=current.data), plist("OTHER", data=current.data), (1,)), AttributeError),
            ((current, plist(data={"2026-06-01": {1: {"g": [entry()]}}}), (31,)), ValueError),
        ]
        for args, error in cases:
            with self.subTest(error=error):
                with self.assertRaises(error):
                    list(difference(*args))

    def test_difference_equal_length_paths(self):
        old = plist(data={
            "2026-06-01": {9: {"skip": [entry()]}},
            "2026-06-02": {1: {
                "changed": [entry(5)],
                "anomaly": [entry(5, count=2)],
                "same": [entry(31)],
            }},
        })
        new = plist(data={
            "2026-06-01": {9: {"skip": [entry(31)]}},
            "2026-06-02": {1: {
                "changed": [entry(31, name="new")],
                "anomaly": [entry(31, count=3)],
                "same": [entry(31)],
            }},
        })
        rows = list(difference(old, new, (31, 36)))
        self.assertEqual(rows[0][:6], ("ROSSKO", 1, "2026-06-02", 1, "changed", (5, 31)))
        self.assertEqual(rows[0][6]["name"], "new")

    def test_difference_alignment_full_partial_and_failure(self):
        old = plist(data={
            "2026-06-01": {9: {"skip": [entry()]}},
            "2026-06-02": {1: {
                "full": [entry(5, path=(0, 0))],
                "partial": [entry(5, count=4, comment="x", path=(1, 0))],
                "bad": [entry(5, count=2)],
            }},
        })
        new = plist(data={
            "2026-06-01": {9: {"skip": [entry()]}},
            "2026-06-02": {1: {
                "full": [entry(31, path=(0, 0)), entry(8, path=(0, 1))],
                "partial": [
                    entry(5, count=4, comment="x", path=(1, 0)),
                    entry(31, count=1, comment="x", path=(1, 1), name="partial-return"),
                ],
                "bad": [entry(5, count=3), entry(31, count=1)],
            }},
        })
        rows = list(difference(old, new, (31, 36)))
        self.assertEqual([row[4] for row in rows], ["partial"])
        self.assertEqual(rows[0][6]["name"], "partial-return")

        profit_old = plist("PROFIT", data={
            "2026-06-01": {1: {"x": [entry()]}},
            "2026-06-02": {1: {"x": [
                entry(5, count=2, path=(0, 0)),
                entry(5, count=4, comment="x", path=(0, 1)),
            ]}},
        })
        profit_new = plist("PROFIT", data={
            "2026-06-01": {1: {"x": [entry()]}},
            "2026-06-02": {1: {"x": [
                entry(20, count=2, path=(0, 0)),
                entry(5, count=4, comment="x", path=(0, 1)),
                entry(20, count=1, comment="x", path=(0, 2)),
            ]}},
        })
        self.assertEqual(len(list(difference(profit_old, profit_new, (20,)))), 2)

        no_return_old_data = {
            "2026-06-01": {1: {"x": [entry()]}},
            "2026-06-02": {
                1: {"x": [entry(5, count=4, comment="x")]},
            },
        }
        no_return_new_data = {
            "2026-06-01": {1: {"x": [entry()]}},
            "2026-06-02": {
                1: {"x": [
                    entry(5, count=4, comment="x", path=(0, 0)),
                    entry(8, count=1, comment="x", path=(0, 1)),
                ]},
            },
        }
        no_return_old = plist(data=no_return_old_data)
        no_return_new = plist(data=no_return_new_data)
        self.assertEqual(list(difference(no_return_old, no_return_new, (31,))), [])

    def test_alignment_helpers_cover_edge_cases(self):
        self.assertEqual(_align_product_type([], []), [])
        self.assertIsNone(_align_product_type([], [entry()]))
        self.assertIsNone(_align_product_type([entry()], []))
        self.assertIsNone(_align_product_type([entry(count=2)], [entry(count=3)]))
        self.assertEqual(len(_align_product_type([entry()], [entry()]) or []), 1)

        old = entry(5, count=4, comment="x", path=(0, 0))
        same = entry(5, count=4, comment="x", path=(0, 0))
        partial = entry(31, count=1, comment="x", path=(0, 1))
        self.assertTrue(_is_partial_return(old, same, partial))
        self.assertFalse(_is_return_transition("ROSSKO", 31, 36, (36,)))
        self.assertTrue(_is_return_transition("PROFIT", 5, 20, (20,)))

        # A tempting partial match whose tail cannot align falls back and fails.
        self.assertIsNone(_align_product_type([old, entry(5)], [same, partial, entry(count=9)]))

    def test_pickle_roundtrip_and_errors(self):
        value = plist(data={"2026-06-02": {1: {"g": [entry()]}}})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "value.pkl"
            wrong = root / "value.txt"
            not_plist = root / "other.pkl"
            wrong.write_text("x", encoding="utf-8")

            write_plist(value, str(target))
            self.assertEqual(read_plist(str(target)).data, value.data)
            with self.assertRaises(TypeError):
                write_plist({}, target)
            with self.assertRaises(ValueError):
                write_plist(value, wrong)
            with self.assertRaises(TypeError):
                read_plist(1)
            with self.assertRaises(FileNotFoundError):
                read_plist(root / "missing.pkl")
            with self.assertRaises(ValueError):
                read_plist(wrong)
            with not_plist.open("wb") as stream:
                pickle.dump({}, stream)
            with self.assertRaises(TypeError):
                read_plist(not_plist)


if __name__ == "__main__":
    unittest.main()
