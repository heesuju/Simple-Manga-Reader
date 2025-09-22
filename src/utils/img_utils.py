import re
from typing import List
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader, QColor
from PyQt6.QtCore import Qt, QSize, QBuffer, QByteArray, QRect
import zipfile
from src.utils.str_utils import find_number

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

def is_image_folder(folder: Path) -> bool:
    files = [f for f in folder.iterdir() if f.is_file()]
    return bool(files) and all(f.suffix.lower() in IMG_EXTS for f in files)

def get_image_size(path: str) -> tuple[int,int]:
    """Return width/height ratio of image."""
    reader = QImageReader(str(path))
    size = reader.size()
    height = size.height()
    width = size.width()
    if height == 0:
        return width, height, 0
    
    return width, height

def get_image_ratio(w:int,h:int):
    return round(w / h, 2) if h != 0 else 0.0

def crop_pixmap(pixmap: QPixmap, width: int, height: int) -> QPixmap:
    if pixmap.isNull():
        return pixmap
    
    scaled_pixmap = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled_pixmap.width() - width) // 2
    y = (scaled_pixmap.height() - height) // 2
    return scaled_pixmap.copy(x, y, width, height)

def empty_placeholder(width:int=150, height:int=200):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("black"))
    return pixmap

def load_thumbnail(reader:QImageReader, width:int, height:int, quality:int=50):
    reader.setScaledSize(QSize(width, height))
    reader.setQuality(quality)  # Lower quality for faster loading
    image = reader.read()
    if image.isNull():
        return empty_placeholder(width, height)
    return QPixmap.fromImage(image)

def load_thumbnail_from_path(path, width=150, height=200, crop=None):
    reader = QImageReader(str(path))
    original_size = reader.size()
    
    if crop:
        if original_size.width() > original_size.height():
            if crop == 'left':
                reader.setClipRect(QRect(0, 0, original_size.width() // 2, original_size.height()))
            elif crop == 'right':
                reader.setClipRect(QRect(original_size.width() // 2, 0, original_size.width() // 2, original_size.height()))

    return load_thumbnail(reader, width, height)

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
                return load_thumbnail(reader, width, height)
    except zipfile.BadZipFile:
        return None

def load_thumbnail_from_virtual_path(virtual_path, width=150, height=200, crop=None):
    try:
        zip_path, image_name = virtual_path.split('|', 1)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with zf.open(image_name) as f:
                image_data = f.read()
                
                byte_array = QByteArray(image_data)
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.OpenModeFlag.ReadOnly)

                reader = QImageReader(buffer, QByteArray())
                original_size = reader.size()

                if crop:
                    if original_size.width() > original_size.height():
                        if crop == 'left':
                            reader.setClipRect(QRect(0, 0, original_size.width() // 2, original_size.height()))
                        elif crop == 'right':
                            reader.setClipRect(QRect(original_size.width() // 2, 0, original_size.width() // 2, original_size.height()))

                return load_thumbnail(reader, width, height)
            
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

def load_pixmap_for_thumbnailing(path: str, target_width: int = 0) -> QPixmap | None:
    reader = None
    buffer = None # Keep buffer in scope

    if '|' in path:
        image_data = get_image_data_from_zip(path)
        if image_data:
            byte_array = QByteArray(image_data)
            buffer = QBuffer(byte_array)
            buffer.open(QBuffer.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer)
    else:
        reader = QImageReader(path)

    if reader is None or not reader.canRead():
        return None

    reader.setAutoTransform(True)
    if target_width > 0:
        original_size = reader.size()
        if original_size.width() > target_width:
            height = int(original_size.height() * (target_width / original_size.width()))
            reader.setScaledSize(QSize(target_width, height))
            reader.setQuality(10)

    image = reader.read()
    if image.isNull():
        return None

    return QPixmap.fromImage(image)

def get_chapter_number(path):
    """Extract the chapter number as integer from the folder or file name."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name
    
    match = re.search(r'Ch\.\s*(\d+)', name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    else:
        return find_number(name)