from pathlib import Path
from typing import Iterable, TypeAlias

from .format import ProductList
from .research import difference, read_plist, write_plist
from ..utils.archive import archive_pkl
from ..utils.config import load_config
from ..utils.other import day_of_week


cfg = load_config()
WORKFLOW_PATH = Path(cfg["Backup"]["cache"])

SupplierName: TypeAlias = str
SupplierId: TypeAlias = str

ALLOWED_STATUSES = {
    "ROSSKO": (31, 36),
    "PROFIT": (20, )
}


def run(data: list[tuple[SupplierName, SupplierId, Iterable[dict]], ...]):
    result: list[tuple[str, int, dict]] = []

    for agent_name, agent_id, fetched_data in data:
        plist = ProductList.adapt((agent_name, agent_id, fetched_data))
        
        today_path = Path(day_of_week(0, postfix=f"_{agent_name.lower()}") + '.pkl')
        yesterday_path = Path(day_of_week(-1, postfix=f"_{agent_name.lower()}") + '.pkl')
        
        write_plist(plist, WORKFLOW_PATH / agent_name.lower() / today_path)
        old_plist = read_plist(WORKFLOW_PATH / agent_name.lower() / yesterday_path)

        got_data = [
            new_data 
            for _, _, _d, _o, _g, _s, new_data in 
            difference(old_plist, plist, ALLOWED_STATUSES.get(plist.agent_name))
        ]
        
        result.append((agent_name, agent_id, got_data))
        
        archive_pkl(
            plist,
            agent_name.lower(),
            archive_dir=cfg["Backup"]["archive"]["product_difference_checkup"]
        )

    return result
