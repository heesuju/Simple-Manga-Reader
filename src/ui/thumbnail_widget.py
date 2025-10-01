from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QMenu
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal, QMargins
from src.utils.img_utils import crop_pixmap
from src.ui.info_dialog import InfoDialog
import os
import sys
import subprocess

class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(self, series, library_manager, parent=None):
        super().__init__(parent)
        self.series = series
        self.library_manager = library_manager
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        self.image_container = QWidget()
        self.image_container.setObjectName("image_container")
        self.image_label = QLabel(self.image_container)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_container.setFixedSize(150, 210)
        self.image_label.setFixedSize(150, 210)

        self.info_layout = QHBoxLayout()
        self.name_label = QLabel()
        self.name_label.setWordWrap(True)

        font_metrics = QFontMetrics(self.name_label.font())
        line_height = font_metrics.height()
        max_height = line_height * 2
        self.name_label.setMaximumHeight(max_height)

        text = self.series['name']
        rect = font_metrics.boundingRect(0, 0, 130, max_height * 2, Qt.TextFlag.TextWordWrap, text)
        if rect.height() > max_height:
            # Find the right place to cut the text
            end = len(text)
            while end > 0:
                end -= 1
                rect = font_metrics.boundingRect(0, 0, 130, max_height, Qt.TextFlag.TextWordWrap, text[:end] + '...')
                if rect.height() <= max_height:
                    text = text[:end] + '...'
                    break
        self.name_label.setText(text)

        self.menu_button = QPushButton("\u22EE") # Vertical ellipsis
        self.menu_button.setFlat(True)
        self.menu_button.setStyleSheet("border: none; font-size: 20px;")
        self.menu_button.setFixedSize(30, 30)
        self.menu_button.clicked.connect(self.show_menu)

        self.info_layout.addWidget(self.name_label)
        self.info_layout.addWidget(self.menu_button)

        self.layout.addWidget(self.image_container)
        self.layout.addLayout(self.info_layout)
        self.setFixedSize(160, 260)

        self._hover = False
        self._selected = False
        self._update_style()

    def show_menu(self):
        menu = QMenu(self)
        open_action = menu.addAction("Open Folder")
        remove_action = menu.addAction("Remove")
        get_info_action = menu.addAction("Get Info")
        action = menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

        if action == open_action:
            self.open_folder()
        elif action == remove_action:
            self.remove_requested.emit(self.series)
        elif action == get_info_action:
            self.get_info()

    def get_info(self):
        dialog = InfoDialog(self.series, self.library_manager, self)
        dialog.exec()

    def open_folder(self):
        if sys.platform == "win32":
            os.startfile(self.series['path'])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.series['path']])
        else:
            subprocess.Popen(["xdg-open", self.series['path']])

    def _update_style(self):
        border_style = "border: 2px solid transparent;"
        if self._selected:
            border_style = "border: 2px solid rgba(74, 134, 232, 180);"
        elif self._hover:
            border_style = "border: 2px solid rgba(100, 100, 100, 180);"
        self.image_container.setStyleSheet(f"QWidget#image_container {{ {border_style} }}")

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
            self.clicked.emit(self.series)
        return super().mousePressEvent(ev)

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        
        cropped = crop_pixmap(pixmap, 150, 210)
        self.image_label.setPixmap(cropped)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()