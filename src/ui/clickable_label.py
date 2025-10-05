from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import pyqtSignal

class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def mousePressEvent(self, event):
        self.clicked.emit()
