from logging import INFO

from autodealerAPI import Connection, DatabaseConfig, setup_logging

from .utils.other import get_config, logger


LOG = logger(name="Request", fpath="logs\\req.log")
ERRDATA = logger(name="Errors", fpath="logs\\corrupt_data.log")
setup_logging(log_file="C:\\Program Files\\_Scripts\\Create_ReturnNomeclature\\logs\\frame.log", level=INFO)
CFG = get_config()


def run(data):
    db_cfg = DatabaseConfig()

    connection = Connection(db_cfg)
    
    for agent_name, agent_id, products in data:
        transaction = connection.transaction()

        with transaction.start_transaction(type_api="high", read_only=False) as trans:
            try:
                LOG.debug("Старт цикла создания документов")
                docs_pks = trans.create_document_out(agent_id, 0)
                LOG.info("Документы созданы и сохранены")
            except Exception as exc:
                LOG.error(f"Ошибка создания документов; Ошибка: {exc}")
                raise

            try:
                LOG.debug("Старт цикла заполнения документов")
                trans.fill_document_out(
                    products,
                    docs_pks["DOCUMENT_OUT"],
                    docs_pks["DOCUMENT_OUT_HEADER"]
                )
                LOG.info("Документы заполнены и сохранены")
            except Exception as exc:
                LOG.error(f"Ошибка заполнения документов; Ошибка: {exc}")
                raise

    connection.close()
