from PyQt6.QtWidgets import QWidget, QHBoxLayout, QScrollArea, QFrame
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

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.content_area = VerticalScrollArea()
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)
        self.content_area.setVisible(False)

        self.layout.addWidget(self.content_area)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(200)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_content)

    def set_content_widget(self, widget):
        self.content_area.setWidget(widget)

    def show_content(self):
        self.hide_timer.stop()
        self.content_area.setVisible(True)
        self.setVisible(True)

    def hide_content(self):
        self.content_area.setVisible(False)
        self.setVisible(False)

    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hide_timer.start()
        super().leaveEvent(event)
