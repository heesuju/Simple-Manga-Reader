from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QPushButton, QHBoxLayout, QFrame
import os
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal

from src.core.item_loader import ItemLoader
from src.ui.reader_view import ReaderView
from src.utils.img_utils import crop_pixmap
from pathlib import Path
from src.utils.img_utils import get_chapter_number

class ChapterListItemWidget(QWidget):
    chapter_selected = pyqtSignal(object)

    def __init__(self, chapter, series, chapter_name, library_manager, parent=None):
        super().__init__(parent)
        self.chapter = chapter
        self.series = series
        self.library_manager = library_manager

        self.layout = QHBoxLayout(self)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(75, 38)
        self.name_label = QLabel(chapter_name)

        self.layout.addWidget(self.thumbnail_label)
        self.layout.addWidget(self.name_label)
        self.layout.addStretch()

    def set_pixmap(self, pixmap):
        cropped_pixmap = crop_pixmap(pixmap, 75, 38)
        self.thumbnail_label.setPixmap(cropped_pixmap)

    def mousePressEvent(self, event):
        self.chapter_selected.emit(self.chapter)

class ChapterListView(QWidget):
    back_to_library = pyqtSignal()
    open_reader = pyqtSignal(object, object)

    def __init__(self, series, library_manager, parent=None):
        super().__init__(parent)
        self.series = series
        self.library_manager = library_manager
        self.parent_grid = parent
        self.chapter_widgets = []
        self.threadpool = QThreadPool()

        self.layout = QVBoxLayout(self)

        # Top layout with series info
        top_layout = QHBoxLayout()
        self.series_thumbnail = QLabel()
        self.series_thumbnail.setFixedSize(150, 200)
        full_cover_path = os.path.join(series['root_dir'], series['cover_image'])
        cover_pixmap = QPixmap(full_cover_path)
        self.series_thumbnail.setPixmap(cover_pixmap.scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.series_name_label = QLabel(series['name'])
        self.series_name_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        top_layout.addWidget(self.series_thumbnail)
        top_layout.addWidget(self.series_name_label)
        top_layout.addStretch()

        self.back_btn = QPushButton("Back to Library")
        self.back_btn.clicked.connect(self.go_back)

        self.layout.addLayout(top_layout)
        self.layout.addWidget(self.back_btn)

        self.scroll_area = QScrollArea()
        self.scroll_content = QWidget()
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        self.load_chapters()

    def load_chapters(self):
        chapters = self.series.get('chapters', [])
        for i, chapter in enumerate(chapters):
            item_widget = ChapterListItemWidget(chapter, self.series, f"Ch {i+1}", self.library_manager, self)
            item_widget.chapter_selected.connect(self.on_chapter_selected)
            self.list_layout.addWidget(item_widget)
            self.chapter_widgets.append(item_widget)

            # Add a divider line
            if i < len(chapters) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                self.list_layout.addWidget(line)

        loader = ItemLoader(chapters, 0, item_type='chapter', thumb_width=150, thumb_height=75, root_dir=self.series['root_dir'])
        loader.signals.item_loaded.connect(self.on_thumbnail_loaded)
        self.threadpool.start(loader)

    def on_chapter_selected(self, chapter):
        self.open_reader.emit(self.series, chapter)

    def on_thumbnail_loaded(self, pixmap, item, index, generation, item_type):
        if index < len(self.chapter_widgets):
            self.chapter_widgets[index].set_pixmap(pixmap)

    def go_back(self):
        self.back_to_library.emit()