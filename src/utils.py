import re
import zipfile
import io
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtCore import Qt, QSize, QBuffer, QByteArray

def is_image_folder(folder: Path) -> bool:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
    files = [f for f in folder.iterdir() if f.is_file()]
    return bool(files) and all(f.suffix.lower() in image_exts for f in files)

def get_chapter_number(path):
    """Extract the chapter number as integer from the folder or file name."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name
    
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

def load_thumbnail_from_zip(path, width=150, height=200):
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
            if not image_files:
                return None

            first_image_name = image_files[0]
            with zf.open(first_image_name) as f:
                image_data = f.read()
                
                byte_array = QByteArray(image_data)
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.OpenModeFlag.ReadOnly)

                reader = QImageReader(buffer, QByteArray())
                reader.setScaledSize(QSize(width, height))
                reader.setQuality(50)
                
                image = reader.read()
                if image.isNull():
                    return None
                return QPixmap.fromImage(image)
    except zipfile.BadZipFile:
        return None

def load_thumbnail_from_virtual_path(virtual_path, width=150, height=200):
    try:
        zip_path, image_name = virtual_path.split('|', 1)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with zf.open(image_name) as f:
                image_data = f.read()
                
                byte_array = QByteArray(image_data)
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.OpenModeFlag.ReadOnly)

                reader = QImageReader(buffer, QByteArray())
                reader.setScaledSize(QSize(width, height))
                reader.setQuality(50)
                
                image = reader.read()
                if image.isNull():
                    return None
                return QPixmap.fromImage(image)
    except (zipfile.BadZipFile, KeyError):
        return None

def get_image_data_from_zip(virtual_path):
    try:
        zip_path, image_name = virtual_path.split('|', 1)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with zf.open(image_name) as f:
                return f.read()
    except (zipfile.BadZipFile, KeyError):
        return None
