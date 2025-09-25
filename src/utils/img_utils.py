import re
from typing import Union, List
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader, QColor, QImage
from PyQt6.QtCore import Qt, QSize, QBuffer, QByteArray, QRect
import zipfile
from src.utils.str_utils import find_number
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

def is_image_folder(folder: Union[Path, str]) -> bool:
    if isinstance(folder, str):
        folder = Path(folder)
    files = [f for f in folder.iterdir() if f.is_file()]
    return bool(files) and all(f.suffix.lower() in IMG_EXTS for f in files)

def get_image_size(path: Union[str, Path]):
    path = str(path)
    if '|' in path:
        return get_image_size_from_virtual_path(path)
    else:
        return get_image_size_from_path(path)

def get_image_size_from_path(path: str) -> tuple[int,int]:
    """Return width/height ratio of image."""
    reader = QImageReader(str(path))
    size = reader.size()
    height = size.height()
    width = size.width()
    if height == 0:
        return width, height, 0
    
    return width, height

def get_image_size_from_virtual_path(path:str):
    try:
        zip_path, image_name = path.split('|', 1)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with zf.open(image_name) as f:
                image_data = f.read()
                
                byte_array = QByteArray(image_data)
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.OpenModeFlag.ReadOnly)

                reader = QImageReader(buffer, QByteArray())
                size = reader.size()
                height = size.height()
                width = size.width()
                if height == 0:
                    return width, height, 0
                
                return width, height
            
    except (zipfile.BadZipFile, KeyError):
        return None
    
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
    

def _get_first_image_path(chapter_dir):
    if isinstance(chapter_dir, str) and chapter_dir.endswith('.zip'):
        try:
            with zipfile.ZipFile(chapter_dir, 'r') as zf:
                image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                if image_files:
                    return f"{chapter_dir}|{image_files[0]}"
        except zipfile.BadZipFile:
            return None
    elif isinstance(chapter_dir, Path) and chapter_dir.is_dir():
        exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
        image_files = [p for p in sorted(chapter_dir.iterdir()) if p.suffix.lower() in exts and p.is_file()]
        if image_files:
            return str(image_files[0])
    return None

def segment_image_by_black_lines(image_path: str) -> List[dict]:
    """
    Segments an image into multiple parts based on black lines.
    Returns a list of dictionaries, each containing the coordinates for each segmented part.
    """
    try:
        # Load the image using OpenCV
        img = cv2.imread(image_path)
        if img is None:
            return []

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Apply threshold to get a binary image
        # Black lines will be white, everything else will be black
        _, thresh = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY_INV)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        panels = []
        for contour in contours:
            # Filter out small contours
            if cv2.contourArea(contour) < 1000:
                continue

            # Get bounding box for each contour
            x, y, w, h = cv2.boundingRect(contour)

            cx = x + w // 2
            cy = y + h // 2

            panels.append({"cx": cx, "cy": cy, "w": w, "h": h})

        return panels
    except Exception as e:
        print(f"Error segmenting image: {e}")
        return []

def detect_manga_panels(image_path: str) -> List[dict]:
    """
    Detects rectangular panels in a manga image.
    Returns a list of dictionaries, each containing the center coordinates and dimensions.
    """
    try:
        # Load the image using OpenCV
        img = cv2.imread(image_path)
        if img is None:
            return []

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Adaptive thresholding to handle different lighting conditions
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        panels = []
        for contour in contours:
            # Filter out small contours based on area
            if cv2.contourArea(contour) < 1000:
                continue

            # Approximate the contour to a polygon
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            # Check if the polygon has 4 vertices (is a quadrilateral)
            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(approx)
                
                # Filter out shapes that are not large enough
                if w > 50 and h > 50:
                    cx = x + w // 2
                    cy = y + h // 2
                    panels.append({"cx": cx, "cy": cy, "w": w, "h": h})

        return panels
    except Exception as e:
        print(f"Error detecting panels: {e}")
        return []

def draw_text_on_image(image, text, box):
    """
    Draws text on an image with a white background using PIL for UTF-8 support.
    The text is wrapped to fit the bounding box.

    Args:
        image: The image to draw on (numpy array from OpenCV).
        text: The text to draw.
        box: The bounding box (min_x, min_y, max_x, max_y).
    """
    min_x, min_y, max_x, max_y = [int(c) for c in box]

    # Draw a white rectangle to cover the original text
    cv2.rectangle(image, (min_x, min_y), (max_x, max_y), (255, 255, 255), -1)

    # Convert OpenCV image to PIL image
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)

    # --- Font Size Selection & Text Wrapping ---
    box_width = max_x - min_x
    box_height = max_y - min_y
    
    font_size = box_height
    font = None
    wrapped_text = text

    while font_size > 1:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        # --- Text Wrapping ---
        words = text.split()
        lines = []
        if not words:
            wrapped_text = ""
        else:
            current_line = words[0]
            for word in words[1:]:
                test_line = f"{current_line} {word}"
                text_bbox = draw.textbbox((0,0), test_line, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                if text_width <= box_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            lines.append(current_line)
            wrapped_text = "\n".join(lines)

        # --- Check if wrapped text fits ---
        text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        if text_width <= box_width and text_height <= box_height:
            break
        font_size -= 1

    # --- Text Placement ---
    text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = min_x + (box_width - text_width) / 2
    text_y = min_y + (box_height - text_height) / 2

    # Draw the text
    draw.multiline_text((text_x, text_y), wrapped_text, font=font, fill=(0, 0, 0), align="center")

    # Convert PIL image back to OpenCV image
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)