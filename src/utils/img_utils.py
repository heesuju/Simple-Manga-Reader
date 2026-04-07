import re
import os
import hashlib
from typing import Union, List, Optional
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader, QColor, QImage
from PyQt6.QtCore import Qt, QSize, QBuffer, QByteArray, QRect
import zipfile
import threading
from collections import OrderedDict
from src.utils.str_utils import find_number
from src.utils.archive_utils import decode_zip_filename, ARCHIVE_EXTS, ZIP_EXTS, split_virtual_path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def imread_unicode(path: str, flags=cv2.IMREAD_COLOR):
    """Read an image from a path that may contain non-ASCII characters on Windows."""
    try:
        # Use fromfile to read the file as a numpy array (Unicode safe)
        nparr = np.fromfile(path, np.uint8)
        # Decode the image from the array
        return cv2.imdecode(nparr, flags)
    except Exception as e:
        print(f"Error reading image {path}: {e}")
        return None

def imwrite_unicode(path: str, img, params=None):
    """Write an image to a path that may contain non-ASCII characters on Windows."""
    try:
        ext = Path(path).suffix
        # Encode the image to the specified extension
        ret, nparr = cv2.imencode(ext, img, params)
        if ret:
            # Save the array to file (Unicode safe)
            nparr.tofile(path)
            return True
    except Exception as e:
        print(f"Error writing image {path}: {e}")
    return False

class ZipCache:
    """Thread-safe LRU cache for open ZipFile objects."""
    def __init__(self, max_size: int = 5):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = threading.Lock()
        self.read_lock = threading.Lock() # Lock for actual file I/O operations

    def get_zip(self, path: str) -> zipfile.ZipFile:
        with self.lock:
            if path in self.cache:
                zf = self.cache[path]
                try:
                    # Quick check if the zip is still usable
                    if zf.fp is not None:
                        self.cache.move_to_end(path)
                        return zf
                except Exception:
                    pass
                
                # If we reach here, the zip is closed or broken
                try:
                    zf.close()
                except Exception:
                    pass
                del self.cache[path]
            
            # Create new ZipFile
            try:
                zf = zipfile.ZipFile(path, 'r')
                self.cache[path] = zf
                
                # Evict oldest if full
                if len(self.cache) > self.max_size:
                    _, zip_to_close = self.cache.popitem(last=False)
                    try:
                        zip_to_close.close()
                    except Exception:
                        pass
                
                return zf
            except Exception:
                return None

    def clear(self):
        with self.lock:
            for zf in self.cache.values():
                try:
                    zf.close()
                except Exception:
                    pass
            self.cache.clear()

ZIP_CACHE = ZipCache(max_size=5)

def qimage_reader_from_bytes(data: bytes):
    """Create a QImageReader from raw bytes. Returns (reader, buffer) — keep buffer in scope.

    Uses QBuffer.setData() so the buffer owns its copy of the data and no external
    QByteArray reference needs to be kept alive.
    """
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)
    return QImageReader(buffer), buffer

def get_image_format_from_ext(path: str) -> str:
    """Return the Qt image format string for a file path based on its extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".jpe"):
        return "JPEG"
    if ext == ".webp":
        return "WEBP"
    if ext == ".avif":
        return "AVIF"
    return "PNG"

def compress_qimage_to_size(img: QImage, target_bytes: int, fmt: str) -> Optional[QByteArray]:
    """Compress a QImage to fit within target_bytes via binary-search quality then downscaling.

    JPEG/WEBP: tries quality reduction first, then downscaling.
    PNG: lossless, so only downscaling is possible.
    Returns None if the image cannot be made small enough.
    """
    if fmt == "PNG":
        curr_img = img
        scale = 1.0
        while True:
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            curr_img.save(buf, "PNG")
            if ba.size() <= target_bytes:
                return ba
            scale *= 0.9
            w = int(img.width() * scale)
            h = int(img.height() * scale)
            if w < 10 or h < 10:
                break
            curr_img = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return None

    if fmt not in ("JPEG", "WEBP"):
        return None

    low, high = 0, 100
    best_data = None
    for _ in range(8):
        mid = (low + high) // 2
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        img.save(buf, fmt, mid)
        if ba.size() <= target_bytes:
            best_data = ba
            low = mid + 1
        else:
            high = mid - 1

    if best_data is None:
        scale = 0.9
        curr_img = img
        while True:
            w = int(curr_img.width() * scale)
            h = int(curr_img.height() * scale)
            if w < 10 or h < 10:
                break
            curr_img = curr_img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            curr_img.save(buf, fmt, 0)
            if ba.size() <= target_bytes:
                best_data = ba
                break

    return best_data

CACHE_DIR = Path('.cache/thumbnails')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_key(path: str, width: int, height: int, crop: str = None) -> str:
    """Generate a cache key for a file path and thumbnail settings."""
    mod_time = os.path.getmtime(path)
    settings = f"{width}x{height}{'_' + crop if crop else ''}"
    return hashlib.md5(f"{path}{mod_time}{settings}".encode()).hexdigest()

def get_virtual_path_cache_key(virtual_path: str, width: int, height: int, crop: str = None) -> str:
    """Generate a cache key for a virtual path and thumbnail settings."""
    zip_path, image_name = split_virtual_path(virtual_path)
    mod_time = os.path.getmtime(zip_path)
    settings = f"{width}x{height}{'_' + crop if crop else ''}"
    return hashlib.md5(f"{virtual_path}{mod_time}{settings}".encode()).hexdigest()

IMG_EXTS = ('.jpg', '.jpeg', '.jpe', '.png', '.bmp', '.gif', '.webp', '.avif')

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
    # SKIP monotone check for videos as they can't be decoded easily this way
    if any(image_path.lower().endswith(ext) for ext in VIDEO_EXTS):
        return False

    try:
        # Use Unicode-safe read
        img = imread_unicode(image_path, cv2.IMREAD_GRAYSCALE)

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

def crop_qimage(image: QImage, width: int, height: int) -> QImage:
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return image
    
    scaled_image = image.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled_image.width() - width) // 2
    y = (scaled_image.height() - height) // 2
    return scaled_image.copy(x, y, width, height)

def crop_pixmap(pixmap: QPixmap, width: int, height: int) -> QPixmap:
    return QPixmap.fromImage(crop_qimage(pixmap.toImage(), width, height))

def create_thumbnail(image: QImage, width: int, height: int) -> QImage:
    if image.isNull():
        return empty_placeholder_qimage(width, height)
         
    return crop_qimage(image, width, height)

def empty_placeholder_qimage(width:int=150, height:int=200):
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor("black"))
    return img

def empty_placeholder(width:int=150, height:int=200):
    return QPixmap.fromImage(empty_placeholder_qimage(width, height))

def load_thumbnail(reader:QImageReader, width:int, height:int, quality:int=50, source_size:QSize=None) -> QImage:
    if source_size:
        size = source_size
    else:
        size = reader.size()
    
    if size.isEmpty():
        return empty_placeholder_qimage(width, height)
    
    src_w = size.width()
    src_h = size.height()
    
    # Calculate scale to COVER the target area (Expand)
    scale = max(width / src_w, height / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    reader.setScaledSize(QSize(new_w, new_h))
    reader.setQuality(quality)  # Lower quality for faster loading
    image = reader.read()
    if image.isNull():
        return empty_placeholder_qimage(width, height)
    
    return crop_qimage(image, width, height)

def load_thumbnail_from_path(path, width=150, height=200, crop=None) -> QImage:
    path_str = str(path)
    try:
        cache_key = get_cache_key(path_str, width, height, crop)
        cached_thumb_path = CACHE_DIR / f"{cache_key}.png"

        if cached_thumb_path.exists():
            q_image = QImage()
            if q_image.load(str(cached_thumb_path)):
                return q_image
    except FileNotFoundError:
        return None # Original file not found
        
    video_extensions = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
    file_ext = Path(path_str).suffix.lower()

    q_image = None

    if file_ext in ARCHIVE_EXTS:
        return load_thumbnail_from_zip(path, width, height)

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
                    q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                    # Video frames are already cropped/scaled by cv2, so just return
                    return q_image
            cap.release()
        except Exception as e:
            print(f"Error creating video thumbnail: {e}")
            q_image = None # Ensure q_image is None on error
    elif file_ext == '.avif':
        try:
            pil_img = Image.open(path_str).convert('RGBA')
            if crop and pil_img.width > pil_img.height:
                half = pil_img.width // 2
                if crop == 'left':
                    pil_img = pil_img.crop((0, 0, half, pil_img.height))
                elif crop == 'right':
                    pil_img = pil_img.crop((half, 0, pil_img.width, pil_img.height))
            scale = max(width / pil_img.width, height / pil_img.height)
            new_w, new_h = int(pil_img.width * scale), int(pil_img.height * scale)
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            data = pil_img.tobytes('raw', 'RGBA')
            q_image = QImage(data, pil_img.width, pil_img.height, pil_img.width * 4, QImage.Format.Format_RGBA8888).copy()
        except Exception as e:
            print(f"Error loading AVIF thumbnail: {e}")
    else:
        # Existing image loading logic
        reader = QImageReader(path_str)
        original_size = reader.size()

        effective_size = original_size
        if crop:
            if original_size.width() > original_size.height():
                if crop == 'left':
                    effective_size = QSize(original_size.width() // 2, original_size.height())
                    reader.setClipRect(QRect(0, 0, original_size.width() // 2, original_size.height()))
                elif crop == 'right':
                    effective_size = QSize(original_size.width() // 2, original_size.height())
                    reader.setClipRect(QRect(original_size.width() // 2, 0, original_size.width() // 2, original_size.height()))

        q_image = load_thumbnail(reader, width, height, source_size=effective_size)

    if q_image and not q_image.isNull():
        # Scale (Crop) and save the thumbnail
        scaled_img = crop_qimage(q_image, width, height)
        scaled_img.save(str(cached_thumb_path), "PNG")
        return scaled_img

    # Return a placeholder if everything failed
    return empty_placeholder_qimage(width, height)

def load_thumbnail_from_zip(path, width=150, height=200) -> QImage:
    path_str = str(path)
    try:
        cache_key = get_cache_key(path_str, width, height)
        cached_thumb_path = CACHE_DIR / f"{cache_key}.png"

        if cached_thumb_path.exists():
            img = QImage()
            if img.load(str(cached_thumb_path)):
                return img
    except FileNotFoundError:
        return None # Original file not found

    try:
        from src.utils.archive_utils import SevenZipHandler
        
        path_obj = Path(path_str)
        ext = path_obj.suffix.lower()
        is_zip = ext in {'.zip', '.cbz'}
        
        # 1. Try zipfile first for .zip/.cbz as it has proven encoding correction
        if is_zip:
            from src.utils.img_utils import ZIP_CACHE
            zf = ZIP_CACHE.get_zip(path)
            if zf:
                try:
                    with ZIP_CACHE.read_lock:
                        # Get list of files with proper encoding fallback
                        namelist = []
                        for info in zf.infolist():
                            name = decode_zip_filename(info.filename, info.flag_bits)
                            namelist.append((name, info.filename))

                        image_files = sorted([pair for pair in namelist if pair[0].lower().endswith(IMG_EXTS) and not pair[0].startswith('__MACOSX')])
                        if image_files:
                            decoded_name, original_name = image_files[0]
                            with zf.open(original_name) as f:
                                image_data = f.read()
                            
                            reader, buffer = qimage_reader_from_bytes(image_data)
                            q_image = load_thumbnail(reader, width, height)

                            if q_image and not q_image.isNull():
                                q_image.save(str(cached_thumb_path), "PNG")

                            return q_image
                except (zipfile.BadZipFile, KeyError, RuntimeError, OSError, PermissionError, Exception) as e:
                    print(f"Error reading zip for thumbnail {path}: {e}")
                    pass

        # 2. Try 7-Zip as primary for non-zip or fallback for zip
        if SevenZipHandler.is_available():
            files = SevenZipHandler.list_files(path_str)
            image_files = sorted([f for f in files if f.lower().endswith(IMG_EXTS) and not f.startswith('__MACOSX')])
            
            if image_files:
                first_image_name = image_files[0]
                image_data = SevenZipHandler.read_file(path_str, first_image_name)
                
                if image_data:
                    reader, buffer = qimage_reader_from_bytes(image_data)
                    q_image = load_thumbnail(reader, width, height)

                    if q_image and not q_image.isNull():
                        q_image.save(str(cached_thumb_path), "PNG")
                    
                    return q_image
        return None
    except zipfile.BadZipFile:
        return None
        
def load_thumbnail_from_virtual_path(virtual_path, width=150, height=200, crop=None) -> QImage:
    try:
        cache_key = get_virtual_path_cache_key(virtual_path, width, height, crop)
        cached_thumb_path = CACHE_DIR / f"{cache_key}.png"

        if cached_thumb_path.exists():
            img = QImage()
            if img.load(str(cached_thumb_path)):
                return img
    except FileNotFoundError:
        return None # Original zip file not found

    try:
        image_data = get_image_data_from_zip(virtual_path)

        if image_data:
            reader, buffer = qimage_reader_from_bytes(image_data)
            reader.setAutoTransform(True)
            original_image = reader.read()

            if not original_image.isNull():
                thumb_image = create_thumbnail(original_image, width, height)
                # Save to cache
                if not CACHE_DIR.exists():
                    CACHE_DIR.mkdir(parents=True)
                thumb_image.save(str(cached_thumb_path), "PNG")
                return thumb_image
                
        return None
    except Exception as e:
        print(f"Error loading virtual thumbnail {virtual_path}: {e}")
        return None

def get_image_data_from_zip(virtual_path):
    zip_path_str, image_name = split_virtual_path(virtual_path)
    
    # Try 7-Zip first for ALL archives
    from src.utils.archive_utils import SevenZipHandler
    if SevenZipHandler.is_available():
        data = SevenZipHandler.read_file(zip_path_str, image_name)
        if data: return data
    
    # Standard Zip support (cached)
    try:
        zf = ZIP_CACHE.get_zip(zip_path_str)
        if zf:
            with ZIP_CACHE.read_lock:
                # Direct try
                try:
                    with zf.open(image_name) as f:
                        return f.read()
                except (KeyError, ValueError, RuntimeError):
                    pass

                # Fixed separator try
                image_name_fixed = image_name.replace('\\', '/')
                try:
                    with zf.open(image_name_fixed) as f:
                        return f.read()
                except (KeyError, ValueError, RuntimeError):
                    pass

                # Fallback: find original name by decoding CP437 -> CP932/UTF-8
                for info in zf.infolist():
                    decoded = decode_zip_filename(info.filename, info.flag_bits)
                    if decoded == image_name or decoded.replace('\\', '/') == image_name_fixed:
                        with zf.open(info.filename) as f:
                            return f.read()
    except (zipfile.BadZipFile, OSError, PermissionError, Exception) as e:
        print(f"Error reading image data from zip {zip_path_str}: {e}")
        pass
    return None

def load_qimage_for_thumbnailing(path: str, target_width: int = 0) -> QImage | None:
    reader = None
    buffer = None # Keep buffer in scope

    if '|' in path:
        image_data = get_image_data_from_zip(path)
        if image_data:
            reader, buffer = qimage_reader_from_bytes(image_data)
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

    return image

def get_image_aspect_ratio(path: str) -> float | None:
    """Gets the aspect ratio (height / width) of an image efficiently. Returns None if it fails."""
    reader = None
    buffer = None
    if '|' in path:
        image_data = get_image_data_from_zip(path)
        if image_data:
            from src.utils.img_utils import qimage_reader_from_bytes
            reader, buffer = qimage_reader_from_bytes(image_data)
    else:
        if not os.path.isfile(path) or any(path.lower().endswith(ext) for ext in VIDEO_EXTS):
            return None
        reader = QImageReader(path)
        
    if reader and reader.canRead():
        size = reader.size()
        if size.isValid() and size.width() > 0:
            return size.height() / size.width()
            
    return None

def get_chapter_number(path):
    """Extract a representative number for sorting from a filename or path."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name
    
    # 1. Prioritize page index (p, page, pg)
    page_match = re.search(r'(?:page|pg|p)\.?\s*(\d+(?:\.\d+)?)', name, re.IGNORECASE)
    if page_match:
        return float(page_match.group(1))

    # 2. Priority: Chapter (ch, chapter, c)
    ch_match = re.search(r'(?:chapter|ch|c)\.?\s*(\d+(?:\.\d+)?)', name, re.IGNORECASE)
    if ch_match:
        return float(ch_match.group(1))
    
    # 3. Fallback to the first number found
    # Using float finding logic to handle decimals
    numbers = re.findall(r'\d+(?:\.\d+)?', name)
    return float(numbers[0]) if numbers else float('inf')

def extract_page_number(filename: str) -> int:
    """Extract the page number from a filename."""
    stem = Path(filename).stem
    numbers = re.findall(r'\d+', stem)
    if numbers:
        return int(numbers[-1])
    return -1
    

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}

def _get_first_media_path(chapter_input):
    if not chapter_input:
        return None
        
    # Handle dict input from Library Scanner
    if isinstance(chapter_input, dict):
        path_str = chapter_input.get('path', '')
    else:
        path_str = str(chapter_input)
        
    if not path_str:
        return None
        
    # Handle Virtual Paths (archive.zip|subfolder)
    if '|' in path_str:
        archive_path, internal_path = split_virtual_path(path_str)
        internal_path = internal_path.strip('/').replace('\\', '/')
        archive_ext = Path(archive_path).suffix.lower()
        
        try:
            # 1. Handle Zip/CBZ with encoding support
            if archive_ext in {'.zip', '.cbz'}:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    namelist = []
                    for info in zf.infolist():
                        name = decode_zip_filename(info.filename, info.flag_bits)
                        namelist.append((name, info.filename))
                    
                    # Filter for files within the internal_path
                    valid_files = []
                    for decoded_name, original_name in namelist:
                        decoded_norm = decoded_name.strip('/').replace('\\', '/')
                        if not internal_path or decoded_norm.startswith(internal_path + '/'):
                            rel = decoded_norm[len(internal_path):].strip('/') if internal_path else decoded_norm
                            if rel and '/' not in rel: # Direct child
                                if (decoded_norm.lower().endswith(IMG_EXTS) or decoded_norm.lower().endswith(tuple(VIDEO_EXTS))) and not decoded_norm.startswith('__MACOSX'):
                                    valid_files.append(decoded_name)
                    
                    valid_files.sort()
                    if valid_files:
                        return f"{archive_path}|{valid_files[0]}"

            # 2. Fallback to SevenZipHandler
            from src.utils.archive_utils import SevenZipHandler
            if SevenZipHandler.is_available():
                files = SevenZipHandler.list_files(archive_path)
                valid_files = []
                for f in files:
                    f_norm = f.strip('/').replace('\\', '/')
                    if not internal_path or f_norm.startswith(internal_path + '/'):
                        rel = f_norm[len(internal_path):].strip('/') if internal_path else f_norm
                        if rel and '/' not in rel:
                            if (f_norm.lower().endswith(IMG_EXTS) or f_norm.lower().endswith(tuple(VIDEO_EXTS))) and not f_norm.startswith('__MACOSX'):
                                valid_files.append(f)
                
                valid_files.sort()
                if valid_files:
                    return f"{archive_path}|{valid_files[0]}"
        except Exception as e:
            print(f"Error resolving virtual path {path_str}: {e}")
            return None

    # Handle Normal Paths
    path_obj = Path(path_str)
    # If it's an archive file (not a virtual path yet)
    if path_obj.suffix.lower() in ARCHIVE_EXTS:
        if not os.path.isfile(path_str): # Check if the archive file actually exists
            return None
        # Re-use the virtual path logic for the root
        return _get_first_media_path(f"{path_str}|")
            
    # 2. Handle Directories
    elif path_obj.is_dir():
        valid_exts = IMG_EXTS + tuple(VIDEO_EXTS)
        try:
            media_files = [p for p in sorted(path_obj.iterdir()) if p.suffix.lower() in valid_exts and p.is_file()]
            if media_files:
                return str(media_files[0])
        except Exception as e:
            print(f"Error scanning directory {path_str}: {e}")
            
    # 3. Handle Direct Video/Image Files
    elif path_obj.suffix.lower() in (IMG_EXTS + tuple(VIDEO_EXTS)):
        return path_str

    return None

def segment_image_by_black_lines(image_path: str) -> List[dict]:
    """
    Segments an image into multiple parts based on black lines.
    Returns a list of dictionaries, each containing the coordinates for each segmented part.
    """
    try:
        # Load the image using Unicode-safe read
        img = imread_unicode(image_path)
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
        # Load the image using Unicode-safe read
        img = imread_unicode(image_path)
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