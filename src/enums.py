from enum import Enum

class ViewMode(Enum):
    NONE=0
    SINGLE=1
    DOUBLE=2
    STRIP=3
    
class ItemType(str, Enum):
    ZIP="zip"
    FOLDER="folder"
    IMAGE="image"