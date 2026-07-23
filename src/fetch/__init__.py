from datetime import date, timedelta
from typing import Iterable, TypeAlias

from requests import RequestException

from ..utils.logging import Logger
log = Logger.new("fetch")
PATH_TO_LOGFILE = log.filepath

from .suppliers import profit, rossko               # noqa: E402
from ..utils.archive import archive_json            # noqa: E402
from ..utils.config import load_config              # noqa: E402


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
        try:
            data = provider.pull_data(start=start.isoformat(), end=end.isoformat())
        except (RuntimeError, RequestException) as rerr:
            log.error(rerr)
            raise
        except Exception as exc:
            log.critical(exc)
            raise
        else:
            result.append((provider.NAME, provider.ID, data))
            archive_json(
                data, 
                provider.NAME,
                archive_dir=cfg["Archive"]["path"]["server_answers"]
            )

    if result:
        return result
    raise ValueError("Все ответы пустые!")


__all__ = [run]
