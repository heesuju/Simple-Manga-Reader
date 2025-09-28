from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QEvent
from PyQt6.QtGui import QPixmap, QMouseEvent, QPainter, QColor, QFont
from pathlib import Path

class ClickableLabel(QWidget):
    clicked = pyqtSignal(object, int)

    def __init__(self, path: object, index: int, item_type: str):
        super().__init__()
        self.path = path
        self.index = index
        self.item_type = item_type
        self.pixmap = None
        self.hovered = False

        if isinstance(path, str) and '|' in path:
            self.display_name = Path(path.split('|')[1]).name
        else:
            self.display_name = path.get("name")

        self.setFixedSize(150, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def setPixmap(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.update()

    def enterEvent(self, event: QEvent):
        self.hovered = True
        self.update()

    def leaveEvent(self, event: QEvent):
        self.hovered = False
        self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path, self.index)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw thumbnail
        if self.pixmap:
            painter.drawPixmap(self.rect(), self.pixmap)

        # Draw overlay on hover
        if self.hovered:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.display_name)

        # Draw icon
        self._draw_icon(painter)

    def _draw_icon(self, painter: QPainter):
        icon_size = 32
        padding = 5
        icon_rect = self.rect().adjusted(
            self.width() - icon_size - padding,
            self.height() - icon_size - padding,
            -padding,
            -padding,
        )

        painter.setPen(Qt.GlobalColor.white)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRect(icon_rect)

        if self.item_type == 'folder':
            self._draw_folder_icon(painter, icon_rect)
        elif self.item_type == 'image':
            self._draw_image_icon(painter, icon_rect)
        elif self.item_type == 'zip':
            self._draw_zip_icon(painter, icon_rect)

    def _draw_folder_icon(self, painter: QPainter, rect):
        # A simple folder shape
        painter.setPen(Qt.GlobalColor.white)
        painter.setBrush(Qt.GlobalColor.yellow)
        
        folder_body = rect.adjusted(2, 8, -2, -2)
        painter.drawRect(folder_body)
        
        folder_tab = rect.adjusted(2, 2, -rect.width() // 2, - (rect.height() - 8))
        painter.drawRect(folder_tab)


    def _draw_image_icon(self, painter: QPainter, rect):
        # A simple mountain landscape
        painter.setPen(Qt.GlobalColor.white)
        
        # Sun
        painter.setBrush(Qt.GlobalColor.yellow)
        sun_rect = rect.adjusted(5, 5, -15, -15)
        painter.drawEllipse(sun_rect)

        # Mountains
        painter.setBrush(QColor(139, 69, 19)) # SaddleBrown
        
        # Triangle 1
        poly1 = [
            rect.bottomLeft(),
            rect.center(),
            rect.bottomRight()
        ]
        painter.drawPolygon(poly1)

    def _draw_zip_icon(self, painter: QPainter, rect):
        # A simple zip file icon
        painter.setPen(Qt.GlobalColor.white)
        painter.setBrush(QColor(150, 150, 150)) # Gray
        painter.drawRect(rect)

        # Zipper
        painter.setPen(Qt.GlobalColor.black)
        zipper_rect = rect.adjusted(rect.width() // 2 - 2, 2, -(rect.width() // 2 - 2), -2)
        painter.drawRect(zipper_rect)
        for i in range(4, rect.height() - 4, 4):
            painter.drawLine(zipper_rect.left(), rect.top() + i, zipper_rect.right(), rect.top() + i)