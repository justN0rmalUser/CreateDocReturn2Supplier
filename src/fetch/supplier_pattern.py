from abc import ABC, abstractmethod
from typing import ClassVar


class Supplier(ABC):
    """Абстрактный класс для встраиваемых модулей - поставщиков"""
    
    NAME: ClassVar[str]
    ID: ClassVar[int]

    @abstractmethod
    def pull_data(self, start: str, end: str) -> dict:
        pass
