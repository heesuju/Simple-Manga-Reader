from typing import List
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import pyqtSignal, QRunnable, QObject
from src.enums import ViewMode
from typing import List

def get_default_view_mode(paths:List)->bool:
    """Return whether the images in the same folder is part of a manga by checking if most page ratios are the same"""
    return ViewMode.SINGLE
    