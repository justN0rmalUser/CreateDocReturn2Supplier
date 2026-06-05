from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def install_autodealer_standard_stub() -> None:
    import types

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

    sys.modules.setdefault("autodealerAPI", autodealer_module)
    sys.modules.setdefault("autodealerAPI.utils", utils_module)
    sys.modules.setdefault("autodealerAPI.utils.functions", functions_module)
    sys.modules.setdefault("autodealerAPI.utils.functions.standard", standard_module)


install_autodealer_standard_stub()

from utilities._utils import get_config, isodate
from utilities.dataobject import ProductList, read_plist, write_plist
from utilities.rosskoNprofit import RosskoAPI
import back.get_data as get_data_module


ARTIFACT_DIR = PROJECT_ROOT / "data" / "temp" / "test_work_replay"


def main() -> None:
    args = parse_args()
    cfg = get_config()

    start = date.fromisoformat(args.start or cfg["DEFAULT"]["start_date"])
    end = date.fromisoformat(args.end or cfg["DEFAULT"]["end_date"])

    api = RosskoAPI(
        url=cfg["Rossko"]["URL"],
        key_1=cfg["Rossko"]["first_secret"],
        key_2=cfg["Rossko"]["second_secret"],
    )

    print(f"Fetching Rossko orders: {start.isoformat()} -> {end.isoformat()}")
    source_raw = api.get_orders(start=start.isoformat(), end=end.isoformat())
    normalize_parts_lists(source_raw)

    order_idx, part_idx = choose_part(source_raw, args.order_index, args.part_index)
    old_raw = copy.deepcopy(source_raw)
    new_raw = copy.deepcopy(source_raw)

    old_part = old_raw[order_idx]["parts"]["part"][part_idx]
    new_part = new_raw[order_idx]["parts"]["part"][part_idx]
    original_status = int(new_part["status"])

    old_part["status"] = args.old_status
    new_part["status"] = args.new_status

    old_products = ProductList.from_rossko(old_raw)
    new_products = ProductList.from_rossko(new_raw)
    add_min_day_sentinel(old_products)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    old_path = ARTIFACT_DIR / "old_before.pkl"
    new_path = ARTIFACT_DIR / "new_after.pkl"
    write_plist(old_products, old_path)
    write_plist(new_products, new_path)

    print("Changed one Rossko part for replay:")
    print(json.dumps({
        "order_idx": order_idx,
        "part_idx": part_idx,
        "order_id": source_raw[order_idx]["id"],
        "guid": new_part["guid"],
        "partnumber": new_part["partnumber"],
        "original_status": original_status,
        "old_status": args.old_status,
        "new_status": args.new_status,
    }, ensure_ascii=False, indent=2))

    rows = replay_get_data_cycle(
        start=start,
        end=end,
        new_raw=new_raw,
        old_path=old_path,
        new_path=new_path,
    )

    print("Program cycle result:")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Artifacts written to: {ARTIFACT_DIR}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Rossko data, modify one part status and replay back.get_data.get_rossko_data."
    )
    parser.add_argument("--start", help="ISO start date. Defaults to config.ini DEFAULT.start_date.")
    parser.add_argument("--end", help="ISO end date. Defaults to config.ini DEFAULT.end_date.")
    parser.add_argument("--order-index", type=int, help="Raw order index to modify.")
    parser.add_argument("--part-index", type=int, help="Raw part index inside selected order to modify.")
    parser.add_argument("--old-status", type=int, default=5, help="Status used in the fake old snapshot.")
    parser.add_argument("--new-status", type=int, default=31, help="Status used in the fake new snapshot.")
    return parser.parse_args()


def normalize_parts_lists(raw_orders: list[dict[str, Any]]) -> None:
    for order in raw_orders:
        part = order.get("parts", {}).get("part", [])
        if isinstance(part, dict):
            order["parts"]["part"] = [part]


def choose_part(raw_orders: list[dict[str, Any]], order_index: int | None, part_index: int | None) -> tuple[int, int]:
    if not raw_orders:
        raise AssertionError("Rossko returned no orders for this period.")

    if order_index is not None or part_index is not None:
        if order_index is None or part_index is None:
            raise ValueError("--order-index and --part-index must be passed together.")

        order = raw_orders[order_index]
        order["parts"]["part"][part_index]
        return order_index, part_index

    required_keys = {"guid", "status", "name", "brand", "partnumber", "count", "price"}
    for order_idx, order in enumerate(raw_orders):
        for idx_part, part in enumerate(order["parts"]["part"]):
            if required_keys.issubset(part):
                return order_idx, idx_part

    raise AssertionError("No Rossko part has all fields required by get_data.py.")


def add_min_day_sentinel(old_products: ProductList) -> None:
    if old_products.min_day is None:
        raise AssertionError("Old ProductList is empty; cannot add sentinel day.")

    sentinel_day = (date.fromisoformat(old_products.min_day) - timedelta(days=1)).isoformat()
    old_products.add({
        sentinel_day: {
            -1: {
                0: ("__sentinel__", 5, (-1, -1)),
            }
        }
    })


def replay_get_data_cycle(
    *,
    start: date,
    end: date,
    new_raw: list[dict[str, Any]],
    old_path: Path,
    new_path: Path,
) -> list[dict[str, float | str]]:
    original_rossko_api = get_data_module.RosskoAPI
    original_write_plist = get_data_module.write_plist
    original_read_plist = get_data_module.read_plist
    original_day_of_week = get_data_module.day_of_week

    class ReplayRosskoAPI:
        def __init__(self, *, url: str, key_1: str, key_2: str):
            self.url = url
            self.key_1 = key_1
            self.key_2 = key_2

        def get_orders(self, *, start: str, end: str) -> list[dict[str, Any]]:
            return new_raw

    try:
        get_data_module.RosskoAPI = ReplayRosskoAPI
        get_data_module.write_plist = lambda product_list, path: write_plist(product_list, new_path)
        get_data_module.read_plist = lambda path: read_plist(old_path)
        get_data_module.day_of_week = lambda delta_days=0: "old" if delta_days == -1 else "new"

        agent_id, rows_iter = get_data_module.get_rossko_data(start_date=start, end_date=end)
        rows = list(rows_iter)
        return [{"agent_id": agent_id, **row} for row in rows]
    finally:
        get_data_module.RosskoAPI = original_rossko_api
        get_data_module.write_plist = original_write_plist
        get_data_module.read_plist = original_read_plist
        get_data_module.day_of_week = original_day_of_week


if __name__ == "__main__":
    main()
