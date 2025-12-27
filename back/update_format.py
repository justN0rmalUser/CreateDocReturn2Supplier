import sys
import fdb
import configparser

from utilities._utils import std


cfg = configparser.ConfigParser(); cfg.read("config.ini")


DB_PATH = cfg['Database']['db_path']
DB_USER = cfg['Database']['db_user']
DB_PASSWORD = cfg['Database']['db_password']


def stdcode(cursor):
    SQLC = """
    SELECT DISTINCT CODE FROM SHOP_NOMENCLATURE
    """

    data = cursor.execute(SQLC).fetchall()

    with open("utilities\\fmt.py", mode='w', encoding='utf-8') as file:
        file.write('fmt_code = {\n')
        for code in data:
            file.write(f'\t"{std(str(*code))}": "{str(*code)}",\n')
        file.write("}\n\n")

def stdfirm(cursor):
    SQLF = """
    SELECT PRODUCER_ID, NAME FROM PRODUCER
    """

    data = cursor.execute(SQLF).fetchall()

    with open("utilities\\fmt.py", mode='a', encoding='utf-8') as file:
        file.write('fmt_firm = {\n')
        for prod_id, name in data:
            file.write(f'\t"{std(str(name))}": {prod_id},\n')
        file.write("}\n")


def main():
    try:
        con = fdb.connect(dsn=DB_PATH, user=DB_USER, password=DB_PASSWORD)
    except Exception as e:
        sys.exit(1)

    try:
        cur = con.cursor()
    except Exception as e:
        sys.exit(1)

    try:
        stdcode(cur)
    except Exception as exc:
        sys.exit(1)
    
    try:
        stdfirm(cur)
    except Exception as exc:
        sys.exit(1)