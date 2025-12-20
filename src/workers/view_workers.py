import zipfile
from pathlib import Path
import io
import os
from PIL import Image, ImageQt

from PyQt6.QtCore import Qt, QRunnable, pyqtSlot, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from src.utils.img_utils import get_chapter_number, get_image_data_from_zip
from src.core.alt_manager import AltManager

# New: list of video extensions we want to treat as media
VIDEO_EXTS = {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}

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
        # Perform blocking I/O and processing here
        image_list = self._get_image_list()
        image_list = sorted(image_list, key=get_chapter_number)

        # Group images here in the worker thread
        # 1. Load alt config
        alt_config = AltManager.load_alts(self.series_path)
        # 2. Extract chapter specific config
        chapter_name = Path(self.manga_dir).name
        chapter_alts = alt_config.get(chapter_name, {})
        # 3. Group
        grouped_pages = AltManager.group_images(image_list, chapter_alts)

        initial_index = 0
        if self.start_from_end:
            initial_index = len(grouped_pages) - 1

        initial_pixmap = None
        if grouped_pages:
            if 0 <= initial_index < len(grouped_pages):
                # only try to load a pixmap if the initial item is an image (not a video)
                # Use the first variant of the page
                page = grouped_pages[initial_index]
                candidate = page.images[0]
                # candidate may be "zip|name" or a file path
                suffix = Path(candidate.split('|')[-1]).suffix.lower()
                if suffix in IMAGE_EXTS:
                    initial_pixmap = self.load_pixmap(candidate)
                else:
                    initial_pixmap = None

        result = {
            "manga_dir": self.manga_dir,
            "images": grouped_pages, # Now passing Page objects
            "initial_index": initial_index,
            "initial_index": initial_index,
            "initial_pixmap": initial_pixmap,
            "start_from_end": self.start_from_end
        }
        self.signals.finished.emit(result)

    def _get_image_list(self):
        """
        Return list of media file paths (strings). For ZIPs we return "zip_path|entry"
        so upstream can detect zip entries. Include both images and videos.
        """
        if not self.manga_dir:
            return []
        manga_path = Path(self.manga_dir)
        if self.manga_dir.endswith('.zip'):
            try:
                with zipfile.ZipFile(self.manga_dir, 'r') as zf:
                    # include image and video extensions
                    valid_exts = tuple(list(IMAGE_EXTS) + list(VIDEO_EXTS))
                    image_files = sorted([f for f in zf.namelist()
                                          if f.lower().endswith(valid_exts) and not f.startswith('__MACOSX') and Path(f).stem.lower() != 'cover'])
                    return [f"{self.manga_dir}|{name}" for name in image_files]
            except zipfile.BadZipFile:
                return []
        elif manga_path.is_dir():
            exts = IMAGE_EXTS.union(VIDEO_EXTS)
            files = []
            
            # 1. Scan root
            files.extend([str(p) for p in manga_path.iterdir() 
                          if p.suffix.lower() in exts and p.is_file() and "_detached_" not in p.name and p.stem.lower() != 'cover'])
            
            # 2. Scan alts/ subfolder
            alts_dir = manga_path / "alts"
            if alts_dir.exists() and alts_dir.is_dir():
                files.extend([str(p) for p in alts_dir.iterdir() 
                              if p.suffix.lower() in exts and p.is_file() and "_detached_" not in p.name and p.stem.lower() != 'cover'])
                
            return sorted(files)
        return []

class WorkerSignals(QObject):
    finished = pyqtSignal(int, QPixmap)

class PixmapLoader(QRunnable):
    def __init__(self, path: str, index: int, load_func):
        super().__init__()
        self.path = path
        self.index = index
        self.load_func = load_func
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        """
        For videos the load_func will likely return a null QPixmap.
        That's expected — callers should handle the absence of a pixmap (e.g. play video instead).
        """
        pixmap = self.load_func(self.path)
        self.signals.finished.emit(self.index, pixmap)

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
    def __init__(self, image: QImage, target_width: int, index: int, generation_id: int):
        super().__init__()
        self.image = image
        self.target_width = target_width
        self.index = index
        self.generation_id = generation_id
        self.signals = AsyncScaleSignals()

    @pyqtSlot()
    def run(self):
        if self.image.isNull():
            return
        scaled = self.image.scaledToWidth(self.target_width, Qt.TransformationMode.SmoothTransformation)
        self.signals.finished.emit(self.index, scaled, self.generation_id)
