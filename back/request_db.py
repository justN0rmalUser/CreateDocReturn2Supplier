import datetime
import sys
import fdb
import configparser
import logging as log

from utilities._utils import *


cfg = configparser.ConfigParser(); cfg.read("config.ini")

DB_PATH = cfg['Database']['db_path']
DB_USER = cfg['Database']['db_user']
DB_PASSWORD = cfg['Database']['db_password']

now = datetime.now()


req_log = log.getLogger("request")
req_log.setLevel(log.DEBUG)

req_hand = log.FileHandler(filename="logs\\req.log", encoding='utf-8')
req_hand.setFormatter(log.Formatter('[%(asctime)s] %(levelname)s | %(message)s'))

req_log.addHandler(req_hand)



def aggregate_data (cursor, data):
    valid_data = []
    summary = 0.0
    for key in data:
        brand_id, code = key
        price, count = data[key]
        req_log.info(f"Проверка фирмы и кода из ключа; BRAND: {brand_id}, CODE: {code}")
        req_log.info(f"Проверка цены и количества из значения по ключу; PRICE: {price}, COUNT: {count}")

        try:
            count_of_free_slots = check_count_goods(cursor, brand_id, code)
            assert count_of_free_slots, "Нет свободных слотов"
            
            slots = get_slots(cursor, brand_id, code)
            assert slots, "Ошибка при поиске позиций"

            if count_of_free_slots - count < 0:
                count = min(count, count_of_free_slots)
        except AssertionError as ass:
            req_log.warning(f"{ass}; BRAND: {brand_id}, CODE: {code}")
        else:
            for good_id, shop_id, quantity in slots:
                quantity = float(quantity)
                if count <= 0 or quantity <= 0:
                    req_log.warning(f"Кол-во товара: {count}, Кол-во в позиции: {quantity} -> что-то нулевое или отрицательное!")
                    continue
                if count - quantity >= 0:
                    if good_id and shop_id:
                        valid_data.append((good_id, shop_id, price, quantity))
                        summary += price * quantity
                        count -= quantity
                        req_log.info(f"Товар {good_id}:{shop_id} добавлен в список валида")
                        if count == 0:
                            break
                    else:
                        req_log.warning(f"Товар {good_id}:{shop_id} не найден в базе!")
                else:
                    if good_id and shop_id:
                        valid_data.append((good_id, shop_id, price, count))
                        summary += price * count
                        req_log.info(f"Товар {good_id}:{shop_id} добавлен в список валида")
                    else:
                        req_log.warning(f"Товар {good_id}:{shop_id} не найден в базе!")
                    break
    return valid_data, summary


def main(success_data):
    # Подключение к базе данных
    rossko, profit = success_data
    try:
        con = fdb.connect(dsn=DB_PATH, user=DB_USER, password=DB_PASSWORD)
        req_log.info("База данных подключена успешно")
    except Exception as e:
        req_log.error(f"Ошибка подключения к базе: {e}")
        sys.exit(1)

    # Курсор
    try:
        cur = con.cursor()
        req_log.info("Курсор установлен успешно")
    except Exception as e:
        req_log.error(f"Ошибка установки курсора: {e}")
        sys.exit(1)

    all_goods_is_commited = True
    for partner in success_data:
        # Проверка валидных товаров
        partner_id, data, fail, summa = partner
        valid_data, valid_summa = aggregate_data(cursor=cur, data=data)

        # Создание цепочки документов
        if valid_data:
            doc_reg_id = document_registry(cur)
            req_log.info("Создание документа регистрации; ID: {}".format(doc_reg_id))

            doc_out_id = document_out(cur, valid_summa, partner_id)
            req_log.info("Создание документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_out_id, doc_reg_id))

            doc_reg_id = document_registry(cur, doc_reg_id) # update
            req_log.info("Обновление документа регистрации; ID: {}".format(doc_reg_id))
            
            doc_head_i = document_out_header(cur, doc_out_id, doc_reg_id)   
            req_log.info("Создание заголовка документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_head_i, doc_reg_id))
            
            doc_pvd_id = document_return_pvd_detail(cur, doc_head_i)
            con.commit()
            req_log.info("Создание причины отказа документа реализации товара; DOC_HEAD ID: {}".format(doc_head_i))
        
            # Отправка БД 
            for i, goods_params in enumerate(valid_data, start=1):
                good_id, shop_id, price, count = goods_params
                if goods_out(cur, good_id, doc_out_id, shop_id, price, count, i):
                    con.commit()
                    req_log.info("Товар успешно добавлен") 
                else:
                    all_goods_is_commited = False
                    req_log.warning("Товар не добавлен!")

            document_registry(cur, self_update_id=doc_reg_id)
            req_log.info("Печатка даты в документе регистрации; ID: {}".format(doc_reg_id))

            document_out(cur, valid_summa, self_update_id=doc_out_id)
            req_log.info("Изменение категории состояния на 4 для документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_out_id, doc_reg_id))

            document_out_header(cur, doc_out_id, doc_reg_id, self_update_id=doc_head_i)
            req_log.info("Изменение категории состояния на 4 для заголовка документа реализации товара; ID: {}; DOC_REG ID: {}".format(doc_head_i, doc_reg_id))

            document_action(cur, doc_reg_id, valid_summa, is_end=True)
            con.commit()
            req_log.info("Изменение категории состояния на 4 в активностях документа; ID: {}; DOC_REG ID: {}".format(doc_head_i, doc_reg_id))
        else:
            req_log.warning(f"Среди товаров поставщика {partner_id} не найден никакой валид!")
            all_goods_is_commited = False
        return all_goods_is_commited


    
