from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel
)
from PyQt6.QtGui import QPixmap, QMouseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QMargins
from src.utils.img_utils import crop_pixmap

class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, index, text, show_label=True, fixed_width=None, parent=None):
        super().__init__(parent)
        self.index = index
        self.fixed_width = fixed_width
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.image_container = QWidget()
        self.image_container.setObjectName("image_container")

        self.image_label = QLabel(self.image_container)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.text_label = QLabel(text, self.image_container)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not show_label:
            self.text_label.hide()

        if self.fixed_width is None:
            self.image_container.setFixedSize(100, 140)
            self.image_label.setFixedSize(100, 140)
            self.text_label.setGeometry(0, 120, 100, 20)

        self._hover = False
        self._selected = False
        self._update_style()

        self.layout.addWidget(self.image_container)

    def _update_margins(self, margins:QMargins):
        self.layout.setContentsMargins(margins)

    def _update_style(self):
        border_style = "border: 2px solid transparent;"
        if self._selected:
            border_style = "border: 2px solid rgba(74, 134, 232, 180);"
        elif self._hover:
            border_style = "border: 2px solid rgba(100, 100, 100, 180);"
        self.image_container.setStyleSheet(f"QWidget#image_container {{ {border_style} }}")

        if self._selected:
            if self._hover:
                bg = "rgba(74, 134, 232, 220)"  # brighter blue
            else:
                bg = "rgba(74, 134, 232, 180)"  # normal blue
        else:
            if self._hover:
                bg = "rgba(0, 0, 0, 180)"       # darker black
            else:
                bg = "rgba(0, 0, 0, 120)"       # normal black

        self.text_label.setStyleSheet(f"""
            background-color: {bg};
            color: white;
            font-size: 10px;
            border-radius: 0px;
        """)

    def enterEvent(self, event):
        self._hover = True
        self._update_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._update_style()
        super().leaveEvent(event)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        return super().mousePressEvent(ev)

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        
        if self.fixed_width is not None:
            self.image_label.setPixmap(pixmap)
            self.image_container.setFixedSize(pixmap.size())
            self.image_label.setFixedSize(pixmap.size())
            self.text_label.setGeometry(0, pixmap.height() - 20, pixmap.width(), 20)
        else:
            cropped = crop_pixmap(pixmap, 100, 140)
            self.image_label.setPixmap(cropped)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()