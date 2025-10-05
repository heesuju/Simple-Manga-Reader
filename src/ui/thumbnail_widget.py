from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QMenu, QGraphicsBlurEffect, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QPixmap, QMouseEvent, QFontMetrics, QPainter, QPainterPath
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
        self.image_label.setGeometry(QRect(5, 5, self.image_container_size.width(), self.image_container_size.height()))

        # Shine effect
        self.shine_label = QLabel(self)
        self.shine_label.setStyleSheet("background-color: qradialgradient(cx:1, cy:0, radius: 1, fx:1, fy:0, stop:0 rgba(255, 255, 255, 100), stop:0.5 rgba(255, 255, 255, 0));")
        
        self.shine_opacity_effect = QGraphicsOpacityEffect(self.shine_label)
        self.shine_label.setGraphicsEffect(self.shine_opacity_effect)
        self.shine_opacity_effect.setOpacity(0)

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
            end = len(text)
            while end > 0:
                end -= 1
                rect = font_metrics.boundingRect(0, 0, 130, max_height, Qt.TextFlag.TextWordWrap, text[:end] + '...')
                if rect.height() <= max_height:
                    text = text[:end] + '...'
                    break
        self.name_label.setText(text)

        self.info_layout.addWidget(self.name_label)

        self.layout.addWidget(self.image_container)
        self.layout.addLayout(self.info_layout)

        self._hover = False
        self._selected = False
        self.image_container.setStyleSheet(f"QWidget#image_container {{ border: 2px solid transparent; border-radius: 10px; background-color: transparent; }}")

        self.setup_animation()

        if self.show_chapter_number:
            self.chapter_label = QLabel(self)
            self.chapter_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; border-radius: 5px; padding: 2px;")
            self.chapter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.chapter_label.hide()

    def set_chapter_number(self, series_obj):
        if not self.show_chapter_number or 'last_read_chapter' not in series_obj or not series_obj['last_read_chapter']:
            return

        chapter_path = series_obj['last_read_chapter']
        chapter_number = get_chapter_number(chapter_path)

        if chapter_number is not None:
            self.chapter_label.setText(f"Ch{chapter_number:02}")
            self.chapter_label.adjustSize()
            self.chapter_label.move(self.image_container.width() - self.chapter_label.width() - 5, 5)
            self.chapter_label.show()
            self.chapter_label.raise_()

    def setup_animation(self):
        # Grow animation
        self.anim_group_grow = QParallelAnimationGroup(self)
        self.anim_group_shrink = QParallelAnimationGroup(self)

        # Image label animation
        anim_img_grow = QPropertyAnimation(self.image_label, b"geometry")
        anim_img_grow.setDuration(150)
        anim_img_grow.setEasingCurve(QEasingCurve.Type.InOutQuad)
        original_rect = QRect(5, 5, self.image_container_size.width(), self.image_container_size.height())
        grown_rect = QRect(
            5 - int(self.image_container_size.width() * 0.05),
            5 - int(self.image_container_size.height() * 0.05),
            int(self.image_container_size.width() * 1.1),
            int(self.image_container_size.height() * 1.1)
        )
        anim_img_grow.setStartValue(original_rect)
        anim_img_grow.setEndValue(grown_rect)
        self.anim_group_grow.addAnimation(anim_img_grow)

        anim_img_shrink = QPropertyAnimation(self.image_label, b"geometry")
        anim_img_shrink.setDuration(150)
        anim_img_shrink.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim_img_shrink.setStartValue(grown_rect)
        anim_img_shrink.setEndValue(original_rect)
        self.anim_group_shrink.addAnimation(anim_img_shrink)

        # Shine label animation
        shine_size = int(self.image_container_size.width() * 0.8)
        original_shine_rect = QRect(original_rect.right() - shine_size, original_rect.top(), shine_size, shine_size)
        grown_shine_size = int(grown_rect.width() * 0.8)
        grown_shine_rect = QRect(grown_rect.right() - grown_shine_size, grown_rect.top(), grown_shine_size, grown_shine_size)

        anim_shine_grow = QPropertyAnimation(self.shine_label, b"geometry")
        anim_shine_grow.setDuration(150)
        anim_shine_grow.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim_shine_grow.setStartValue(original_shine_rect)
        anim_shine_grow.setEndValue(grown_shine_rect)
        self.anim_group_grow.addAnimation(anim_shine_grow)

        anim_shine_shrink = QPropertyAnimation(self.shine_label, b"geometry")
        anim_shine_shrink.setDuration(150)
        anim_shine_shrink.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim_shine_shrink.setStartValue(grown_shine_rect)
        anim_shine_shrink.setEndValue(original_shine_rect)
        self.anim_group_shrink.addAnimation(anim_shine_shrink)

        # Shine fade in/out
        self.anim_fade_in = QPropertyAnimation(self.shine_opacity_effect, b"opacity")
        self.anim_fade_in.setDuration(200)
        self.anim_fade_in.setStartValue(0)
        self.anim_fade_in.setEndValue(1)

        self.anim_fade_out = QPropertyAnimation(self.shine_opacity_effect, b"opacity")
        self.anim_fade_out.setDuration(200)
        self.anim_fade_out.setStartValue(1)
        self.anim_fade_out.setEndValue(0)

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
        dialog.exec()

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
        self.shine_label.raise_()
        if self.show_chapter_number and hasattr(self, 'chapter_label'):
            self.chapter_label.raise_()
        self.anim_group_shrink.stop()
        self.anim_group_grow.start()
        self.anim_fade_out.stop()
        self.anim_fade_in.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.anim_group_grow.stop()
        self.anim_group_shrink.start()
        self.anim_fade_in.stop()
        self.anim_fade_out.start()
        super().leaveEvent(event)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.series)
        return super().mousePressEvent(ev)

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        
        cropped = crop_pixmap(pixmap, self.image_container_size.width(), self.image_container_size.height())
        
        rounded = QPixmap(cropped.size())
        rounded.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, cropped.width(), cropped.height(), 0, 0)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()

        self.image_label.setPixmap(rounded)
