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
        log_supplier = Logger.new(f"update.{agent_name}", "update")
        
        connection = Connection(db_cfg)

        with connection.single_transaction(type_api="high", read_only=False) as trans:
            try:
                try:
                    log_supplier.debug("Создание документов поставщика")
                    docs_pks = trans.create_document_out(agent_id, 0)
                    log_supplier.info("Документы поставщика созданы")
                except Exception as exc:
                    log.error(
                        "Ошибка создания документов поставщика %s: %s",
                        agent_name,
                        exc,
                    )
                    raise

                try:
                    log_supplier.debug("Заполнение документов поставщика")
                    trans.fill_document_out(
                        products,
                        docs_pks["DOCUMENT_OUT"],
                        docs_pks["DOCUMENT_OUT_HEADER"]
                    )
                    log_supplier.info("Документы поставщика заполнены")
                except Exception as exc:
                    log.error(
                        "Ошибка заполнения документов поставщика %s: %s",
                        agent_name,
                        exc,
                    )
                    raise
                
                log_supplier.success("Данные записаны, ошибок нет")
            finally:
                log_supplier.close()

    log.info("Обновление данных завершено, подключение закрыто")
