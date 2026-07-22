from datetime import date, timedelta

from src.utils.config import load_config
from .suppliers import (
    rossko,
    profit
)


cfg = load_config()


SUPPLIERS = (
    rossko.RosskoAPI(), 
    profit.ProfitLigaAPI()
)


def run() -> list[tuple[str, int, list[dict[str, str | float | int | dict]]], ...]:
    end: date = date.today() - timedelta(days=cfg["DEFAULT"]["delta_days"])
    start: date = end - timedelta(days=63)
    
    result: list[tuple[str, int, list[dict[str, str | float | int | dict]]], ...] = []
    
    for provider in SUPPLIERS:
        result.append((provider.NAME, provider.ID, provider.pull_data(start=start, end=end)))

    if result:
        return result
    raise ValueError("Все ответы пустые!")


__all__ = [run]
