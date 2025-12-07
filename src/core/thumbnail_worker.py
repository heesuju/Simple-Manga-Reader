from typing import List
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import pyqtSignal, QRunnable, QObject
from src.enums import ViewMode
from typing import List

def get_default_view_mode(paths:List)->bool:
    """Return whether the images in the same folder is part of a manga by checking if most page ratios are the same"""
    return ViewMode.SINGLE
    
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