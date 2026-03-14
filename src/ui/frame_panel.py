import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QImage
from src.workers.view_workers import VideoBatchFrameExtractorWorker

THUMB_W = 120
THUMB_H = 160
PAGE_SIZE = 50

class FrameThumbnail(QWidget):
    """Single clickable video frame thumbnail."""
    def __init__(self, parent, frame_index, on_click=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.frame_index = frame_index
        self.on_click = on_click

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(THUMB_H + 30)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(THUMB_W, THUMB_H)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: rgba(255, 255, 255, 10);")
        layout.addWidget(self.thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel(f"Frame {frame_index}")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("color: white; font-size: 11px;")
        layout.addWidget(self.name_label)

    def set_qimage(self, qimage: QImage):
        if qimage and not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            self.thumb_label.setPixmap(pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_click:
            self.on_click(self.frame_index)
        super().mousePressEvent(event)


class FramePanel(QWidget):
    """Vertical panel showing video frames with paging."""
    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None, thread_pool=None):
        super().__init__(parent)
        self.thread_pool = thread_pool
        self.video_path = None
        self.total_frames = 0
        self.current_page = 0
        self.thumbnails = {} # {frame_index: FrameThumbnail}

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            FramePanel {
                background-color: rgba(0, 0, 0, 170);
                border: none;
            }
        """)
        self.setFixedWidth(THUMB_W + 40)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Pagination controls
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("<")
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.clicked.connect(self.prev_page)
        
        self.page_label = QLabel("0/0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("color: white; font-weight: bold;")
        
        self.next_btn = QPushButton(">")
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.clicked.connect(self.next_page)

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.page_label, 1)
        nav_layout.addWidget(self.next_btn)
        main_layout.addLayout(nav_layout)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        main_layout.addWidget(self.scroll_area, 1)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        self.hide()

    def set_video(self, path, total_frames):
        self.video_path = path
        self.total_frames = total_frames
        self.current_page = 0
        self._update_ui()

    def _update_ui(self):
        if not self.video_path or self.total_frames <= 0:
            self.hide()
            return

        total_pages = (self.total_frames + PAGE_SIZE - 1) // PAGE_SIZE
        self.page_label.setText(f"{self.current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

        self._clear_thumbnails()
        
        # Determine range for current page
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, self.total_frames)
        
        indices = list(range(start_idx, end_idx))
        
        for idx in indices:
            thumb = FrameThumbnail(self.scroll_content, idx, on_click=self.seek_requested.emit)
            self.scroll_layout.addWidget(thumb)
            self.thumbnails[idx] = thumb

        # Trigger async extraction for this batch
        if self.thread_pool:
            worker = VideoBatchFrameExtractorWorker(self.video_path, indices, THUMB_W, THUMB_H)
            worker.signals.finished.connect(self._on_frames_extracted)
            self.thread_pool.start(worker)

    def _on_frames_extracted(self, path, results, start_idx, end_idx):
        if path != self.video_path:
            return
        
        for idx, qimage in results.items():
            if idx in self.thumbnails:
                self.thumbnails[idx].set_qimage(qimage)

    def _clear_thumbnails(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.thumbnails.clear()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_ui()

    def next_page(self):
        total_pages = (self.total_frames + PAGE_SIZE - 1) // PAGE_SIZE
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._update_ui()
