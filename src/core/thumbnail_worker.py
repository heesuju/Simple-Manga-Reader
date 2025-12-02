from typing import List, Tuple
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import pyqtSignal, QRunnable, QObject
from src.enums import ViewMode
from typing import List
from collections import Counter
from src.utils.img_utils import get_image_size, get_image_ratio

def get_common_size_ratio(paths:List, tolerance: int = 2) -> Tuple[Tuple[int, int], float, float, float]:
    """Return the most common ratio among the list of images(10 max)."""
    sizes = [get_image_size(path) for path in paths[:10] if get_image_size(path) is not None]
    if not sizes:
        return (0, 0), 0.0, 0.0, 0.0
    
    def normalize_size(size):
        w, h = size
        return (round(w / tolerance) * tolerance, round(h / tolerance) * tolerance)
    
    norm_sizes = [normalize_size(size) for size in sizes]
    
    counter = Counter(norm_sizes)
    w_counter = Counter([w for w, h in norm_sizes])
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
        elif ratio > 0.3 and ratio < 0.5:
            return ViewMode.STRIP
    elif w_percentage > 0.7:
        return ViewMode.STRIP
    else:
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