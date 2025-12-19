from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QMenu, QGraphicsBlurEffect, QGraphicsOpacityEffect, QCheckBox
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QFontMetrics, QPainter, QPainterPath, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QMargins, QPropertyAnimation, QSize, QEasingCurve, QRect, QParallelAnimationGroup
from src.utils.img_utils import crop_pixmap, get_chapter_number
from src.ui.info_dialog import InfoDialog
import os
import sys
import subprocess

class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(self, series, library_manager, parent=None, show_chapter_number=False):
        super().__init__(parent)
        self.series = series
        self.library_manager = library_manager
        self.show_chapter_number = show_chapter_number
        self.is_in_selection_mode = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.image_container = QWidget()
        self.image_container.setObjectName("image_container")
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(True)

        self.original_size = QSize(160, 260)
        self.image_container_size = QSize(150, 210)
        self.setFixedSize(self.original_size)
        self.image_container.setFixedSize(self.image_container_size)
        self.image_label.setGeometry(QRect(5, 10, self.image_container_size.width(), self.image_container_size.height()))

        self.info_layout = QHBoxLayout()
        self.name_label = QLabel()
        self.name_label.setWordWrap(True)

        font_metrics = QFontMetrics(self.name_label.font())
        line_height = font_metrics.height()
        max_height = line_height * 2
        self.name_label.setMaximumHeight(max_height)

        self._update_text()

        self.info_layout.addWidget(self.name_label)

        self.layout.addWidget(self.image_container)
        self.layout.addLayout(self.info_layout)

        self.checkbox = QCheckBox(self)
        self.checkbox.setGeometry(12, 14, 20, 20)
        self.checkbox.hide()

        self._hover = False
        self._selected = False
        self.image_container.setStyleSheet(f"QWidget#image_container {{ border: 2px solid transparent; border-radius: 10px; background-color: transparent; }}")

        self.setup_animation()

        if self.show_chapter_number:
            self.chapter_label = QLabel(self)
            self.chapter_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; border-radius: 5px; padding: 2px;")
            self.chapter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.chapter_label.hide()

    def set_selection_mode(self, enabled):
        self.is_in_selection_mode = enabled
        if enabled:
            self.checkbox.show()
            self.checkbox.raise_()
        else:
            self.checkbox.hide()
            self.checkbox.setChecked(False)

    def is_selected(self):
        return self.checkbox.isChecked()

    def set_chapter_number(self, series_obj):
        if not self.show_chapter_number or 'last_read_chapter' not in series_obj or not series_obj['last_read_chapter']:
            return

        chapter_path = series_obj['last_read_chapter']
        chapter_number = get_chapter_number(chapter_path)

        if chapter_number is not None and chapter_number != float('inf'):
            self.chapter_label.setText(f"Ch{chapter_number:02}")
            self.chapter_label.adjustSize()
            self.chapter_label.move(self.image_container.width() - self.chapter_label.width() - 5, 5)
            self.chapter_label.show()
            self.chapter_label.raise_()
        else:
             self.chapter_label.hide()

    def setup_animation(self):
        # Grow animation
        self.anim_group_grow = QParallelAnimationGroup(self)
        self.anim_group_shrink = QParallelAnimationGroup(self)

        # Image label animation
        scale_factor = 1.05
        grown_width = int(self.image_container_size.width() * scale_factor)
        grown_height = int(self.image_container_size.height() * scale_factor)

        original_x = 5
        original_y = 10

        original_rect = QRect(original_x, original_y, self.image_container_size.width(), self.image_container_size.height())
        grown_rect = QRect(
            original_x - (grown_width - self.image_container_size.width()) // 2,
            original_y - (grown_height - self.image_container_size.height()) // 2,
            grown_width,
            grown_height
        )

        anim_img_grow = QPropertyAnimation(self.image_label, b"geometry")
        anim_img_grow.setDuration(150)
        anim_img_grow.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim_img_grow.setStartValue(original_rect)
        anim_img_grow.setEndValue(grown_rect)
        self.anim_group_grow.addAnimation(anim_img_grow)

        anim_img_shrink = QPropertyAnimation(self.image_label, b"geometry")
        anim_img_shrink.setDuration(150)
        anim_img_shrink.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim_img_shrink.setStartValue(grown_rect)
        anim_img_shrink.setEndValue(original_rect)
        self.anim_group_shrink.addAnimation(anim_img_shrink)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        open_action = menu.addAction("Open Folder")
        remove_action = menu.addAction("Remove")
        get_info_action = menu.addAction("Get Info")
        action = menu.exec(event.globalPos())

        if action == open_action:
            self.open_folder()
        elif action == remove_action:
            self.remove_requested.emit(self.series)
        elif action == get_info_action:
            self.get_info()

    def get_info(self):
        dialog = InfoDialog(self.series, self.library_manager, self)
        if dialog.exec():
            # If dialog was accepted (Save clicked), reload the series data
            self.reload_series()

    def reload_series(self):
        """Reloads the series data from the database and updates the UI."""
        updated_series = self.library_manager.get_series_by_path(self.series['path'])
        if updated_series:
            self.series = updated_series
            self._update_text()
            
            # Reload cover image
            if self.series.get('cover_image') and os.path.exists(self.series['cover_image']):
                pixmap = QPixmap(self.series['cover_image'])
                if not pixmap.isNull():
                    self.set_pixmap(pixmap)

    def _update_text(self):
        """Updates the name label with truncation logic."""
        font_metrics = QFontMetrics(self.name_label.font())
        line_height = font_metrics.height()
        max_height = line_height * 2
        
        text = self.series['name']
        rect = font_metrics.boundingRect(0, 0, 130, max_height * 2, Qt.TextFlag.TextWordWrap, text)
        if rect.height() > max_height:
            end = len(text)
            while end > 0:
                end -= 1
                rect = font_metrics.boundingRect(0, 0, 130, max_height, Qt.TextFlag.TextWordWrap, text[:end] + '...')
                if rect.height() <= max_height:
                    text = text[:end] + '...'
                    break
        self.name_label.setText(text)

    def open_folder(self):
        if sys.platform == "win32":
            os.startfile(self.series['path'])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.series['path']])
        else:
            subprocess.Popen(["xdg-open", self.series['path']])

    def enterEvent(self, event):
        self._hover = True
        self.image_label.raise_()
        if self.show_chapter_number and hasattr(self, 'chapter_label'):
            self.chapter_label.raise_()
        if self.is_in_selection_mode:
            self.checkbox.raise_()
        self.anim_group_shrink.stop()
        self.anim_group_grow.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.anim_group_grow.stop()
        self.anim_group_shrink.start()
        super().leaveEvent(event)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if self.is_in_selection_mode:
            self.checkbox.toggle()
            return  # Consume the event
        
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.series)
        
        super().mousePressEvent(ev)

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        
        cropped = crop_pixmap(pixmap, self.image_container_size.width(), self.image_container_size.height())
        
        rounded = QPixmap(cropped.size())
        rounded.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, cropped.width(), cropped.height(), 8, 8)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()

        self.image_label.setPixmap(rounded)

    def set_as_missing(self):
        pixmap = QPixmap(self.image_container_size)
        pixmap.fill(QColor("gray"))

        painter = QPainter(pixmap)
        
        # Draw a large question mark
        font = painter.font()
        font.setPointSize(60)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "?")

        # Draw "Missing" text at the bottom
        font.setPointSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(200, 200, 200))
        text_rect = pixmap.rect().adjusted(0, 0, 0, -10) # Margin from bottom
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, "Missing")
        
        painter.end()

        self.image_label.setPixmap(pixmap)

