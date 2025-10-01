
from PyQt6.QtWidgets import QPushButton, QSizePolicy
from PyQt6.QtCore import pyqtSignal

class TokenWidget(QPushButton):
    remove_requested = pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(f"{text} ✕", parent)
        self.text = text
        self.setStyleSheet("QPushButton { background-color: #E0E0E0; border-radius: 5px; padding: 2px 5px; } QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.clicked.connect(self.emit_remove_request)

    def emit_remove_request(self):
        self.remove_requested.emit(self.text)
