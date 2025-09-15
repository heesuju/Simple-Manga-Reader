from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QThread, pyqtSignal

class ImageLoader(QThread):
    imageLoaded = pyqtSignal(QPixmap, int)

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths

    def run(self):
        for i, p in enumerate(self.paths):
            pix = QPixmap(p)
            self.imageLoaded.emit(pix, i)
            # small interval
            self.msleep(2)