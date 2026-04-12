from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor

GRIP_W = 6

class GripStrip(QWidget):
    """Ultra-slim vertical bar used to toggle side panels."""
    def __init__(self, on_toggle, parent=None):
        super().__init__(parent)
        self.on_toggle = on_toggle
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(GRIP_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        # Very subtle default background
        self.setStyleSheet("GripStrip { background-color: rgba(255, 255, 255, 5); }")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a very subtle vertical line or pill to indicate it's a grip
        is_hovered = self.underMouse()
        
        opacity = 120 if is_hovered else 30
        color = QColor(255, 255, 255, opacity)
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Center the grip line
        grip_rect = QRect(2, 40, GRIP_W - 4, self.height() - 80)
        painter.drawRoundedRect(grip_rect, 1, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_toggle()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)
