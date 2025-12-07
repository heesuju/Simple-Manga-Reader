import zipfile
from pathlib import Path

from PyQt6.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap
from src.utils.img_utils import get_chapter_number

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