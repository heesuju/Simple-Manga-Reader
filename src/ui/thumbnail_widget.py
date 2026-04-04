from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QMenu, QCheckBox
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QFontMetrics, QPainter, QPainterPath, QColor, QLinearGradient
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QSize, QEasingCurve, QRect, QParallelAnimationGroup, pyqtProperty
from pathlib import Path
from src.utils.img_utils import crop_pixmap, get_chapter_number, load_thumbnail_from_zip
from src.utils.archive_utils import ZIP_EXTS
from src.ui.info_dialog import InfoDialog
import os
import sys
import subprocess

class ShineLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._shine_opacity = 0.0
        
        # Animation for the shine effect
        self.shine_animation = QPropertyAnimation(self, b"shine_opacity")
        self.shine_animation.setDuration(200)
        self.shine_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    @pyqtProperty(float)
    def shine_opacity(self):
        return self._shine_opacity

    @shine_opacity.setter
    def shine_opacity(self, value):
        self._shine_opacity = value
        self.update()

    def set_hovered(self, hovered):
        if self._hovered == hovered:
            return
        
        self._hovered = hovered
        self.shine_animation.stop()
        if hovered:
            self.shine_animation.setEndValue(1.0)
        else:
            self.shine_animation.setEndValue(0.0)
        self.shine_animation.start()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._shine_opacity > 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Use the same rounding as the image for clipping
            path = QPainterPath()
            path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)
            painter.setClipPath(path)

            # 1. Surface Gloss (Top-down)
            surface_gradient = QLinearGradient(0, 0, 0, self.height())
            surface_gradient.setColorAt(0.0, QColor(255, 255, 255, int(30 * self._shine_opacity)))
            surface_gradient.setColorAt(0.5, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), surface_gradient)

            # 2. Corner Reflection (Top-Right)
            reflection_gradient = QLinearGradient(self.width(), 0, 0, self.height())
            reflection_gradient.setColorAt(0.0, QColor(255, 255, 255, int(130 * self._shine_opacity)))
            reflection_gradient.setColorAt(0.4, QColor(255, 255, 255, int(50 * self._shine_opacity)))
            reflection_gradient.setColorAt(0.6, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), reflection_gradient)
            
            # 3. Glass Border
            pen_color = QColor(255, 255, 255, int(80 * self._shine_opacity))
            painter.setPen(pen_color)
            border_path = QPainterPath()
            border_path.addRoundedRect(1, 1, self.width()-2, self.height()-2, 7, 7)
            painter.setClipPath(path)
            painter.drawPath(border_path)

            painter.end()


THUMB_W = 160
THUMB_H = 260
IMG_W = 150
IMG_H = 210
RECENT_THUMB_H = THUMB_H // 2 + 20  # slightly taller than half for label breathing room


class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    rescan_requested = pyqtSignal(object)
    clear_cache_requested = pyqtSignal(object)

    def __init__(self, series, library_manager, parent=None, height=THUMB_H):
        super().__init__(parent)
        self.series = series
        self.library_manager = library_manager
        self.is_in_selection_mode = False
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(6)

        self.image_container = QWidget()
        self.image_container.setObjectName("image_container")

        # Parent to self so it can expand beyond the container bounds
        self.image_label = ShineLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(True)

        ratio = height / THUMB_H
        self.original_size = QSize(THUMB_W, height)
        self.image_container_size = QSize(IMG_W, int(IMG_H * ratio))
        self.setFixedSize(self.original_size)
        self.image_container.setFixedSize(self.image_container_size)

        # Original geometry relative to ThumbnailWidget
        self.image_label.setGeometry(5, 10, self.image_container_size.width(), self.image_container_size.height())

        self.info_layout = QHBoxLayout()
        self.name_label = QLabel()
        self.name_label.setWordWrap(True)

        font_metrics = QFontMetrics(self.name_label.font())
        line_height = font_metrics.height()
        max_height = line_height * 2
        self.name_label.setMaximumHeight(max_height)

        self._update_text()

        self.info_layout.addWidget(self.name_label)

        self.main_layout.addWidget(self.image_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.main_layout.addLayout(self.info_layout)

        self.checkbox = QCheckBox(self)
        self.checkbox.setGeometry(12, 14, 20, 20)
        self.checkbox.hide()

        self._hover = False
        self._selected = False
        self.image_container.setStyleSheet(f"QWidget#image_container {{ border: 2px solid transparent; border-radius: 10px; background-color: transparent; }}")

        self.setup_animation()


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

    def set_progress(self, series_obj):
        chapter_path = series_obj.get('last_read_chapter')
        if not chapter_path:
            return
        chapters = series_obj.get('chapters', [])
        chapter_idx = next((i for i, ch in enumerate(chapters) if ch.get('path') == chapter_path), -1)
        if chapter_idx != -1:
            page = series_obj.get('last_read_page', 0) or 0
            self.name_label.setText(f"Ch {chapter_idx + 1} · p {page + 1}")

    def setup_animation(self):
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
        rescan_action = menu.addAction("Rescan Series")
        clear_cache_action = menu.addAction("Clear Extraction Cache")
        remove_action = menu.addAction("Remove")
        get_info_action = menu.addAction("Edit Info")
        action = menu.exec(event.globalPos())

        if action == open_action:
            self.open_folder()
        elif action == rescan_action:
            self.rescan_requested.emit(self.series)
        elif action == clear_cache_action:
            self.clear_cache_requested.emit(self.series)
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
            cover_path = self.series.get('cover_image')
            if cover_path and os.path.exists(cover_path):
                pixmap = None
                if Path(cover_path).suffix.lower() in ZIP_EXTS:
                    q_img = load_thumbnail_from_zip(cover_path)
                    if q_img and not q_img.isNull():
                        pixmap = QPixmap.fromImage(q_img)
                else:
                    pixmap = QPixmap(cover_path)
                    
                if pixmap and not pixmap.isNull():
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
        self.image_label.set_hovered(True)
        if self.is_in_selection_mode:
            self.checkbox.raise_()
        self.anim_group_shrink.stop()
        self.anim_group_grow.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.image_label.set_hovered(False)
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
        w, h = self.image_container_size.width(), self.image_container_size.height()

        base = QPixmap(self.image_container_size)
        base.fill(QColor("gray"))

        painter = QPainter(base)
        font = painter.font()
        font.setPointSize(60)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(base.rect(), Qt.AlignmentFlag.AlignCenter, "?")

        font.setPointSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(base.rect().adjusted(0, 0, 0, -10), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, "Missing")
        painter.end()

        rounded = QPixmap(self.image_container_size)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 8, 8)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, base)
        painter.end()

        self.image_label.setPixmap(rounded)

