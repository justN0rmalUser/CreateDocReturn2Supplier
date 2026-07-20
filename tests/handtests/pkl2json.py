import sys 
import os
import json
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

from utilities.dataobject import read_plist


JSON_PATH = Path(r"C:\Program Files\_Scripts\Create_ReturnNomeclature\tests\handtests\pkl_last.json")


if __name__ == "__main__":
    plist = read_plist(
        Path(input("Введите полный путь до pkl:\n>>> "))
    )

    with open(JSON_PATH, 'w', encoding="utf-8") as FILE:
        json.dump(plist.data, FILE, ensure_ascii=False, indent=4)
    print("Успех")