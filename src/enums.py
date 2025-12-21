from enum import Enum

class ViewMode(Enum):
    SINGLE=0
    DOUBLE=1
    STRIP=2

class ItemType(str, Enum):
    ZIP="zip"
    FOLDER="folder"
    IMAGE="image"

class Language(str, Enum):
    ENG="ENG"
    KOR="KOR"
