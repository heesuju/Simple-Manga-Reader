from PyQt6.QtGui import QImage
from PyQt6.QtCore import pyqtSignal, QRunnable, QObject

class ThumbnailWorker(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(int, QImage)

    def __init__(self, index, path, load_thumb_func):
        super().__init__()
        self.index = index
        self.path = path
        self.load_thumb = load_thumb_func # Returns QImage
        self.signals = self.Signals()

    def run(self):
        thumb = self.load_thumb(self.path) # QImage
        if thumb and not thumb.isNull():
            self.signals.finished.emit(self.index, thumb)


class ChapterThumbnailWorker(QRunnable):
    """Like ThumbnailWorker but resolves the first media path from a chapter object
    in the worker thread, avoiding blocking zip I/O on the main thread."""

    class Signals(QObject):
        finished = pyqtSignal(int, QImage)

    def __init__(self, index, chapter, load_thumb_func):
        super().__init__()
        self.index = index
        self.chapter = chapter
        self.load_thumb = load_thumb_func
        self.signals = self.Signals()

    def run(self):
        from src.utils.img_utils import _get_first_media_path
        path = _get_first_media_path(self.chapter)
        if not path:
            return
        thumb = self.load_thumb(path)
        if thumb and not thumb.isNull():
            self.signals.finished.emit(self.index, thumb)
