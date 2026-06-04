from __future__ import annotations

from datetime import date
import logging
import pickle
import tempfile
import unittest

from utilities import rosskoNprofit as rossko_module


for handler in list(rossko_module.GET_DATA_LOGGER.handlers):
    if isinstance(handler, logging.FileHandler):
        rossko_module.GET_DATA_LOGGER.removeHandler(handler)
        handler.close()
rossko_module.GET_DATA_LOGGER.addHandler(logging.NullHandler())
rossko_module.GET_DATA_LOGGER.propagate = False

NormalizedPosition = rossko_module.NormalizedPosition
RosskoAPI = rossko_module.RosskoAPI


def make_order(
    order_id: int,
    status: int | None,
    *,
    guid: str = "guid-1",
    brand: str | None = "Brand",
    code: str | None = "A-1",
    created_date: str = "01.01.2026 10:00:00",
    part_as_dict: bool = False,
) -> dict:
    part = {
        "guid": guid,
        "partnumber": code,
        "name": "Part",
        "brand": brand,
        "price": "100.50",
        "count": 2,
    }
    if status is not None:
        part["status"] = status

    return {
        "id": order_id,
        "created_date": created_date,
        "parts": {"part": part if part_as_dict else [part]},
    }


def make_position(key: str, status: int) -> NormalizedPosition:
    return {
        "period": "01.01.2026",
        "order_id": key,
        "created_date": "01.01.2026 10:00:00",
        "guid": key,
        "brand": "Brand",
        "partnumber": "A-1",
        "name": "Part",
        "price": 100.5,
        "count": 2.0,
        "status": status,
    }


class FakeRosskoAPI(RosskoAPI):
    def __init__(
        self,
        responses: dict[tuple[date, date], list[dict]] | None = None,
        *,
        start: date = date(2026, 1, 1),
        end: date = date(2026, 3, 5),
        snapshot_path: str = "unused.pkl",
    ) -> None:
        super().__init__(
            url="",
            key_1="",
            key_2="",
            start_date=start,
            end_date=end,
            snapshot_path=snapshot_path,
            request_delay=0,
        )
        self.responses = responses or {}
        self.calls: list[tuple[date, date]] = []

    def _request_orders(self, start: date, end: date) -> list[dict]:
        self.calls.append((start, end))
        return list(self.responses.get((start, end), []))


class RosskoAPITests(unittest.TestCase):
    def test_64_day_window_starts_as_two_32_day_requests(self) -> None:
        api = FakeRosskoAPI()

        api.get_orders_for_period()

        self.assertEqual(
            api.calls,
            [
                (date(2026, 1, 1), date(2026, 2, 1)),
                (date(2026, 2, 2), date(2026, 3, 5)),
            ],
        )

    def test_saturated_range_is_split_in_half(self) -> None:
        saturated_orders = [make_order(i, 2, guid=f"guid-{i}") for i in range(500)]
        responses = {
            (date(2026, 1, 1), date(2026, 2, 1)): saturated_orders,
        }
        api = FakeRosskoAPI(responses)

        api.get_orders_for_period()

        self.assertEqual(
            api.calls,
            [
                (date(2026, 1, 1), date(2026, 2, 1)),
                (date(2026, 1, 1), date(2026, 1, 16)),
                (date(2026, 1, 17), date(2026, 2, 1)),
                (date(2026, 2, 2), date(2026, 3, 5)),
            ],
        )

    def test_saturated_one_day_range_is_kept_with_warning(self) -> None:
        day = date(2026, 1, 1)
        orders = [make_order(i, 2, guid=f"guid-{i}") for i in range(500)]
        api = FakeRosskoAPI({(day, day): orders}, start=day, end=day)

        with self.assertLogs("Getter", level="WARNING") as logs:
            result = api.get_orders_for_period()

        self.assertEqual(len(result), 500)
        self.assertIn("data may be incomplete", "\n".join(logs.output))

    def test_normalizer_accepts_dict_list_and_missing_status(self) -> None:
        api = FakeRosskoAPI(start=date(2026, 1, 1), end=date(2026, 1, 1))
        orders = [
            make_order(1, 31, guid="dict-part", part_as_dict=True),
            {
                "id": 2,
                "created_date": "01.01.2026 11:00:00",
                "parts": {
                    "part": [
                        make_order(2, 36, guid="list-part")["parts"]["part"][0],
                        make_order(2, None, guid="missing-status")["parts"]["part"][0],
                    ]
                },
            },
        ]

        with self.assertLogs("Getter", level="WARNING"):
            snapshot = api.normalize_orders(orders)

        statuses = {position["guid"]: position["status"] for position in snapshot.values()}
        self.assertEqual(statuses["dict-part"], 31)
        self.assertEqual(statuses["list-part"], 36)
        self.assertEqual(statuses["missing-status"], -1)

    def test_diff_only_returns_positions_newly_entered_target_statuses(self) -> None:
        previous = {
            "k1": make_position("k1", 2),
            "k2": make_position("k2", 2),
            "k3": make_position("k3", 31),
            "k5": make_position("k5", 31),
        }
        current = {
            "k1": make_position("k1", 31),
            "k2": make_position("k2", 36),
            "k3": make_position("k3", 31),
            "k4": make_position("k4", 31),
            "k5": make_position("k5", 2),
        }

        changed = RosskoAPI.diff_snapshots(previous, current)

        self.assertEqual({position["guid"] for position in changed}, {"k1", "k2", "k4"})

    def test_iteration_uses_pickle_snapshot_and_commit_writes_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = f"{tmpdir}/rossko.pkl"
            previous = {"01.01.2026|1|guid-1": make_position("guid-1", 2)}
            previous["01.01.2026|1|guid-1"]["order_id"] = "1"
            with open(snapshot_path, "wb") as snapshot_file:
                pickle.dump(previous, snapshot_file)

            day = date(2026, 1, 1)
            responses = {(day, day): [make_order(1, 31, part_as_dict=True)]}
            api = FakeRosskoAPI(responses, start=day, end=day, snapshot_path=snapshot_path)

            rows = list(api)
            api.commit_snapshot()

            self.assertEqual(rows, [{"name": "Part", "firm": "Brand", "code": "A-1", "count": 2.0, "price": 100.5}])
            with open(snapshot_path, "rb") as snapshot_file:
                saved = pickle.load(snapshot_file)
            self.assertEqual(saved["01.01.2026|1|guid-1"]["status"], 31)


if __name__ == "__main__":
    unittest.main()
