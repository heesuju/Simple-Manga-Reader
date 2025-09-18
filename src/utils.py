import re
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtCore import Qt, QSize

def is_image_folder(folder: Path) -> bool:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
    files = [f for f in folder.iterdir() if f.is_file()]
    return bool(files) and all(f.suffix.lower() in image_exts for f in files)

def get_chapter_number(path: Path):
    """Extract the chapter number as integer from the folder name."""
    name = path.name
    match = re.search(r'Ch\.\s*(\d+)', name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return -1

def load_thumbnail(path, width=150, height=200):
    reader = QImageReader(str(path))
    reader.setScaledSize(QSize(width, height))
    reader.setQuality(50)  # Lower quality for faster loading
    image = reader.read()
    if image.isNull():
        pix = QPixmap(width, height)
        pix.fill(Qt.GlobalColor.gray)
        return pix
    return QPixmap.fromImage(image)
