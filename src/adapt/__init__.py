from pathlib import Path
from typing import Iterable, TypeAlias

from .format import ProductList
from .research import difference, read_plist, write_plist
from ..utils.archive import archive_pkl
from ..utils.config import load_config
from ..utils.other import day_of_week


cfg = load_config()
WORKFLOW_PATH = Path(cfg["Cache"]["path"])

SupplierName: TypeAlias = str
SupplierId: TypeAlias = str
SupplierData: TypeAlias = Iterable[dict]

DataPkg: TypeAlias = tuple[SupplierName, SupplierId, SupplierData]

ALLOWED_STATUSES = {
    "ROSSKO": (31, 36),
    "PROFIT": (20, )
}


def run(data: list[DataPkg]):
    result: list[DataPkg] = []

    # Запись сегодняшних данных
    for agent_name, agent_id, fetched_data in data:
        plist = ProductList.adapt((agent_name, agent_id, fetched_data))
        
        today_path = Path(day_of_week(0, postfix=f"_{agent_name.lower()}") + '.pkl')
        
        write_plist(plist, WORKFLOW_PATH / agent_name.lower() / today_path)

    # Сравнение
    for agent_name, agent_id, fetched_data in data:
        yesterday_path = Path(day_of_week(-1, postfix=f"_{agent_name.lower()}") + '.pkl')
        today_path = Path(day_of_week(0, postfix=f"_{agent_name.lower()}") + '.pkl')
        
        old_plist = read_plist(WORKFLOW_PATH / agent_name.lower() / yesterday_path)
        new_plist = read_plist(WORKFLOW_PATH / agent_name.lower() / today_path)

        statuses_for_supplier = ALLOWED_STATUSES.get(new_plist.agent_name)
        got_data = [
            product 
            for _, _, _d, _o, _g, _s, product in 
            difference(old_plist, new_plist, statuses_for_supplier)
        ]
        
        if got_data:
            result.append((agent_name, agent_id, got_data))
        
        archive_pkl(
            plist,
            agent_name.lower(),
            archive_dir=cfg["Archive"]["path"]["product_difference_checkup"]
        )

    return result
