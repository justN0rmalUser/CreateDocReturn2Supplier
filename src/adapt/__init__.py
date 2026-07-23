from pathlib import Path
from typing import Iterable, TypeAlias

from ..utils.logging import Logger
log = Logger.new("adapt")
PATH_TO_LOGFILE = log.filepath

from .format import ProductList                                         # noqa: E402
from .research import difference, read_plist, write_plist               # noqa: E402
from ..utils.archive import archive_pkl                                 # noqa: E402
from ..utils.config import load_config                                  # noqa: E402
from ..utils.other import day_of_week                                   # noqa: E402


cfg = load_config()
WORKFLOW_PATH = Path(cfg["Cache"]["path"])

SupplierName: TypeAlias = str
SupplierId: TypeAlias = str
SupplierData: TypeAlias = Iterable[dict]

DataPkg: TypeAlias = tuple[SupplierName, SupplierId, SupplierData]

ALLOWED_STATUSES = cfg["Cache"]["statuses"]


def run(data: list[DataPkg]):
    log.debug('Старт функции "run"')
    try:
        return _run(data)
    except Exception as exc:
        log.critical("Критическая ошибка адаптации данных: %s", exc, exc_info=True)
        raise


def _run(data: list[DataPkg]):
    log.debug('Старт функции "run"')
    result: list[DataPkg] = []

    # Запись сегодняшних данных
    for agent_name, agent_id, fetched_data in data:
        try:
            log.info("Адаптация данных поставщика %s", agent_name)
            plist = ProductList.adapt((agent_name, agent_id, fetched_data))
            
            today_path = Path(day_of_week(0, postfix=f"_{agent_name}") + '.pkl')
            
            write_plist(plist, WORKFLOW_PATH / agent_name / today_path)
        except ValueError as verr:
            log.error(verr)
            raise
        except Exception as exc:
            log.critical(exc)
            raise
        else:
            log.info("Текущие данные поставщика %s сохранены", agent_name)
            archive_pkl(
                plist,
                agent_name,
                archive_dir=cfg["Archive"]["path"]["product_difference_checkup"]
            )
            log.info("Данные поставщика %s архивированы", agent_name)

    # Сравнение
    for agent_name, agent_id, fetched_data in data:
        try:
            log.info("Сравнение данных поставщика %s", agent_name)
            
            yesterday_path = Path(day_of_week(-1, postfix=f"_{agent_name}") + '.pkl')
            today_path = Path(day_of_week(0, postfix=f"_{agent_name}") + '.pkl')
            
            old_plist = read_plist(WORKFLOW_PATH / agent_name / yesterday_path)
            new_plist = read_plist(WORKFLOW_PATH / agent_name / today_path)

            statuses_for_supplier = ALLOWED_STATUSES.get(new_plist.agent_name)
            got_data = [
                product 
                for _, _, _d, _o, _g, _s, product in 
                difference(old_plist, new_plist, statuses_for_supplier)
            ]
        except Exception as exc:
            log.critical(exc)
            raise
        else:
            if got_data:
                result.append((agent_name, agent_id, got_data))
                log.info(
                    "Для поставщика %s найдено возвратов: %d",
                    agent_name,
                    len(got_data),
                )
            else:
                log.warning("Для поставщика %s возвраты не найдены", agent_name)
        
    log.info("Адаптация данных завершена")
    return result
