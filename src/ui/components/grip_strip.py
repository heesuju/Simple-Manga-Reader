from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt

GRIP_W = 6


class GripStrip(QWidget):
    """Thin vertical bar used to collapse/expand side panels."""

    def __init__(self, on_toggle, parent=None):
        super().__init__(parent)
        self.on_toggle = on_toggle
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(GRIP_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Toggle panel")
        self._set_hovered(False)

    def _set_hovered(self, hovered: bool):
        color = "rgba(255, 255, 255, 70)" if hovered else "rgba(255, 255, 255, 20)"
        self.setStyleSheet(f"GripStrip {{ background-color: {color}; }}")

    def enterEvent(self, event):
        self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovered(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_toggle()
        super().mousePressEvent(event)
