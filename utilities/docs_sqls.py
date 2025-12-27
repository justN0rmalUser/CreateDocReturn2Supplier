import sys
import time
from datetime import datetime, date


def document_registry(cursor, self_update_id: int | None=None, *, time_stamp: date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
    GET_ID = "SELECT MAX(DOCUMENT_REGISTRY_ID) FROM DOCUMENT_REGISTRY"
    CREATE_DOC = """
    INSERT INTO DOCUMENT_REGISTRY(
        METATABLE_ID,
        CREATE_USER_ID, 
        CREATE_DATE,
        CHANGE_USER_ID,
        CHANGE_DATE, 
        DOCUMENT_TYPE_ID_CACHE
    )
    VALUES(
        12,
        1,
        '{stamp}',
        1,
        '{stamp}',
        7
    )
    """
    
    UPDATE_DOC = """
    UPDATE DOCUMENT_REGISTRY
    SET CHANGE_DATE = '{stamp}'
    WHERE DOCUMENT_REGISTRY_ID = {doc_id}
    """
    if self_update_id:
        try:
            cursor.execute(UPDATE_DOC.format(stamp=time_stamp, doc_id=self_update_id))
        except Exception as exc:
            print('doc_req')
            print(exc)
            return False
        else:
            return self_update_id
    else:
        try:
            cursor.execute(CREATE_DOC.format(stamp=time_stamp))
        except Exception as exc:
            print('doc_req')
            print(exc)
            return False
        else:
            res = cursor.execute(GET_ID).fetchone()
            return res[0]


def document_out_header(cursor, doc_out, doc_reg, self_update_id: int | None=None, *, time_stamp: date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
    GET_ID = "SELECT MAX(DOCUMENT_OUT_HEADER_ID) FROM DOCUMENT_OUT_HEADER"
    GET_NUM = 'SELECT MAX("NUMBER") FROM DOCUMENT_OUT_HEADER'
    CREATE_DOC = """
    INSERT INTO DOCUMENT_OUT_HEADER(
        DOCUMENT_REGISTRY_ID, 
        DOCUMENT_OUT_ID, 
        DOCUMENT_TYPE_ID, 
        USER_ID, 
        "NUMBER", 
        DATE_CREATE, 
        STATE,  
        MANAGER_ID,
        BARCODE
    )
    VALUES(
        {doc_reg},
        {doc_out},
        7,
        1,
        (SELECT MAX("NUMBER") FROM DOCUMENT_OUT_HEADER WHERE DOCUMENT_TYPE_ID = 7) + 1,
        '{stamp}',
        2,
        1,
        '20000004'
    )"""

    UPDATE_DOC = """
    UPDATE DOCUMENT_OUT_HEADER
    SET STATE = 4
    WHERE DOCUMENT_OUT_HEADER_ID = {doc_id}
    """
    
    if self_update_id:
        try:
            cursor.execute(UPDATE_DOC.format(doc_id=self_update_id))
        except Exception as exc:
            print('out_head')
            print(exc)
            return False
        else:
            return self_update_id    
    else:
        try:
            cursor.execute(CREATE_DOC.format(doc_reg=doc_reg, doc_out=doc_out, stamp=time_stamp))
            
        except Exception as exc:
            print('out_head')
            print(exc)
            return False
        else:
            print(cursor.execute(GET_NUM).fetchone())
            res = cursor.execute(GET_ID).fetchone()
            return res[0]

def document_action(cursor, doc_reg, summa, is_end: bool, *, time_stamp: date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
    CREATE_DOC = """
    INSERT INTO DOCUMENT_ACTION(
        DOCUMENT_REGISTRY_ID,
        USER_ID,
        ACTION_DATETIME,
        STATE
        )
    VALUES (
        {doc_reg},
        1,
        '{stamp}',
        4
    )
    """
    try:
        cursor.execute(CREATE_DOC.format(stamp=time_stamp, doc_reg=doc_reg))
    except Exception as exc:
        print('doc_act')
        print(exc)
        return False
    else:
        return True


def document_out(cursor, summa, partner_id, self_update_id: int | None=None, *, time_stamp: date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
    GET_ID = "SELECT MAX(DOCUMENT_OUT_ID) FROM DOCUMENT_OUT"
    CREATE_DOC = """
    INSERT INTO DOCUMENT_OUT(
        DOCUMENT_TYPE_ID,
        ORGANIZATION_ID, 
        ORGANIZATION_CONTACT_ID, 
        ORGANIZATION_REQUISITE_ID,
        CLIENT_ID, 
        SUMMA, 
        DATE_ACCEPT,
        FLAG
    )
    VALUES (
        7,
        1,
        4458,
        2,
        {partner_id},
        {summa},
		'{stamp}',
        1
    )
    """

    UPDATE_DOC = """
    UPDATE DOCUMENT_OUT
    SET DATE_ACCEPT = '{stamp}'
    WHERE DOCUMENT_OUT_ID = {doc_id}
    """
    if self_update_id:
        try:
            cursor.execute(UPDATE_DOC.format(stamp=time_stamp, doc_id=self_update_id))
        except Exception as exc:
            print('doc_out')
            print(exc)
            return False
        else:
            return self_update_id    
    else:
        try:
            cursor.execute(CREATE_DOC.format(partner_id=partner_id, summa=summa, stamp=time_stamp))
        except Exception as exc:
            print('doc_out')
            print(exc)
            return False
        else:
            res = cursor.execute(GET_ID).fetchone()
            return res[0]

def document_return_pvd_detail(cursor, doc_out_head, *, time_stamp: date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")):
    CREATE_DOC = """
    INSERT INTO DOCUMENT_RETURN_PVD_DETAIL(
        DOCUMENT_OUT_HEADER_ID, 
        REASON
    )
    VALUES (
        {doc_out_head},
        'Отказ (Auto)'
    )"""
    try:
        cursor.execute(CREATE_DOC.format(doc_out_head=doc_out_head))
    except Exception as exc:
        print('pvd')
        print(exc)
        return False
    else:
        return True

def goods_out(cursor, good_in, doc_out, shop_nom, price, count, enum):
    INSERT_VALUE = """
    INSERT INTO GOODS_OUT(
        GOODS_IN_ID,
        DOCUMENT_OUT_ID,
        SHOP_NOMENCLATURE_ID,
        COST,
        GOODS_COUNT,
        GOODS_COUNT_FACT,
        GUARANTE,
        POSITION_NUMBER
    )
    VALUES (
        {good_in},
        {doc_out},
        {shop_nom},
        {cost},
        {count},
        {count},
        1,
        {enum}
    )
    """
    try:
        cursor.execute(INSERT_VALUE.format(
            good_in=good_in, 
            doc_out=doc_out,
            shop_nom=shop_nom,
            cost=price,
            count=count,
            enum=enum)
            )
    except Exception as exc:
        print('goods out')
        print(exc)
        return False
    else:
        return True


def goods_in(cursor, brand_ID, code):
    GET_GOODSIN = """
    SELECT GOODS_IN_ID, GOODS_IN.SHOP_NOMENCLATURE_ID 
    FROM GOODS_IN
    JOIN SHOP_NOMENCLATURE USING(SHOP_NOMENCLATURE_ID)
    JOIN PRODUCER USING(PRODUCER_ID)
    WHERE PRODUCER_ID = {brand} AND (SEARCH_VALUE_NUMBER_MANUFACTURE = '{code}' OR CODE = '{code}')
    ORDER BY GOODS_IN.SHOP_NOMENCLATURE_ID DESC, GOODS_IN_ID DESC;
    """

    try:
        inid = cursor.execute(GET_GOODSIN.format(brand=brand_ID, code=code)).fetchall()
        assert inid
    except AssertionError:
        return False, False
    except Exception as exc:
        print('goods in')
        print(exc)
        return False
    else:
        return inid

def check_count_goods(cursor, brand_ID, code):
    GET_SUM = """
    SELECT
        COALESCE(in_total.total_in, 0) - COALESCE(out_total.total_out, 0) AS balance
    FROM
        (SELECT SUM(gi.GOODS_COUNT) AS total_in
        FROM GOODS_IN gi
        JOIN SHOP_NOMENCLATURE sn ON gi.SHOP_NOMENCLATURE_ID = sn.SHOP_NOMENCLATURE_ID
        JOIN PRODUCER p ON sn.PRODUCER_ID = p.PRODUCER_ID
        WHERE p.PRODUCER_ID = {brand}
        AND ('{code}' = sn.SEARCH_VALUE_NUMBER_MANUFACTURE OR '{code}' = sn.CODE)
        ) in_total
    FULL JOIN
        (SELECT SUM(go.GOODS_COUNT) AS total_out
        FROM GOODS_OUT go
        JOIN GOODS_IN gi ON go.GOODS_IN_ID = gi.GOODS_IN_ID
        JOIN SHOP_NOMENCLATURE sn ON gi.SHOP_NOMENCLATURE_ID = sn.SHOP_NOMENCLATURE_ID
        JOIN PRODUCER p ON sn.PRODUCER_ID = p.PRODUCER_ID
        WHERE p.PRODUCER_ID = {brand}
        AND ('{code}' = sn.SEARCH_VALUE_NUMBER_MANUFACTURE OR '{code}' = sn.CODE)
        ) out_total
    ON 1 = 1;
    """

    GET_GIN = """
    SELECT GOODS_IN_ID, GOODS_IN.SHOP_NOMENCLATURE_ID, SUM(GOODS_COUNT) 
    FROM GOODS_IN
    JOIN SHOP_NOMENCLATURE USING(SHOP_NOMENCLATURE_ID)
    JOIN PRODUCER USING(PRODUCER_ID)
    WHERE PRODUCER_ID = {brand} AND (SEARCH_VALUE_NUMBER_MANUFACTURE = '{code}' OR CODE = '{code}')
    GROUP BY GOODS_IN_ID, GOODS_IN.SHOP_NOMENCLATURE_ID;
    """
    GET_SAME_FROM_OUT = """
    SELECT SUM(GOODS_COUNT) 
    FROM GOODS_OUT
    JOIN SHOP_NOMENCLATURE USING(SHOP_NOMENCLATURE_ID)
    JOIN PRODUCER USING(PRODUCER_ID)
    WHERE PRODUCER_ID = {gin} AND GOODS_OUT.SHOP_NOMENCLATURE_ID = {sid}
    GROUP BY GOODS_IN_ID, GOODS_OUT.SHOP_NOMENCLATURE_ID;
    """

    try:
        con = cursor.execute(GET_SUM.format(brand=brand_ID, code=code)).fetchone()
    except Exception as exc:
        print("чек")
        print(exc)
        return 0
    else:
        return float(con[0])
    
def get_slots(cursor, brand_ID, code):
    GET_DIFF = """
    WITH in_agg AS (
        SELECT 
            gi.GOODS_IN_ID,
            gi.SHOP_NOMENCLATURE_ID,
            SUM(gi.GOODS_COUNT) AS total_in
        FROM GOODS_IN gi
        JOIN SHOP_NOMENCLATURE sn USING(SHOP_NOMENCLATURE_ID)
        JOIN PRODUCER p USING(PRODUCER_ID)
        WHERE p.PRODUCER_ID = {brand} 
            AND ('{code}' IN (sn.SEARCH_VALUE_NUMBER_MANUFACTURE, sn.CODE))
        GROUP BY gi.GOODS_IN_ID, gi.SHOP_NOMENCLATURE_ID 
    ),
    out_agg AS (
        SELECT 
            go.GOODS_IN_ID,
            SUM(go.GOODS_COUNT) AS total_out
        FROM GOODS_OUT go
        GROUP BY go.GOODS_IN_ID
    )
    SELECT 
        in_agg.GOODS_IN_ID AS GIN,
        in_agg.SHOP_NOMENCLATURE_ID AS SNID,
        in_agg.total_in - COALESCE(out_agg.total_out, 0) AS net_balance
    FROM in_agg
    LEFT JOIN out_agg ON in_agg.GOODS_IN_ID = out_agg.GOODS_IN_ID
	WHERE (in_agg.total_in - COALESCE(out_agg.total_out, 0)) > 0 
        AND in_agg.GOODS_IN_ID IS NOT NULL 
        AND in_agg.SHOP_NOMENCLATURE_ID IS NOT NULL
	ORDER BY GIN
    """
    try:
        slt = cursor.execute(GET_DIFF.format(brand=brand_ID, code=code)).fetchall()
    except Exception as exc:
        print("слоты")
        print(exc)
        return ()
    else:
        return slt
