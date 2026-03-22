import fdb

from utilities._utils import logger, get_config
from utilities.docs_sqls import (
    document_registry,
    document_out_header,
    document_action,
    document_out,
    document_return_pvd_detail,
    goods_out,
    goods_in,
    check_count_goods,
    get_slots
)


cfg = get_config()

LOG = logger(name="Request", fpath="logs\\req.log")
ERRDATA = logger(name="Errors", fpath="logs\\corrupt_data.log")


def get_free_cells(cursor, brand_id, code, count):
    count_of_free_slots = check_count_goods(cursor, brand_id, code)
    assert count_of_free_slots, "Нет свободных слотов"
    
    slots = get_slots(cursor, brand_id, code)
    assert slots, "Ошибка при поиске позиций"

    if count_of_free_slots - count < 0:
        count = min(count, count_of_free_slots)
    
    return slots, count


def aggregate_data (cursor, data):
    valid_data = []
    summary = 0.0
    for guid in data:
        inner_dict = data[guid]

        brand_id = inner_dict["brand"]
        code = inner_dict["partnumber"]
        price = inner_dict["price"]
        count = inner_dict["count"]

        LOG.info(f"Проверка фирмы и кода из ключа; BRAND: {brand_id}, CODE: {code}")
        LOG.info(f"Проверка цены и количества из значения по ключу; PRICE: {price}, COUNT: {count}")

        try:
            slots, count = get_free_cells(cursor, brand_id, code, count)
        except AssertionError as ass:
            ERRDATA.warning(f"{ass}; BRAND: {brand_id}, CODE: {code}")
        else:
            for good_id, shop_id, quantity in slots:
                quantity = float(quantity)
                if count <= 0 or quantity <= 0:
                    LOG.warning(f"Кол-во товара: {count}, Кол-во в позиции: {quantity} -> что-то нулевое или отрицательное!")
                    continue
                if count - quantity >= 0:
                    if good_id and shop_id:
                        valid_data.append((good_id, shop_id, price, quantity))
                        summary += price * quantity
                        count -= quantity
                        LOG.info(f"Товар {good_id}:{shop_id} добавлен в список валида")
                        if count == 0:
                            break
                    else:
                        LOG.warning(f"Товар {good_id}:{shop_id} не найден в базе!")
                else:
                    if good_id and shop_id:
                        valid_data.append((good_id, shop_id, price, count))
                        summary += price * count
                        LOG.info(f"Товар {good_id}:{shop_id} добавлен в список валида")
                    else:
                        LOG.warning(f"Товар {good_id}:{shop_id} не найден в базе!")
                    break
    return valid_data, summary


def main(*, contractorHeader):
    # Подключение к базе данных
    try:
        LOG.debug("Подключение к базе данных")
        con = fdb.connect(dsn=      cfg["Database"]["db_path"],
                          user=     cfg["Database"]["db_user"], 
                          password= cfg["Database"]["db_password"])
    except Exception as e:
        LOG.critical(f"Ошибка подключения к базе: {e}")
        raise
    else:
        LOG.info("База данных подключена успешно")

    # Курсор
    try:
        LOG.debug("Создание курсора")
        cur = con.cursor()
    except Exception as e:
        LOG.critical(f"Ошибка установки курсора: {e}")
        raise
    else:
        LOG.info("Курсор установлен успешно")


    all_goods_is_commited = True
    for agent_id in contractorHeader:
        # Проверка валидных товаров
        data = contractorHeader[agent_id]
        valid_data, valid_summa = aggregate_data(cursor=cur, data=data)

        # Создание цепочки документов
        if valid_data:
            LOG.debug("Старт цикла создания документов")
            try:
                doc_reg_id = document_registry(cur)
                LOG.debug("Создание документа регистрации; ID: {}".format(doc_reg_id))

                doc_out_id = document_out(cur, valid_summa, int(agent_id))
                LOG.debug("Создание документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_out_id, doc_reg_id))

                doc_reg_id = document_registry(cur, doc_reg_id) # update
                LOG.debug("Обновление документа регистрации; ID: {}".format(doc_reg_id))
                
                doc_head_i = document_out_header(cur, doc_out_id, doc_reg_id)   
                LOG.debug("Создание заголовка документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_head_i, doc_reg_id))
                
                doc_pvd_id = document_return_pvd_detail(cur, doc_head_i)
                LOG.debug("Создание причины отказа документа реализации товара; DOC_HEAD ID: {}".format(doc_head_i))
            except Exception as exc:
                LOG.error(f"Ошибка создания документов; Ошибка: {exc}")
                raise
            else:
                con.commit()
                LOG.info("Документы созданы и сохранены")
        
            # Отправка БД 
            for i, goods_params in enumerate(valid_data, start=1):
                good_id, shop_id, price, count = goods_params
                if goods_out(cur, good_id, doc_out_id, shop_id, price, count, i):
                    con.commit()
                    LOG.info("Товар успешно добавлен") 
                else:
                    all_goods_is_commited = False
                    LOG.warning("Товар не добавлен!") 
                    ERRDATA.warning(f"Товар не добавлен! Его goodsin_id: <{good_id}>, shopnom_id: <{shop_id}>; Кол-во: {count}, Цена: {price}")
            try:
                document_registry(cur, self_update_id=doc_reg_id)
                LOG.info("Печатка даты в документе регистрации; ID: {}".format(doc_reg_id))

                document_out(cur, valid_summa, agent_id, self_update_id=doc_out_id)
                LOG.info("Изменение категории состояния на 4 для документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_out_id, doc_reg_id))

                document_out_header(cur, doc_out_id, doc_reg_id, self_update_id=doc_head_i)
                LOG.info("Изменение категории состояния на 4 для заголовка документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_head_i, doc_reg_id))

                document_action(cur, doc_reg_id, valid_summa, is_end=True)
                LOG.info("Изменение категории состояния на 4 в активностях документа; ID: {}; DOC_REG ID: {}".format(doc_head_i, doc_reg_id))
            except Exception as exc:
                LOG.critical(f"Ошибка создания документов; Ошибка: {exc}")
                raise
            else:
                con.commit()
                LOG.info("Документы обновлены и сохранены")
        else:
            LOG.warning(f"Среди товаров поставщика {agent_id} не найден никакой валид!")
            all_goods_is_commited = False
    return all_goods_is_commited


    
