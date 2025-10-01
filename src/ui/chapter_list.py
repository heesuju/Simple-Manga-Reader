from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QPushButton, QHBoxLayout, QFrame
import os
from PyQt6.QtGui import QPixmap, QPalette, QColor
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
        self.is_highlighted = False

        self.setAutoFillBackground(True)
        self.set_default_palette()

        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(10)
        self.chapter_number_label = QLabel()
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(75, 38)
        self.name_label = QLabel()
        self.page_count_label = QLabel()

        self.layout.addWidget(self.chapter_number_label)
        self.layout.addWidget(self.thumbnail_label)
        self.layout.addWidget(self.name_label)
        self.layout.addStretch()
        self.layout.addWidget(self.page_count_label)

        # Set content
        chapter_number = int(chapter_name.replace("Ch ", ""))
        self.chapter_number_label.setText(f'{chapter_number:02}')
        self.chapter_number_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px;")
        self.name_label.setText(Path(chapter['path']).name)

        self.update_page_count()

    def update_page_count(self):
        full_chapter_path = Path(self.chapter['path'])
        if full_chapter_path.exists() and full_chapter_path.is_dir():
            images = [p for p in full_chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} and 'cover' not in p.name.lower()]
            self.page_count_label.setText(f'{len(images)} pages')

    def set_default_palette(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('white'))
        self.setPalette(palette)

    def set_pixmap(self, pixmap):
        cropped_pixmap = crop_pixmap(pixmap, 75, 38)
        self.thumbnail_label.setPixmap(cropped_pixmap)

    def enterEvent(self, event):
        if not self.is_highlighted:
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor('#E6F2FF'))
            self.setPalette(palette)

    def leaveEvent(self, event):
        if not self.is_highlighted:
            self.set_default_palette()

    def mousePressEvent(self, event):
        if not self.is_highlighted:
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor('#CCE5FF'))
            self.setPalette(palette)

    def mouseReleaseEvent(self, event):
        if not self.is_highlighted:
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor('#E6F2FF'))
            self.setPalette(palette)
        self.chapter_selected.emit(self.chapter)

    def set_highlight(self, is_highlighted):
        self.is_highlighted = is_highlighted
        if is_highlighted:
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor('#A8D8FF'))
            self.setPalette(palette)
        else:
            self.set_default_palette()

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
        full_cover_path = series['cover_image']
        cover_pixmap = QPixmap(full_cover_path)
        self.series_thumbnail.setPixmap(cover_pixmap.scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        info_layout = QVBoxLayout()
        self.series_name_label = QLabel(series['name'])
        self.series_name_label.setWordWrap(True)
        self.series_name_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.series_name_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        info_layout.addWidget(self.series_name_label)

        
        self.back_btn = QPushButton("❌")
        self.back_btn.clicked.connect(self.go_back)

        top_layout.addWidget(self.series_thumbnail)
        top_layout.addLayout(info_layout)
        top_layout.addStretch()
        top_layout.addWidget(self.back_btn)
        self.layout.addLayout(top_layout)
        
        info_layout.addWidget(self.series_name_label)

        button_layout = QHBoxLayout()
        self.start_reading_btn = QPushButton("Start Reading")
        self.start_reading_btn.clicked.connect(self.start_reading)
        button_layout.addWidget(self.start_reading_btn)

        last_read_chapter_path = self.series.get('last_read_chapter')
        if last_read_chapter_path:
            last_read_chapter_name = Path(last_read_chapter_path).name
            self.continue_reading_btn = QPushButton(f"Continue Reading: {last_read_chapter_name}")
            self.continue_reading_btn.clicked.connect(self.continue_reading)
            button_layout.addWidget(self.continue_reading_btn)
        
        info_layout.addLayout(button_layout)

        self.scroll_area = QScrollArea()
        self.scroll_content = QWidget()
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setSpacing(0)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        self.load_chapters()

    def load_chapters(self):
        chapters = self.series.get('chapters', [])
        last_read_chapter = self.series.get('last_read_chapter')

        for i, chapter in enumerate(chapters):
            item_widget = ChapterListItemWidget(chapter, self.series, f"Ch {i+1}", self.library_manager, self)
            item_widget.chapter_selected.connect(self.on_chapter_selected)
            self.list_layout.addWidget(item_widget)
            self.chapter_widgets.append(item_widget)

            if chapter['path'] == last_read_chapter:
                item_widget.set_highlight(True)

            # Add a divider line
            if i < len(chapters) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                self.list_layout.addWidget(line)

        self.list_layout.addStretch()

        loader = ItemLoader(chapters, 0, item_type='chapter', thumb_width=150, thumb_height=75)
        loader.signals.item_loaded.connect(self.on_thumbnail_loaded)
        self.threadpool.start(loader)

    def on_chapter_selected(self, chapter):
        self.open_reader.emit(self.series, chapter)

    def on_thumbnail_loaded(self, pixmap, item, index, generation, item_type):
        if index < len(self.chapter_widgets):
            self.chapter_widgets[index].set_pixmap(pixmap)

    def go_back(self):
        self.back_to_library.emit()

    def start_reading(self):
        if self.series.get('chapters'):
            first_chapter = self.series['chapters'][0]
            self.open_reader.emit(self.series, first_chapter)

    def continue_reading(self):
        last_read_chapter_path = self.series.get('last_read_chapter')
        if last_read_chapter_path:
            chapter_to_open = next((ch for ch in self.series['chapters'] if ch['path'] == last_read_chapter_path), None)
            if chapter_to_open:
                self.open_reader.emit(self.series, chapter_to_open)