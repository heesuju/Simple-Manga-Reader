from typing import List
import zipfile
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QFrame, QScrollArea, QSizePolicy, QPinchGesture
)
from PyQt6.QtGui import QPixmap, QKeySequence, QPainter, QShortcut, QMouseEvent
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QRunnable, QObject, QThreadPool, QMargins
from src.ui.collapsible_panel import CollapsiblePanel
from src.ui.image_view import ImageView
import re
import zipfile
import io
from pathlib import Path
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtCore import Qt, QSize, QBuffer, QByteArray
from src.enums import ViewMode
from typing import List
from pathlib import Path
from PyQt6.QtGui import QImageReader
from collections import Counter
from src.utils.img_utils import get_image_size, get_image_ratio

def get_common_size_ratio(paths:List) -> tuple[float, float]:
    """Return the most common ratio among the list of images(10 max)."""
    sizes = [get_image_size(path) for path in paths[:10]]
    if not sizes:
        return (0, 0), 0.0, 0.0

    counter = Counter(sizes)
    w_counter = Counter([w for w, h in sizes])
    most_common_size, count = counter.most_common(1)[0]
    most_common_width, width_count = w_counter.most_common(1)[0]
    w, h = most_common_size
    ratio = get_image_ratio(w, h)
    percentage = round(count / len(sizes), 2)
    width_percentage = round(width_count / len(sizes), 2)
    return most_common_size, ratio, percentage, width_percentage

def get_default_view_mode(paths:List)->bool:
    """Return whether the images in the same folder is part of a manga by checking if most page ratios are the same"""
    size, ratio, percentage, w_percentage = get_common_size_ratio(paths) 
    if percentage > 0.7:
        if ratio > 0.6:
            return ViewMode.SINGLE
        elif ratio > 0.3 and ratio < 0.4:
            return ViewMode.STRIP
    elif w_percentage > 0.7:
        return ViewMode.STRIP
    else:
        return ViewMode.NONE
    
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