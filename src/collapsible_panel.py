from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame
from PyQt6.QtCore import Qt, QTimer

class HorizontalScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def wheelEvent(self, event):
        if event.angleDelta().y() != 0:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

class CollapsiblePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.content_area = HorizontalScrollArea()
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
