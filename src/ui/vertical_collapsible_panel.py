from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame
from PyQt6.QtCore import Qt, QTimer

class VerticalScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

class VerticalCollapsiblePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(200)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_content)

    def show_content(self):
        self.hide_timer.stop()
        self.setVisible(True)
        self.setVisible(True)

    def hide_content(self):
        self.setVisible(False)
        self.setVisible(False)

    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hide_timer.start()
        super().leaveEvent(event)
