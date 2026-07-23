from logging import INFO

from autodealerAPI import Connection, DatabaseConfig, setup_logging

from .utils.logging import Logger


log = Logger.new("update")
PATH_TO_LOGFILE = log.filepath

setup_logging(log_file="C:\\Program Files\\_Scripts\\Create_ReturnNomeclature\\data\\logs\\frame.log", level=INFO)


def run(data):
    log.debug('Старт функции "run"')
    log.debug("Инициализация подключения к базе данных")

    db_cfg = DatabaseConfig()

    
    for agent_name, agent_id, products in data:
        if not products:
            log.warning("Пустые данные у поставщика %s", agent_name)
            continue
        
        log.info("Обновление данных поставщика %s", agent_name)
        
        connection = Connection(db_cfg)

        with connection.single_transaction(type_api="high", read_only=False) as trans:
            try:
                log.debug("Создание документов поставщика %s", agent_name)
                docs_pks = trans.create_document_out(agent_id, 0)
                log.info("Документы поставщика %s созданы", agent_name)
            except Exception as exc:
                log.error(
                    "Ошибка создания документов поставщика %s: %s",
                    agent_name,
                    exc,
                )
                raise

            try:
                log.debug("Заполнение документов поставщика %s", agent_name)
                trans.fill_document_out(
                    products,
                    docs_pks["DOCUMENT_OUT"],
                    docs_pks["DOCUMENT_OUT_HEADER"]
                )
                log.info("Документы поставщика %s заполнены", agent_name)
            except Exception as exc:
                log.error(
                    "Ошибка заполнения документов поставщика %s: %s",
                    agent_name,
                    exc,
                )
                raise

            log.success("Данные записаны, ошибок нет")

    log.info("Обновление данных завершено, подключение закрыто")
