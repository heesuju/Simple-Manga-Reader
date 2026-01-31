import zipfile
from pathlib import Path
import io
import os
from PIL import Image, ImageQt, ImageFilter

from PyQt6.QtCore import Qt, QRunnable, pyqtSlot, QObject, pyqtSignal, QRectF, QBuffer, QIODevice
from PyQt6.QtGui import QPixmap, QImage, QPainter, QFont, QColor, QTextOption

from src.utils.img_utils import get_chapter_number, get_image_data_from_zip
from src.core.alt_manager import AltManager

VIDEO_EXTS = {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}

class ArchiveExtractionSignals(QObject):
    finished = pyqtSignal(str, bool) # archive_path, success

class ArchiveExtractionWorker(QRunnable):
    def __init__(self, archive_path: str):
        super().__init__()
        self.archive_path = archive_path
        self.signals = ArchiveExtractionSignals()

    @pyqtSlot()
    def run(self):
        from src.utils.archive_utils import SevenZipHandler
        success = SevenZipHandler.extract_all(self.archive_path)
        self.signals.finished.emit(self.archive_path, success)

class AnimationFrameLoaderSignals(QObject):
    finished = pyqtSignal(dict)

class AnimationFrameLoaderWorker(QRunnable):
    def __init__(self, path: str, image_data: bytes):
        super().__init__()
        self.path = path
        self.image_data = image_data
        self.signals = AnimationFrameLoaderSignals()

    @pyqtSlot()
    def run(self):
        """
        Load frames for animated images (GIF, animated WEBP). If the path refers to a video
        file (mp4, webm, etc.) we skip processing here — videos are handled by the media player.
        """
        frames = []
        duration = 100

        # Normalize path for zip entries like "archive.zip|file.ext"
        path_lower = self.path.lower() if isinstance(self.path, str) else ""
        if '|' in path_lower:
            ext = Path(path_lower.split('|', 1)[1]).suffix.lower()
        else:
            ext = Path(path_lower).suffix.lower()

        # Skip video formats entirely (they are handled by the video playback path)
        if ext in VIDEO_EXTS:
            result = {"path": self.path, "frames": [], "duration": duration}
            self.signals.finished.emit(result)
            return

        try:
            img = Image.open(io.BytesIO(self.image_data))
            if getattr(img, "is_animated", False):
                # prefer duration from info if available
                duration = img.info.get('duration', 100)
                for i in range(getattr(img, "n_frames", 1)):
                    try:
                        img.seek(i)
                        q_image = ImageQt.toqpixmap(img)
                        frames.append(q_image)
                    except Exception:
                        # If a single frame fails, skip it and continue
                        continue
        except Exception:
            frames = []  # Return empty list on error

        result = {
            "path": self.path,
            "frames": frames,
            "duration": duration
        }
        self.signals.finished.emit(result)

class ChapterLoaderSignals(QObject):
    finished = pyqtSignal(dict)

class ChapterLoaderWorker(QRunnable):
    def __init__(self, manga_dir: str, series_path: str, start_from_end: bool, load_pixmap_func):
        super().__init__()
        self.manga_dir = manga_dir
        self.series_path = series_path
        self.start_from_end = start_from_end
        self.load_pixmap = load_pixmap_func
        self.signals = ChapterLoaderSignals()

    @pyqtSlot()
    def run(self):
        if not self.manga_dir:
            self.signals.finished.emit({
                "manga_dir": None,
                "images": [],
                "initial_index": 0,
                "initial_pixmap": None,
                "start_from_end": False
            })
            return

        # Perform I/O and grouping in the worker thread
        image_list = self._get_image_list()
        image_list = sorted(image_list, key=get_chapter_number)

        alt_config = AltManager.load_alts(self.series_path)
        chapter_name = Path(self.manga_dir).name
        chapter_alts = alt_config.get(chapter_name, {})
        grouped_pages = AltManager.group_images(image_list, chapter_alts)

        initial_index = 0
        if self.start_from_end:
            initial_index = len(grouped_pages) - 1

        initial_pixmap = None
        if grouped_pages:
            if 0 <= initial_index < len(grouped_pages):
                # Use the first variant of the page
                page = grouped_pages[initial_index]
                candidate = page.images[0]
                suffix = Path(candidate.split('|')[-1]).suffix.lower()
                if suffix in IMAGE_EXTS:
                    # Resolve path for extraction cache if needed
                    resolved = self._resolve_path(candidate)
                    initial_pixmap = self.load_pixmap(resolved)
                else:
                    initial_pixmap = None

        # Background Spread Detection
        self._detect_spreads_in_background(grouped_pages)

        result = {
            "manga_dir": self.manga_dir,
            "images": grouped_pages,
            "initial_index": initial_index,
            "initial_pixmap": initial_pixmap,
            "start_from_end": self.start_from_end
        }
        self.signals.finished.emit(result)

    def _resolve_path(self, path: str) -> str:
        """Helper to resolve virtual paths to extraction cache for background processing."""
        if not path or '|' not in path:
            return path
            
        archive_path, internal = path.split('|', 1)
        from src.utils.archive_utils import SevenZipHandler
        extract_dir = SevenZipHandler.get_extract_dir(archive_path)
        target = extract_dir / internal.replace('/', os.sep).replace('\\', os.sep)
        
        if target.exists():
            return str(target)
            
        return path

    def _detect_spreads_in_background(self, pages):
        """Perform spread detection using extracted files or ZipFile data."""
        if not pages:
            return

        import os
        from PyQt6.QtGui import QImageReader
        import zipfile
        from src.utils.img_utils import ZIP_CACHE

        # 1. Samples
        ratios = []
        sample_indices = []
        if len(pages) > 0:
            indices = list(range(len(pages)))
            import random
            sample_indices = random.sample(indices, min(5, len(indices)))
            
        for i in sample_indices:
            page = pages[i]
            path = page.path
            resolved = self._resolve_path(path)
            
            if '|' not in resolved:
                reader = QImageReader(resolved)
                size = reader.size()
                if size.isValid() and size.height() > 0:
                    ratios.append(size.width() / size.height())
            else:
                zip_path, internal = path.split('|', 1)
                zf = ZIP_CACHE.get_zip(zip_path)
                if zf:
                    try:
                        with zf.open(internal) as f:
                            data = f.read()
                            buffer = QBuffer()
                            buffer.setData(data)
                            buffer.open(QBuffer.OpenModeFlag.ReadOnly)
                            reader = QImageReader(buffer)
                            size = reader.size()
                            if size.isValid() and size.height() > 0:
                                ratios.append(size.width() / size.height())
                    except Exception:
                        pass

        if not ratios:
            return

        median_ratio = sorted(ratios)[len(ratios) // 2]
        if median_ratio == 0: return
        is_consistent = all(abs(r - median_ratio) / median_ratio < 0.1 for r in ratios)
        if not is_consistent: return

        spread_threshold = median_ratio * 1.5
        
        # 2. All pages
        for page in pages:
            if getattr(page, 'is_spread_explicit', False):
                continue
                
            path = page.path
            resolved = self._resolve_path(path)
            is_spread = False
            
            if '|' not in resolved:
                reader = QImageReader(resolved)
                size = reader.size()
                if size.isValid() and size.height() > 0:
                    is_spread = (size.width() / size.height()) > spread_threshold
            else:
                pass
            
            if is_spread != page.is_spread:
                page.is_spread = is_spread

    def _get_image_list(self):
        """
        Return list of media file paths (strings). For ZIPs we return "zip_path|entry"
        so upstream can detect zip entries. Include both images and videos.
        """
        if not self.manga_dir:
            return []
            
        path_str = str(self.manga_dir)
        valid_exts = tuple(list(IMAGE_EXTS) + list(VIDEO_EXTS))

        # Case 0: Virtual path (zip|subfolder)
        if '|' in path_str:
            zip_path, internal_prefix = path_str.split('|', 1)
            # Normalize internal prefix
            internal_prefix = internal_prefix.replace('\\', '/')
            if not internal_prefix.endswith('/'):
                internal_prefix += '/'
            
            files = []
            
            # Check extension
            ext = Path(zip_path).suffix.lower()
            if ext in {'.7z', '.rar', '.cbr', '.cb7'}:
                from src.utils.archive_utils import SevenZipHandler
                if SevenZipHandler.is_available():
                    all_files = SevenZipHandler.list_files(zip_path)
                    files = [f for f in all_files if f.replace('\\', '/').startswith(internal_prefix)]
            else:
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        files = [f for f in zf.namelist() if f.replace('\\', '/').startswith(internal_prefix)]
                except Exception:
                    files = []

            image_files = sorted([
                f for f in files
                if f.lower().endswith(valid_exts) and 
                   not f.startswith('__MACOSX') and 
                   Path(f).stem.lower() != 'cover' and
                   '/' not in f.replace('\\', '/')[len(internal_prefix):]
            ])
            # Return full virtual paths: zip_path|entry
            return [f"{zip_path}|{name}" for name in image_files]

        # Case 1: Full ZIP/CBZ file as chapter
        if path_str.lower().endswith(('.zip', '.cbz', '.7z', '.rar', '.cbr', '.cb7')):
            files = []
            ext = Path(path_str).suffix.lower()
            
            if ext in {'.7z', '.rar', '.cbr', '.cb7'}:
                from src.utils.archive_utils import SevenZipHandler
                if SevenZipHandler.is_available():
                    files = SevenZipHandler.list_files(path_str)
            else:
                try:
                    with zipfile.ZipFile(path_str, 'r') as zf:
                        files = zf.namelist()
                except zipfile.BadZipFile:
                    files = []

            image_files = sorted([
                f for f in files
                if f.lower().endswith(valid_exts) and not f.startswith('__MACOSX') and Path(f).stem.lower() != 'cover'
            ])
            return [f"{path_str}|{name}" for name in image_files]
        
        # Case 2: Directory chapter
        manga_path = Path(path_str)
        if manga_path.is_dir():
            files = []
            files.extend([str(p) for p in manga_path.iterdir() 
                          if p.suffix.lower() in valid_exts and p.is_file() and "_detached_" not in p.name and p.stem.lower() != 'cover'])
            return sorted(files)
            
        return []

class WorkerSignals(QObject):
    finished = pyqtSignal(int, QPixmap, int)

class PixmapLoader(QRunnable):
    def __init__(self, path: str, index: int, load_func, generation_id: int):
        super().__init__()
        self.path = path
        self.index = index
        self.load_func = load_func
        self.generation_id = generation_id
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        """
        For videos the load_func will likely return a null QPixmap.
        That's expected — callers should handle the absence of a pixmap (e.g. play video instead).
        """
        pixmap = self.load_func(self.path)
        self.signals.finished.emit(self.index, pixmap, self.generation_id)

class VideoFrameExtractorSignals(QObject):
    finished = pyqtSignal(str, QImage)

class VideoFrameExtractorWorker(QRunnable):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = VideoFrameExtractorSignals()

    @pyqtSlot()
    def run(self):
        try:
            import cv2
            cap = cv2.VideoCapture(self.path)
            if cap.isOpened():
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                # Grab the last frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count - 1))
                ret, frame = cap.read()
                if ret:
                    # Convert BGR to RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame.shape
                    # Robust bytes per line calculation
                    bytes_per_line = frame.strides[0]
                    q_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    # We must make a copy of the data, because 'frame' (numpy array) will be garbage collected
                    q_image = q_image.copy()
                    pass
                    self.signals.finished.emit(self.path, q_image)
                cap.release()
        except Exception as e:
            print(f"Error in async video extraction: {e}")

class VideoTimestampFrameExtractorSignals(QObject):
    finished = pyqtSignal(str, QImage, str) # source_path, image, save_path

class VideoTimestampFrameExtractorWorker(QRunnable):
    def __init__(self, path: str, timestamp_ms: int, save_path: str):
        super().__init__()
        self.path = path
        self.timestamp_ms = timestamp_ms
        self.save_path = save_path
        self.signals = VideoTimestampFrameExtractorSignals()

    @pyqtSlot()
    def run(self):
        try:
            import cv2
            cap = cv2.VideoCapture(self.path)
            if cap.isOpened():
                # Seek to specific timestamp
                cap.set(cv2.CAP_PROP_POS_MSEC, self.timestamp_ms)
                ret, frame = cap.read()
                if ret:
                    # Convert BGR to RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame.shape
                    bytes_per_line = frame.strides[0]
                    q_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    q_image = q_image.copy()
                    
                    self.signals.finished.emit(self.path, q_image, self.save_path)
                cap.release()
        except Exception as e:
            print(f"Error in async video timestamp extraction: {e}")

class AsyncLoaderSignals(QObject):
    finished = pyqtSignal(int, dict) # request_id, results {path: QImage}

class AsyncLoaderWorker(QRunnable):
    def __init__(self, request_id: int, paths: list[str]):
        super().__init__()
        self.request_id = request_id
        self.paths = paths
        self.signals = AsyncLoaderSignals()

    @pyqtSlot()
    def run(self):
        results = {}
        for path in self.paths:
            if not path: continue
            
            if path == "placeholder":
                # Create a small black image, will be resized by consumer
                img = QImage(1, 1, QImage.Format.Format_RGB32)
                img.fill(Qt.GlobalColor.black)
                results[path] = img
                continue
            
            try:
                image_data = None
                path_str = path
                crop = None
                
                if isinstance(path, str):
                    if path.endswith("_left"):
                        path_str = path[:-5]
                        crop = "left"
                    elif path.endswith("_right"):
                        path_str = path[:-6]
                        crop = "right"

                if '|' in path_str:
                    image_data = get_image_data_from_zip(path_str)
                elif os.path.exists(path_str):
                    pass # load directly
                
                q_image = QImage()
                if image_data:
                    q_image.loadFromData(image_data)
                elif os.path.exists(path_str):
                    q_image.load(path_str)
                
                if not q_image.isNull() and crop:
                    w = q_image.width()
                    h = q_image.height()
                    if crop == 'left':
                        q_image = q_image.copy(0, 0, w // 2, h)
                    elif crop == 'right':
                        q_image = q_image.copy(w // 2, 0, w // 2, h)

                if not q_image.isNull():
                    results[path] = q_image
                    
            except Exception as e:
                print(f"Error loading image async {path}: {e}")

        self.signals.finished.emit(self.request_id, results)

class ScaleSignals(QObject):
    finished = pyqtSignal(int, QPixmap)

class ScaleWorker(QRunnable):
    def __init__(self, original_pixmap: QPixmap, target_width: int, index: int):
        super().__init__()
        self.original_pixmap = original_pixmap
        self.target_width = target_width
        self.index = index
        self.signals = ScaleSignals()

    @pyqtSlot()
    def run(self):
        try:
            # Conversion to QImage might be needed for thread safety if QPixmap is not safe across threads in this context
            # deeper qt docs say QPixmap shouldn't be used in worker threads.
            # So we should convert to QImage in __init__ (main thread) or pass QImage.
            pass 
        except Exception:
            pass
            
        # Re-implementing __init__ to take QImage to be safe
        pass

# Redefining to be safe
class SafeScaleWorker(QRunnable):
    def __init__(self, image: QImage, target_width: int, index: int):
        super().__init__()
        self.image = image
        self.target_width = target_width
        self.index = index
        self.signals = ScaleSignals()

    @pyqtSlot()
    def run(self):
        if self.image.isNull():
            return
            
        scaled_image = self.image.scaledToWidth(self.target_width, Qt.TransformationMode.SmoothTransformation)
        # We need to convert back to pixmap on the main thread, so we send QImage back? 
        # Actually QPixmap constructor must be called on main thread. 
        # So we should return QImage or QPixmap? 
        # Standard: Worker does image processing (QImage), Signal emits QImage, Slot updates UI (QPixmap).
        
        # But QPixmap cannot be passed through signal if it was created in thread without complications? Easiest is emit QImage.
        pass

# Final implementation attempt
class AsyncScaleSignals(QObject):
    finished = pyqtSignal(int, QImage, int)

class AsyncScaleWorker(QRunnable):
    def __init__(self, image: QImage, target_width: int, index: int, generation_id: int, high_quality: bool = True):
        super().__init__()
        self.q_image = image.copy() 
        self.target_width = target_width
        self.index = index
        self.generation_id = generation_id
        self.high_quality = high_quality
        self.signals = AsyncScaleSignals()

    @pyqtSlot()
    def run(self):
        if self.q_image.isNull():
            return

        try:
            if not self.high_quality:
                # Fast path using Qt
                scaled = self.q_image.scaledToWidth(self.target_width, Qt.TransformationMode.SmoothTransformation)
                self.signals.finished.emit(self.index, scaled, self.generation_id)
                return

            # 1. Convert QImage -> PIL
            buffer = QBuffer()
            buffer.open(QBuffer.OpenModeFlag.ReadWrite)
            self.q_image.save(buffer, "PNG")
            pil_img = Image.open(io.BytesIO(buffer.data().data()))
            
            w_percent = (self.target_width / float(pil_img.size[0]))
            h_size = int((float(pil_img.size[1]) * float(w_percent)))
            
            pil_resized = pil_img.resize((self.target_width, h_size), Image.Resampling.LANCZOS)

            pil_resized = pil_resized.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=3))
            
            q_out = ImageQt.ImageQt(pil_resized).copy()
            
            self.signals.finished.emit(self.index, q_out, self.generation_id)
            
        except Exception as e:
            print(f"Error in scale: {e}")
            # Fallback to Qt scaling if PIL fails
            scaled = self.q_image.scaledToWidth(self.target_width, Qt.TransformationMode.SmoothTransformation)
            self.signals.finished.emit(self.index, scaled, self.generation_id)

