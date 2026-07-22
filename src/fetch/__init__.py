from datetime import date, timedelta
from typing import Iterable, TypeAlias

from .suppliers import profit, rossko
from ..utils.archive import archive_json
from ..utils.config import load_config


cfg = load_config()


SUPPLIERS = (
    rossko.RosskoAPI(), 
    profit.ProfitLigaAPI()
)

SupplierName: TypeAlias = str
SupplierId: TypeAlias = str


def run() -> list[tuple[str, int, list[dict[str, str | float | int | dict]]], ...]:
    end: date = date.today() - timedelta(days=cfg["DEFAULT"]["delta_days"])
    start: date = end - timedelta(days=63)
    
    result: list[tuple[SupplierName, SupplierId, Iterable[dict]], ...] = []
    
    for provider in SUPPLIERS:
        data = provider.pull_data(start=start, end=end)
        
        archive_json(
            data, 
            provider.NAME.lower(),
            archive_dir=cfg["Backup"]["archive"]["server_answers"]
        )
        
        result.append((provider.NAME, provider.ID, data))

        
    if result:
        return result
    raise ValueError("Все ответы пустые!")


__all__ = [run]
