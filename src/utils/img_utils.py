import re
import os
import hashlib
from typing import Union, List
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader, QColor, QImage
from PyQt6.QtCore import Qt, QSize, QBuffer, QByteArray, QRect
import zipfile
from src.utils.str_utils import find_number
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CACHE_DIR = Path('.cache/thumbnails')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_key(path: str, width: int, height: int, crop: str = None) -> str:
    """Generate a cache key for a file path and thumbnail settings."""
    mod_time = os.path.getmtime(path)
    settings = f"{width}x{height}{'_' + crop if crop else ''}"
    return hashlib.md5(f"{path}{mod_time}{settings}".encode()).hexdigest()

def get_virtual_path_cache_key(virtual_path: str, width: int, height: int, crop: str = None) -> str:
    """Generate a cache key for a virtual path and thumbnail settings."""
    zip_path, image_name = virtual_path.split('|', 1)
    mod_time = os.path.getmtime(zip_path)
    settings = f"{width}x{height}{'_' + crop if crop else ''}"
    return hashlib.md5(f"{virtual_path}{mod_time}{settings}".encode()).hexdigest()

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

def is_image_folder(folder: Union[Path, str]) -> bool:
    if isinstance(folder, str):
        folder = Path(folder)
    files = [f for f in folder.iterdir() if f.is_file()]
    return bool(files) and all(f.suffix.lower() in IMG_EXTS for f in files)

def is_image_monotone(image_path: str, threshold: float = 10.0) -> bool:
    """
    Check if an image is largely monotone (e.g., all white or all black).
    It does this by resizing to a small image and checking the standard deviation.
    """
    try:
        # Read file into a numpy array to handle non-ASCII paths correctly
        with open(image_path, 'rb') as f:
            nparr = np.frombuffer(f.read(), np.uint8)
        
        # Decode image from the array
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        if img is None:
            return True # Treat as monotone if it can't be read

        # Resize to a small image for performance
        small_img = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
        
        # Calculate the standard deviation of pixel intensities
        std_dev = np.std(small_img)
        
        return std_dev < threshold
    except Exception:
        # If any error occurs, assume it's not a valid image for a thumbnail
        return True

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
    path_str = str(path)
    try:
        cache_key = get_cache_key(path_str, width, height, crop)
        cached_thumb_path = CACHE_DIR / f"{cache_key}.png"

        if cached_thumb_path.exists():
            pixmap = QPixmap()
            if pixmap.load(str(cached_thumb_path)):
                return pixmap
    except FileNotFoundError:
        return None # Original file not found
        
    video_extensions = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
    file_ext = Path(path_str).suffix.lower()

    pixmap = None

    if file_ext in video_extensions:
        try:
            cap = cv2.VideoCapture(path_str)
            if cap.isOpened():
                # Try to capture a frame from 2 seconds into the video
                cap.set(cv2.CAP_PROP_POS_MSEC, 2000)
                ret, frame = cap.read()
                if not ret:
                    # if that fails, try the very first frame
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()

                if ret:
                    # Convert BGR frame to RGB
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_frame.shape
                    bytes_per_line = ch * w
                    q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_image)
            cap.release()
        except Exception as e:
            print(f"Error creating video thumbnail: {e}")
            pixmap = None # Ensure pixmap is None on error
    else:
        # Existing image loading logic
        reader = QImageReader(path_str)
        original_size = reader.size()
        
        if crop:
            if original_size.width() > original_size.height():
                if crop == 'left':
                    reader.setClipRect(QRect(0, 0, original_size.width() // 2, original_size.height()))
                elif crop == 'right':
                    reader.setClipRect(QRect(original_size.width() // 2, 0, original_size.width() // 2, original_size.height()))

        pixmap = load_thumbnail(reader, width, height)

    if pixmap and not pixmap.isNull():
        # Scale and save the thumbnail
        scaled_pixmap = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        scaled_pixmap.save(str(cached_thumb_path), "PNG")
        return scaled_pixmap

    # Return a placeholder if everything failed
    return empty_placeholder(width, height)

def load_thumbnail_from_zip(path, width=150, height=200):
    path_str = str(path)
    try:
        cache_key = get_cache_key(path_str, width, height)
        cached_thumb_path = CACHE_DIR / f"{cache_key}.png"

        if cached_thumb_path.exists():
            pixmap = QPixmap()
            if pixmap.load(str(cached_thumb_path)):
                return pixmap
    except FileNotFoundError:
        return None # Original file not found

    try:
        with zipfile.ZipFile(path, 'r') as zf:
            image_files = sorted([f for f in zf.namelist() if f.lower().endswith(IMG_EXTS) and not f.startswith('__MACOSX')])
            if not image_files:
                return None

            first_image_name = image_files[0]
            with zf.open(first_image_name) as f:
                image_data = f.read()
                
                byte_array = QByteArray(image_data)
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.OpenModeFlag.ReadOnly)

                reader = QImageReader(buffer, QByteArray())
                pixmap = load_thumbnail(reader, width, height)

                if pixmap and not pixmap.isNull():
                    pixmap.save(str(cached_thumb_path), "PNG")

                return pixmap
    except zipfile.BadZipFile:
        return None

def load_thumbnail_from_virtual_path(virtual_path, width=150, height=200, crop=None):
    try:
        cache_key = get_virtual_path_cache_key(virtual_path, width, height, crop)
        cached_thumb_path = CACHE_DIR / f"{cache_key}.png"

        if cached_thumb_path.exists():
            pixmap = QPixmap()
            if pixmap.load(str(cached_thumb_path)):
                return pixmap
    except FileNotFoundError:
        return None # Original zip file not found

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

                pixmap = load_thumbnail(reader, width, height)

                if pixmap and not pixmap.isNull():
                    pixmap.save(str(cached_thumb_path), "PNG")

                return pixmap
            
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
    
    # Try explicit "Ch." or "Chapter"
    match = re.search(r'(?:ch|chapter|c)\.?\s*(\d+)', name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # Fallback to finding the first number, but be careful of "Vol 1 Ch 2"
    # If there are multiple numbers, simple find_number might get the volume.
    # But usually manga naming is "Series - Ch X" or "Series 01".
    
    return find_number(name)
    

def _get_first_image_path(chapter_dir):
    if not chapter_dir:
        return None
    chapter_path = Path(chapter_dir)
    if isinstance(chapter_dir, str) and chapter_dir.endswith('.zip'):
        try:
            with zipfile.ZipFile(chapter_dir, 'r') as zf:
                image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                if image_files:
                    return f"{chapter_dir}|{image_files[0]}"
        except zipfile.BadZipFile:
            return None
    elif chapter_path.is_dir():
        exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
        image_files = [p for p in sorted(chapter_path.iterdir()) if p.suffix.lower() in exts and p.is_file()]
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