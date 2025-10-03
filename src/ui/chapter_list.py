from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QPushButton, QHBoxLayout, QFrame, QGraphicsBlurEffect, QGraphicsScene, QGraphicsPixmapItem, QGraphicsDropShadowEffect
import os
from PyQt6.QtGui import QPixmap, QPalette, QColor, QPainter, QLinearGradient
from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal, QRectF

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
        self.hovered = False
        self.pressed = False

        self.setAutoFillBackground(False)

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

        chapter_number = int(chapter_name.replace("Ch ", ""))
        self.chapter_number_label.setText(f'{chapter_number:02}')
        self.chapter_number_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px; color: white; background: transparent;")
        self.name_label.setText(Path(chapter['path']).name)
        self.name_label.setStyleSheet("color: white; background: transparent;")
        self.page_count_label.setStyleSheet("color: white; background: transparent;")

        self.update_page_count()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        
        if self.is_highlighted:
            bg_color = QColor(168, 216, 255, 150)
            border_color = QColor(168, 216, 255, 200)
        elif self.pressed:
            bg_color = QColor(255, 255, 255, 40)
            border_color = QColor(255, 255, 255, 70)
        elif self.hovered:
            bg_color = QColor(255, 255, 255, 20)
            border_color = QColor(255, 255, 255, 50)
        else:
            bg_color = Qt.GlobalColor.transparent
            border_color = QColor(255, 255, 255, 30)

        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(rect, 5, 5)

    def update_page_count(self):
        full_chapter_path = Path(self.chapter['path'])
        if full_chapter_path.exists() and full_chapter_path.is_dir():
            images = [p for p in full_chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} and 'cover' not in p.name.lower()]
            self.page_count_label.setText(f'{len(images)} pages')

    def set_pixmap(self, pixmap):
        cropped_pixmap = crop_pixmap(pixmap, 75, 38)
        self.thumbnail_label.setPixmap(cropped_pixmap)

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def mousePressEvent(self, event):
        self.pressed = True
        self.update()

    def mouseReleaseEvent(self, event):
        self.pressed = False
        self.update()
        if self.rect().contains(event.pos()):
            self.chapter_selected.emit(self.chapter)

    def set_highlight(self, is_highlighted):
        self.is_highlighted = is_highlighted
        self.update()

class GradientOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scroll_offset = 0

    def set_scroll_offset(self, offset):
        self.scroll_offset = offset
        self.update() # Trigger a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Adjust alpha based on scroll position
        scroll_past_halfway = self.scroll_offset > (self.height() / 2)
        target_alpha = 220 if scroll_past_halfway else 200 # Softer alpha values
        target_color = QColor(0, 0, 0, target_alpha)

        # The gradient's start position moves up as we scroll
        initial_gradient_start_y = self.height() / 2
        new_gradient_start_y = initial_gradient_start_y - self.scroll_offset
        
        gradient = QLinearGradient(0, new_gradient_start_y, 0, self.height())
        
        # Create a softer transition
        gradient.setColorAt(0, Qt.GlobalColor.transparent)
        gradient.setColorAt(0.2, target_color) # Softer transition
        gradient.setColorAt(1, target_color)

        painter.fillRect(self.rect(), gradient)

class ChapterListView(QWidget):
    back_to_library = pyqtSignal()
    open_reader = pyqtSignal(object, object)

    def __init__(self, series, library_manager, parent=None):
        super().__init__(parent)
        self.series = series
        self.library_manager = library_manager
        self.chapter_widgets = []
        self.threadpool = QThreadPool()

        self.background_pixmap = QPixmap(self.series['cover_image'])

        # Manual layout of layers
        self.background_label = QLabel(self)
        self.gradient_overlay = GradientOverlay(self)
        self.gradient_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")

        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_content.setStyleSheet("background: transparent;")

        self.content_layout = QVBoxLayout(self.scroll_content)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(10)

        self.top_spacer = QWidget()
        self.content_layout.addWidget(self.top_spacer)

        # Back button is an overlay, everything else scrolls
        self.back_btn = QPushButton("←", self)
        self.back_btn.setFixedSize(40, 40)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 128);
                color: white;
                border:none;
                border-radius: 20px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 160);
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 190);
            }
        """)
        self.back_btn.clicked.connect(self.go_back)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.gradient_overlay.set_scroll_offset)

        self.load_chapters_and_info()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.background_label.setGeometry(self.rect())
        view_size = self.size()
        scaled_pixmap = self.background_pixmap.scaled(view_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        x_offset = (scaled_pixmap.width() - view_size.width()) / 2
        y_offset = (scaled_pixmap.height() - view_size.height()) / 2
        cropped_pixmap = scaled_pixmap.copy(int(x_offset), int(y_offset), view_size.width(), view_size.height())
        self.background_label.setPixmap(cropped_pixmap)
        
        self.gradient_overlay.setGeometry(self.rect())
        self.scroll_area.setGeometry(self.rect())
        self.top_spacer.setFixedHeight(self.height() // 2)
        self.back_btn.move(10, 10)

    def load_chapters_and_info(self):
        # --- Info and Buttons (in scroll area) ---
        button_layout = QHBoxLayout()
        start_reading_btn = QPushButton("Start Reading")
        start_reading_btn.clicked.connect(self.start_reading)
        button_layout.addWidget(start_reading_btn)

        last_read_chapter_path = self.series.get('last_read_chapter')
        if last_read_chapter_path:
            last_read_chapter_name = Path(last_read_chapter_path).name
            continue_reading_btn = QPushButton(f"Continue: {last_read_chapter_name}")
            continue_reading_btn.clicked.connect(self.continue_reading)
            button_layout.addWidget(continue_reading_btn)
        self.content_layout.addLayout(button_layout)

        series_name_label = QLabel(self.series['name'])
        series_name_label.setWordWrap(True)
        series_name_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(5)
        shadow_effect.setColor(QColor(0, 0, 0, 180))
        shadow_effect.setOffset(2, 2)
        series_name_label.setGraphicsEffect(shadow_effect)
        self.content_layout.addWidget(series_name_label)

        authors = self.series.get('authors', [])
        if authors:
            authors_label = QLabel(f"by {', '.join(authors)}")
            authors_label.setStyleSheet("font-style: italic; color: white;")
            self.content_layout.addWidget(authors_label)

        description = self.series.get('description')
        if description:
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setStyleSheet("color: white;")
            self.content_layout.addWidget(description_label)

        # --- Chapters Header ---
        chapters = self.series.get('chapters', [])
        if chapters:
            chapters_header_label = QLabel(f"Chapters ({len(chapters)})")
            chapters_header_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white; margin-top: 10px;")
            self.content_layout.addWidget(chapters_header_label)

        # --- Chapter List ---
        last_read_chapter = self.series.get('last_read_chapter')

        for i, chapter in enumerate(chapters):
            item_widget = ChapterListItemWidget(chapter, self.series, f"Ch {i+1}", self.library_manager, self)
            item_widget.chapter_selected.connect(self.on_chapter_selected)
            self.content_layout.addWidget(item_widget)
            self.chapter_widgets.append(item_widget)

            if chapter['path'] == last_read_chapter:
                item_widget.set_highlight(True)

            if i < len(chapters) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                self.content_layout.addWidget(line)

        self.content_layout.addStretch()

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
