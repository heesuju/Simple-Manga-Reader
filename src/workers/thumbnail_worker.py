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
