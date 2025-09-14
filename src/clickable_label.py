
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QEvent
from PyQt6.QtGui import QPixmap, QMouseEvent, QColor, QPainter, QFont, QBrush, QResizeEvent
from pathlib import Path

class ClickableLabel(QWidget):
    clicked = pyqtSignal(Path, int)

    def __init__(self, folder_path: Path, index:int):
        super().__init__()
        self.folder_path = folder_path
        self.index = index
        self.setFixedSize(150, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Base image
        self.pixmap_label = QLabel(self)
        self.pixmap_label.setGeometry(0, 0, self.width(), self.height())
        self.pixmap_label.setScaledContents(True)

        # Overlay label (hidden by default)
        self.overlay_label = QLabel(folder_path.name, self)
        self.overlay_label.setStyleSheet(
            "background-color: rgba(0,0,0,120); color: white; padding: 2px;"
        )
        self.overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay_label.hide()

        # Enable mouse hover events
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # Position overlay initially
        self._position_overlay()

    def _position_overlay(self):
        """Position overlay at the bottom of the widget dynamically."""
        overlay_height = 25
        self.overlay_label.setGeometry(0, self.height() - overlay_height, self.width(), overlay_height)

    def resizeEvent(self, event: QResizeEvent):
        """Keep overlay at the bottom if widget is resized."""
        self.pixmap_label.setGeometry(0, 0, self.width(), self.height())
        self._position_overlay()
        super().resizeEvent(event)

    def setPixmap(self, pixmap: QPixmap):
        self.pixmap_label.setPixmap(pixmap)

    def enterEvent(self, event: QEvent):
        self.overlay_label.show()

    def leaveEvent(self, event: QEvent):
        self.overlay_label.hide()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.folder_path, self.index)