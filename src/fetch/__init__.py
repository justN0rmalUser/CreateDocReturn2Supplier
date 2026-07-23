from datetime import date, timedelta
from typing import Iterable, TypeAlias

from .suppliers import profit, rossko
from ..utils.archive import archive_json
from ..utils.config import load_config


cfg = load_config()

SupplierName: TypeAlias = str
SupplierId: TypeAlias = str
SupplierData: TypeAlias = Iterable[dict]

DataPkg: TypeAlias = tuple[SupplierName, SupplierId, SupplierData]

SUPPLIERS = (
    rossko.RosskoAPI(), 
    profit.ProfitLigaAPI()
)


def run() -> list[DataPkg]:
    end: date = date.today() - timedelta(days=cfg["Suppliers"]["delta_days"])
    start: date = end - timedelta(days=63)
    
    result: list[DataPkg] = []
    
    for provider in SUPPLIERS:
        data = provider.pull_data(start=start.isoformat(), end=end.isoformat())
        
        archive_json(
            data, 
            provider.NAME.lower(),
            archive_dir=cfg["Archive"]["path"]["server_answers"]
        )
        
        result.append((provider.NAME, provider.ID, data))

        
    if result:
        return result
    raise ValueError("Все ответы пустые!")


__all__ = [run]
