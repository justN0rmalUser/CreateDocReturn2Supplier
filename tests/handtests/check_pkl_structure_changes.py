import json
import pickle
from pathlib import Path


TDATA_PATH = Path(r"C:\Program Files\_Scripts\Create_ReturnNomeclature\data\temp")
JSON_PATH = Path(r"C:\Program Files\_Scripts\Create_ReturnNomeclature\tests\handtests\pkl_structure_changes.json")

class ProductListProxy:
    def __init__(self, data=None):
        self._data = data if data is not None else {}

    @property
    def data(self) -> dict:
        return self._data


class ProductListUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if module == "utilities.dataobject" and name == "ProductList":
            return ProductListProxy
        return super().find_class(module, name)


def read_plist_compat(path: Path) -> ProductListProxy:
    with open(path, "rb") as fpkl:
        obj = ProductListUnpickler(fpkl).load()
        if not isinstance(obj, ProductListProxy):
            raise TypeError(f"{path} does not contain ProductList-compatible payload")
        return obj


def parse_snapshot_name(path: Path) -> tuple[str, str]:
    stem = path.stem
    for suffix in ("_rossko", "_profit"):
        if stem.endswith(suffix):
            return stem.removesuffix(suffix), suffix[1:]
    raise ValueError(f"Unsupported snapshot name: {path.name}")


def iter_snapshot_files() -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = {}
    for path in TDATA_PATH.glob("*.pkl"):
        weekday, source = parse_snapshot_name(path)
        grouped.setdefault(source, []).append(path)

    for source, paths in grouped.items():
        grouped[source] = sorted(paths, key=lambda item: item.stat().st_mtime)
    return grouped


def product_entry(day: str, order_id: int, item_idx: int, payload: tuple[str, int, tuple[int, int]]) -> dict:
    guid, status, raw_path = payload
    return {
        "day": day,
        "order_id": order_id,
        "item_idx": item_idx,
        "guid": guid,
        "status": status,
        "raw_path": list(raw_path),
    }


def compare_product_lists(old_data: ProductListProxy, new_data: ProductListProxy) -> dict[str, list[dict]]:
    changes = {
        "missing_orders": [],
        "added_orders": [],
        "part_count_changed": [],
        "missing_items": [],
        "added_items": [],
        "guid_changed_at_index": [],
    }

    old_days = set(old_data.data)
    new_days = set(new_data.data)
    common_days = sorted(old_days & new_days)

    for day in common_days:
        old_orders = old_data.data[day]
        new_orders = new_data.data[day]

        old_order_ids = set(old_orders)
        new_order_ids = set(new_orders)

        for order_id in sorted(old_order_ids - new_order_ids):
            changes["missing_orders"].append({
                "day": day,
                "order_id": order_id,
                "old_part_count": len(old_orders[order_id]),
            })
        for order_id in sorted(new_order_ids - old_order_ids):
            changes["added_orders"].append({
                "day": day,
                "order_id": order_id,
                "new_part_count": len(new_orders[order_id]),
            })

        for order_id in sorted(old_order_ids & new_order_ids):
            old_items = old_orders[order_id]
            new_items = new_orders[order_id]

            if len(old_items) != len(new_items):
                changes["part_count_changed"].append({
                    "day": day,
                    "order_id": order_id,
                    "old_part_count": len(old_items),
                    "new_part_count": len(new_items),
                })

            old_item_ids = set(old_items)
            new_item_ids = set(new_items)

            for item_idx in sorted(old_item_ids - new_item_ids):
                changes["missing_items"].append({
                    "day": day,
                    "order_id": order_id,
                    "old": product_entry(day, order_id, item_idx, old_items[item_idx]),
                })
            for item_idx in sorted(new_item_ids - old_item_ids):
                changes["added_items"].append({
                    "day": day,
                    "order_id": order_id,
                    "new": product_entry(day, order_id, item_idx, new_items[item_idx]),
                })
            for item_idx in sorted(old_item_ids & new_item_ids):
                old_guid, old_status, old_raw_path = old_items[item_idx]
                new_guid, new_status, new_raw_path = new_items[item_idx]
                if old_guid != new_guid:
                    changes["guid_changed_at_index"].append({
                        "day": day,
                        "order_id": order_id,
                        "item_idx": item_idx,
                        "old": {
                            "guid": old_guid,
                            "status": old_status,
                            "raw_path": list(old_raw_path),
                        },
                        "new": {
                            "guid": new_guid,
                            "status": new_status,
                            "raw_path": list(new_raw_path),
                        },
                    })

    return changes


def has_changes(changes: dict[str, list[dict]]) -> bool:
    return any(changes.values())


def main() -> None:
    grouped_files = iter_snapshot_files()
    result = {
        "base_path": str(TDATA_PATH),
        "output_path": str(JSON_PATH),
        "sources": {},
    }

    for source, paths in grouped_files.items():
        comparisons = []
        for old_path, new_path in zip(paths, paths[1:]):
            old_plist = read_plist_compat(old_path)
            new_plist = read_plist_compat(new_path)
            changes = compare_product_lists(old_plist, new_plist)

            comparisons.append({
                "old_file": old_path.name,
                "new_file": new_path.name,
                "old_days": [min(old_plist.data), max(old_plist.data)] if old_plist.data else [],
                "new_days": [min(new_plist.data), max(new_plist.data)] if new_plist.data else [],
                "has_changes": has_changes(changes),
                "changes": changes,
            })

        result["sources"][source] = {
            "files": [path.name for path in paths],
            "comparisons": comparisons,
        }

    with open(JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=4)

    print(f"Saved structure changes to {JSON_PATH}")


if __name__ == "__main__":
    main()
