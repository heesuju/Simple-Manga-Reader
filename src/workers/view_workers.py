import zipfile
from pathlib import Path
import io
import os
from PIL import Image, ImageQt

from PyQt6.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from src.utils.img_utils import get_chapter_number, get_image_data_from_zip

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
    def __init__(self, manga_dir: str, start_from_end: bool, load_pixmap_func):
        super().__init__()
        self.manga_dir = manga_dir
        self.start_from_end = start_from_end
        self.load_pixmap = load_pixmap_func
        self.signals = ChapterLoaderSignals()

    @pyqtSlot()
    def run(self):
        # Perform blocking I/O and processing here
        image_list = self._get_image_list()
        image_list = sorted(image_list, key=get_chapter_number)

        initial_index = 0
        if self.start_from_end:
            initial_index = len(image_list) - 1

        initial_pixmap = None
        if image_list:
            if 0 <= initial_index < len(image_list):
                # only try to load a pixmap if the initial item is an image (not a video)
                candidate = image_list[initial_index]
                # candidate may be "zip|name" or a file path
                suffix = Path(candidate.split('|')[-1]).suffix.lower()
                if suffix in IMAGE_EXTS:
                    initial_pixmap = self.load_pixmap(candidate)
                else:
                    initial_pixmap = None

        result = {
            "manga_dir": self.manga_dir,
            "images": image_list,
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
                                          if f.lower().endswith(valid_exts) and not f.startswith('__MACOSX')])
                    return [f"{self.manga_dir}|{name}" for name in image_files]
            except zipfile.BadZipFile:
                return []
        elif manga_path.is_dir():
            exts = IMAGE_EXTS.union(VIDEO_EXTS)
            files = []
            
            # 1. Scan root
            files.extend([str(p) for p in manga_path.iterdir() if p.suffix.lower() in exts and p.is_file()])
            
            # 2. Scan alts/ subfolder
            alts_dir = manga_path / "alts"
            if alts_dir.exists() and alts_dir.is_dir():
                files.extend([str(p) for p in alts_dir.iterdir() if p.suffix.lower() in exts and p.is_file()])
                
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
