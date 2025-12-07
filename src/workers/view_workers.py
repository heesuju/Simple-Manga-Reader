import zipfile
from pathlib import Path
import io
import os
from PIL import Image, ImageQt

from PyQt6.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap

from src.utils.img_utils import get_chapter_number, get_image_data_from_zip

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
        frames = []
        duration = 100
        try:
            img = Image.open(io.BytesIO(self.image_data))
            if img.is_animated:
                duration = img.info.get('duration', 100)
                for i in range(img.n_frames):
                    img.seek(i)
                    q_image = ImageQt.toqpixmap(img)
                    frames.append(q_image)
        except Exception:
            frames = [] # Return empty list on error

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
                initial_pixmap = self.load_pixmap(image_list[initial_index])

        result = {
            "manga_dir": self.manga_dir,
            "images": image_list,
            "initial_index": initial_index,
            "initial_pixmap": initial_pixmap
        }
        self.signals.finished.emit(result)

    def _get_image_list(self):
        if not self.manga_dir:
            return []
        manga_path = Path(self.manga_dir)
        if self.manga_dir.endswith('.zip'):
            try:
                with zipfile.ZipFile(self.manga_dir, 'r') as zf:
                    image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                    return [f"{self.manga_dir}|{name}" for name in image_files]
            except zipfile.BadZipFile:
                return []
        elif manga_path.is_dir():
            exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
            return [str(p) for p in sorted(manga_path.iterdir()) if p.suffix.lower() in exts and p.is_file()]
        return []

class WorkerSignals(QObject):
    finished = pyqtSignal(int, QPixmap)

class PixmapLoader(QRunnable):
    def __init__(self, path: str, index: int, reader_view):
        super().__init__()
        self.path = path
        self.index = index
        self.reader_view = reader_view
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        pixmap = self.reader_view._load_pixmap(self.path)
        self.signals.finished.emit(self.index, pixmap)