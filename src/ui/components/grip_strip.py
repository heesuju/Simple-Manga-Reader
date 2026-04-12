from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QFont, QColor

GRIP_W = 18


class GripStrip(QWidget):
    """Thin vertical bar used to collapse/expand side panels, now with tab support."""
    tab_clicked = pyqtSignal(int)

    def __init__(self, on_toggle, parent=None, tabs=None):
        super().__init__(parent)
        self.on_toggle = on_toggle
        self.tabs = tabs or [] # List of strings like ["ALT", "INFO"]
        self.active_tab_index = 0
        self._hovered_tab_index = -1

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(GRIP_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setStyleSheet("GripStrip { background-color: rgba(255, 255, 255, 10); }")

    def setActiveTab(self, index):
        if 0 <= index < len(self.tabs):
            self.active_tab_index = index
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.tabs:
            # Traditional slim grip look
            painter = QPainter(self)
            color = QColor(255, 255, 255, 70 if self.underMouse() else 20)
            painter.fillRect(self.rect().adjusted(6, 40, -6, -40), color)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        h = self.height()
        tab_h = h / len(self.tabs)
        
        font = QFont("Arial", 8, QFont.Weight.Bold)
        painter.setFont(font)

        for i, label in enumerate(self.tabs):
            # Tab rect
            rect = self.rect()
            rect.setTop(int(i * tab_h))
            rect.setBottom(int((i + 1) * tab_h))
            
            # Draw background for hovered or active tab
            is_active = (i == self.active_tab_index and not self.parent()._collapsed)
            is_hovered = (i == self._hovered_tab_index)
            
            if is_active:
                painter.fillRect(rect, QColor(255, 255, 255, 50))
            elif is_hovered:
                painter.fillRect(rect, QColor(255, 255, 255, 30))

            # Draw vertical text
            painter.save()
            painter.translate(rect.center())
            painter.rotate(-90)
            
            text_rect = painter.fontMetrics().boundingRect(label)
            text_rect.moveCenter(QPoint(0, 0))
            
            painter.setPen(QColor(255, 255, 255, 220 if (is_active or is_hovered) else 120))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()

            # Draw separator
            if i < len(self.tabs) - 1:
                painter.setPen(QColor(255, 255, 255, 20))
                painter.drawLine(0, int((i + 1) * tab_h), GRIP_W, int((i + 1) * tab_h))

    def mouseMoveEvent(self, event):
        if not self.tabs:
            super().mouseMoveEvent(event)
            return
            
        old_hover = self._hovered_tab_index
        h = self.height()
        tab_h = h / len(self.tabs)
        self._hovered_tab_index = int(event.position().y() / tab_h)
        
        if old_hover != self._hovered_tab_index:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered_tab_index = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.tabs:
                self.on_toggle()
            else:
                h = self.height()
                tab_h = h / len(self.tabs)
                index = int(event.position().y() / tab_h)
                
                # If same tab clicked while expanded, toggle collapse
                if index == self.active_tab_index and not self.parent()._collapsed:
                    self.on_toggle()
                else:
                    self.active_tab_index = index
                    self.tab_clicked.emit(index)
                    if self.parent()._collapsed:
                        self.on_toggle()
                    self.update()
        super().mousePressEvent(event)
