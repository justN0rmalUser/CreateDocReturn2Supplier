from autodealerAPI import Connection, DatabaseConfig
from typing import Literal, Tuple, Iterable
from pprint import pprint
from utilities._utils import logger


LOG = logger(name="Request", fpath="logs\\req.log")
ERRDATA = logger(name="Errors", fpath="logs\\corrupt_data.log")


def main(*, contractorHeader: Tuple[
    Tuple[
        Literal[8880],
        float,
        Iterable
    ],
    Tuple[
        Literal[8876],
        float,
        Iterable
    ] | None]):


    db_cfg = DatabaseConfig.from_ini(
        "config.ini",
        path_key="db_path",
        user_key="db_user",
        pass_key="db_password"
    )

    connection = Connection(db_cfg)
    transaction = connection.transaction()

    with transaction.start_transaction(type_api="high", read_only=False) as trans:
        for value in contractorHeader:
            if value is None:
                continue

            agent_id, summa, data = value

            try:
                LOG.debug("Старт цикла создания документов")
                docs_pks = trans.create_document_out(agent_id, summa)
                LOG.info("Документы созданы и сохранены")
            except Exception as exc:
                LOG.error(f"Ошибка создания документов; Ошибка: {exc}")
                raise

            try:
                LOG.debug("Старт цикла заполнения документов")
                trans.fill_document_out(
                    data,
                    docs_pks["DOCUMENT_OUT"],
                    docs_pks["DOCUMENT_OUT_HEADER"]
                )
                LOG.info("Документы заполнены и сохранены")
            except Exception as exc:
                LOG.error(f"Ошибка заполнения документов; Ошибка: {exc}")
                raise

    connection.close()
