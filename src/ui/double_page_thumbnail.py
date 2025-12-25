from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel
)
from PyQt6.QtGui import QPixmap, QMouseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QMargins
from src.utils.img_utils import crop_pixmap

class DoublePageThumbnail(QWidget):
    clicked = pyqtSignal(int)
    right_clicked = pyqtSignal(int)

    def __init__(self, index, text, show_label=True, parent=None, is_spread=False):
        super().__init__(parent)
        self.index = index
        self.is_spread = is_spread
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.image_container = QWidget()
        self.image_container.setObjectName("image_container")
        self.image_container.setFixedSize(200, 140)

        # Layout for images inside container
        self.images_layout = QHBoxLayout(self.image_container)
        self.images_layout.setContentsMargins(0, 0, 0, 0)
        self.images_layout.setSpacing(0)

        if self.is_spread:
            self.spread_label = QLabel(self.image_container)
            self.spread_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.spread_label.setScaledContents(False)
            self.images_layout.addWidget(self.spread_label)
        else:
            # Visual Left (First in LTR layout)
            self.visual_left_image = QLabel(self.image_container)
            self.visual_left_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.visual_left_image.setFixedSize(100, 140)
            self.visual_left_image.setStyleSheet("padding: 0px; margin: 0px; border: none;")
            self.images_layout.addWidget(self.visual_left_image)

            # Visual Right (Second in LTR layout)
            self.visual_right_image = QLabel(self.image_container)
            self.visual_right_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.visual_right_image.setFixedSize(100, 140)
            self.visual_right_image.setStyleSheet("padding: 0px; margin: 0px; border: none;")
            self.images_layout.addWidget(self.visual_right_image)

        self.text_label = QLabel(text, self.image_container)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not show_label:
            self.text_label.hide()
        
        self.text_label.raise_()
        self.text_label.move(0, 120)
        self.text_label.setFixedSize(200, 20)

        self.selection_overlay = QWidget(self.image_container)
        self.selection_overlay.setGeometry(0, 0, 200, 140)
        self.selection_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.selection_overlay.raise_()

        self._hover = False
        self._selected = False      
        self._edit_selected = False 
        self._update_style()

        self.layout.addWidget(self.image_container)

    def _update_style(self):
        border_style = "border: 2px solid transparent;"
        
        if self._edit_selected:
            border_style = "border: 2px solid #e74c3c;" 
        elif self._selected:
            border_style = "border: 2px solid rgba(74, 134, 232, 180);"
        elif self._hover:
            border_style = "border: 2px solid rgba(100, 100, 100, 180);"
            
        self.selection_overlay.setStyleSheet(f"background: transparent; {border_style}")
        self.image_container.setStyleSheet("QWidget#image_container { border: none; }")

        if self._edit_selected:
            bg = "#c0392b"
        elif self._selected:
            if self._hover:
                bg = "rgba(74, 134, 232, 220)" 
            else:
                bg = "rgba(74, 134, 232, 180)" 
        else:
            if self._hover:
                bg = "rgba(0, 0, 0, 180)"       
            else:
                bg = "rgba(0, 0, 0, 120)"       

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
        elif ev.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self.index)
        return super().mousePressEvent(ev)

    def set_visual_left_pixmap(self, pixmap: QPixmap):
        if not self.is_spread and hasattr(self, 'visual_left_image'):
             if pixmap.isNull(): return
             cropped = crop_pixmap(pixmap, 100, 140)
             self.visual_left_image.setPixmap(cropped)

    def set_visual_right_pixmap(self, pixmap: QPixmap):
        if not self.is_spread and hasattr(self, 'visual_right_image'):
             if pixmap.isNull(): return
             cropped = crop_pixmap(pixmap, 100, 140)
             self.visual_right_image.setPixmap(cropped)

    def set_spread_pixmap(self, pixmap: QPixmap):
        if self.is_spread and hasattr(self, 'spread_label'):
             if pixmap.isNull(): return
             cropped = crop_pixmap(pixmap, 200, 140)
             self.spread_label.setPixmap(cropped)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def set_edit_selected(self, selected: bool):
        self._edit_selected = selected
        self._update_style()
