from time import sleep

import requests 

from ..supplier_pattern import Supplier
from ...utils.config import load_config
from ...utils.logging import Logger
from ...utils.other import isodate


cfg = load_config()
log = Logger.new("fetch.profit", "fetch")


class ProfitLigaAPI(Supplier):
    """
    Класс для взаимодействия с API Profit Liga.
    Предоставляет методы для получения и фильтрации заказов.
    """

    NAME = "profit"
    ID = 8876
    
    def __init__(
        self, 
        url: str = cfg["Suppliers"]["profit"]["URL"], 
        api_key: str = cfg["Suppliers"]["profit"]["key"]
    ):
        log.debug("Инициализация класса")
        self.url = url
        self.api_key = api_key

    def _make_request(self, page_num: int, *, with_pages: bool=False) -> tuple[int, list[dict]] | tuple[int, list[dict], int]:
        """Делает запрос на сервер

        Parameters
        ----------
        **page_num** : `int`
            Номер страницы во внутренней системе "Profit"
        **with_pages** : `bool`
            С количеством страниц

        Returns
        -------
        `tuple[int, list[dict]] | tuple[int, list[dict], int]`
            Результат запроса: [размер-страницы, данные, Опционально(количество-всех-страниц)]

        Raises
        ------
        `requests.RequestException`
            Ошикбка выполнения запроса
        `RuntimeError`
            Статус ответа не успешен 
        """
        log.debug('Старт функции "_make_request"')
        
        params = {"secret": self.api_key, "page": page_num}
        try:
            log.debug("Старт запроса")
            response = requests.get(self.url, params=params)
            response.raise_for_status()
            sleep(0.5)
        except requests.RequestException as e:
            raise requests.RequestException(f"Ошибка при выполнении запроса к Profit Liga: {e}")
        else:
            log.debug("Запрос успешен")
            answer = response.json()
            if (status := answer["status"]) != "success":
                raise RuntimeError(f"Статус не успешен: {status}")
            return ( (answer["pageSize"], answer["data"], answer["pages"]) 
                    if with_pages
                    else (answer["pageSize"], answer["data"]) )

    def validate_list(
        self, 
        page: list[dict],
        start_date: str,
        end_date: str
    ):
        log.debug('Старт функции "validate_list"')
        _date_pattern = r"%Y-%m-%d %H:%M:%S"
        
        if not page:
            log.warning("Пустой лист")
            return []

        # Получаем даты верхнюю и нижнюю
        log.debug("Получение граничных дат")
        top_of_page = isodate(page[0]["datetime"], _date_pattern)
        bot_of_page = isodate(page[-1]["datetime"], _date_pattern)

        # Если весь лист внутри диапазона
        if end_date >= top_of_page and start_date <= bot_of_page:
            log.debug("Весь лист внутри диапазона")
            return page

        # Ищем индекс первой даты, которая <= end_date (верхняя граница)
        start_idx = end_idx = None
        for i, item in enumerate(page):
            current_date = isodate(item["datetime"], _date_pattern)
            if end_date >= current_date >= start_date:
                if start_idx is None:
                    start_idx = end_idx = i
                else:
                    end_idx = i

        if start_idx is None:
            log.debug("Лист вне диапазона")
            return []
        
        log.debug("Лист частично внутри диапазона")
        return page[start_idx:end_idx + 1]
    
    def pull_data(
        self,
        start: str,
        end: str
    ) -> list[dict[str, str | float | int | dict]]:
        """Получает список всех товаров за проделенный промежуток

        Returns
        -------
        `list[dict[str, str | float | int | dict]]`
            Список заказов
        """
        log.debug('Старт функции "pull_data"')

        log.info('Первый запрос с получением метаданных')
        _, data, count_pages = self._make_request(1, with_pages=True)
        result = self.validate_list(data, start, end)
        log.info('Первый запрос выполнен успешно, количество страниц: %d', count_pages)

        for page in range(2, count_pages+1):
            log.debug('Запрос и обработка страницы %d', page)
            _, data = self._make_request(page, with_pages=False)
            
            valid_data = self.validate_list(data, start, end)
            
            if result and not valid_data:
                log.info('Обработка подошла к концу')
                break
            
            log.info('Добавление страницы %d', page)
            result += valid_data
        
        return result
