from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import pyqtSignal, QRunnable, QObject

class ThumbnailWorker(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(int, QPixmap)

    def __init__(self, index, path, load_thumb_func):
        super().__init__()
        self.index = index
        self.path = path
        self.load_thumb = load_thumb_func
        self.signals = self.Signals()

    def run(self):
        thumb = self.load_thumb(self.path)
        if thumb:
            self.signals.finished.emit(self.index, thumb)
