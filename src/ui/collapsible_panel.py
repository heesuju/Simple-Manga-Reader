from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QFrame
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from src.ui.input_label import InputLabel
from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path

class HorizontalScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def wheelEvent(self, event):
        if event.angleDelta().y() != 0:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

class CollapsiblePanel(QWidget):
    def __init__(self, parent=None, name:str=""):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("CollapsiblePanel { background-color: rgba(0, 0, 0, 170); }")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        self.input_container = QWidget()
        self.input_layout = QHBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.input_container)

        self.content_area = HorizontalScrollArea()
        self.content_area.setStyleSheet("background: transparent;")
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)
        self.content_area.setVisible(False)

        self.layout.addWidget(self.content_area, 1)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(200)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_content)

        self.input_label = InputLabel(name, 0,0)
        self.input_layout.addWidget(self.input_label, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.input_container.setVisible(True)
        
        self.thumbnails_widget = QWidget()
        self.thumbnails_widget.setStyleSheet("background: transparent;")
        self.thumbnails_layout = QHBoxLayout(self.thumbnails_widget)
        self.thumbnails_layout.setSpacing(10)
        self.thumbnails_layout.setContentsMargins(0,0,0,0)
        self.thumbnails_layout.addStretch()
        self.content_area.setWidget(self.thumbnails_widget)

        self.raise_()

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

    def _load_thumbnail(self, path: str) -> QPixmap | None:
        crop = None
        if path.endswith("_left"):
            path = path[:-5]
            crop = "left"
        elif path.endswith("_right"):
            path = path[:-6]
            crop = "right"

        if '|' in path:
            return load_thumbnail_from_virtual_path(virtual_path=path, crop=crop)
        elif path.endswith('.zip'):
            return load_thumbnail_from_zip(path=path)
        else:
            return load_thumbnail_from_path(path=path, crop=crop)