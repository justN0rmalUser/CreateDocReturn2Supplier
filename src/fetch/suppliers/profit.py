from time import sleep

import requests 

from ..supplier_pattern import Supplier
from ...utils.config import load_config
from ...utils.other import isodate


cfg = load_config()


class ProfitLigaAPI(Supplier):
    """
    Класс для взаимодействия с API Profit Liga.
    Предоставляет методы для получения и фильтрации заказов.
    """

    NAME = "PROFIT"
    ID = 8876
    
    def __init__(
        self, 
        url: str = cfg["Suppliers"]["profit"]["URL"], 
        api_key: str = cfg["Suppliers"]["profit"]["key"]
    ):
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
        params = {"secret": self.api_key, "page": page_num}
        try:
            response = requests.get(self.url, params=params)
            response.raise_for_status()
            sleep(0.5)
        except requests.RequestException as e:
            raise requests.RequestException(f"Ошибка при выполнении запроса к Profit Liga: {e}")
        else:
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
        _date_pattern = r"%Y-%m-%d %H:%M:%S"
        
        if not page:
            return []

        # Получаем даты верхнюю и нижнюю
        top_of_page = isodate(page[0]["datetime"], _date_pattern)
        bot_of_page = isodate(page[-1]["datetime"], _date_pattern)

        # Если весь лист внутри диапазона
        if end_date >= top_of_page and start_date <= bot_of_page:
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
            return []
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
        _, data, count_pages = self._make_request(1, with_pages=True)
        result = self.validate_list(data, start, end)

        for page in range(2, count_pages+1):
            _, data = self._make_request(page, with_pages=False)
            
            valid_data = self.validate_list(data, start, end)
            
            if result and not valid_data:
                break
            
            result += valid_data
        
        return result
