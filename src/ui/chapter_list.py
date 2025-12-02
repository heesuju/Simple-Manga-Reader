from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QPushButton, QHBoxLayout, QFrame, QGraphicsBlurEffect, QGraphicsScene, QGraphicsPixmapItem, QGraphicsDropShadowEffect, QSizePolicy
import os
from PyQt6.QtGui import QPixmap, QPalette, QColor, QPainter, QLinearGradient, QShortcut, QKeySequence, QMouseEvent
from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal, QRectF, QObject, QRunnable

from src.core.item_loader import ItemLoader
from src.ui.clickable_label import ClickableLabel
from src.ui.components.flow_layout import FlowLayout
from src.ui.reader_view import ReaderView
from src.utils.img_utils import crop_pixmap
from pathlib import Path
from src.utils.img_utils import get_chapter_number

class ChapterListLoaderSignals(QObject):
    chapter_processed = pyqtSignal(object, int, int)  # chapter, page_count, index
    finished = pyqtSignal()

class ChapterListLoader(QRunnable):
    def __init__(self, chapters):
        super().__init__()
        self.signals = ChapterListLoaderSignals()
        self.chapters = chapters

    def run(self):
        for i, chapter in enumerate(self.chapters):
            page_count = 0
            full_chapter_path = Path(chapter['path'])
            if full_chapter_path.exists() and full_chapter_path.is_dir():
                try:
                    images = [p for p in full_chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} and 'cover' not in p.name.lower()]
                    page_count = len(images)
                except OSError:
                    page_count = 0
            self.signals.chapter_processed.emit(chapter, page_count, i)
        self.signals.finished.emit()


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

        try:
            if len(self.series.get("chapters")) > 0:
                chapter_number = int(get_chapter_number(chapter_name))
                self.chapter_number_label.setText(f'{chapter_number:02}')
            else:
                self.chapter_number_label.setText(f'{1:02}')
        except (ValueError, TypeError, OverflowError):
            self.chapter_number_label.setText(f'{1:02}')
        
        self.chapter_number_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px; color: white; background: transparent;")
        self.name_label.setText(Path(chapter['path']).name)
        self.name_label.setStyleSheet("color: white; background: transparent;")
        self.page_count_label.setStyleSheet("color: white; background: transparent;")
        self.page_count_label.setText("...")

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

    def set_page_count(self, count):
        self.page_count_label.setText(f'{count} pages')

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
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
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
    tag_clicked = pyqtSignal(str, str)

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
        self.content_layout.setSpacing(5)

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
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.go_back)

        self.display_chapters = []
        self.load_chapters_and_info()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.BackButton:
            self.go_back()
        return super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.background_label.setGeometry(self.rect())
        view_size = self.size()
        scaled_pixmap = self.background_pixmap.scaled(view_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        x_offset = (scaled_pixmap.width() - view_size.width()) / 2
        y_offset = 0  # Anchor to top vertically
        cropped_pixmap = scaled_pixmap.copy(int(x_offset), int(y_offset), view_size.width(), view_size.height())
        self.background_label.setPixmap(cropped_pixmap)
        
        self.gradient_overlay.setGeometry(self.rect())
        self.scroll_area.setGeometry(self.rect())
        self.top_spacer.setFixedHeight(self.height() // 2)
        self.back_btn.move(10, 10)

    def _on_tag_clicked(self, tag_type, tag_value):
        self.tag_clicked.emit(tag_type, tag_value)

    def _create_tag_row(self, title, tag_type, tags, color):
        if not tags:
            return

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white; margin-top: 10px;")
        self.content_layout.addWidget(title_label)

        tag_container = QWidget()
        flow_layout = FlowLayout(tag_container)

        stylesheet = f"""
            QLabel {{
                background-color: {color};
                color: #333;
                padding: 4px 8px;
                border-radius: 10px;
                font-size: 12px;
            }}
        """

        for tag in tags:
            tag_label = ClickableLabel(tag)
            tag_label.setStyleSheet(stylesheet)
            tag_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            tag_label.setCursor(Qt.CursorShape.PointingHandCursor)
            tag_label.clicked.connect(lambda t=tag: self._on_tag_clicked(tag_type, t))
            flow_layout.addWidget(tag_label)

        self.content_layout.addWidget(tag_container)

    def on_chapter_page_count_loaded(self, chapter, page_count, index):
        if index < len(self.chapter_widgets):
            self.chapter_widgets[index].set_page_count(page_count)

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

        description = self.series.get('description')
        if description:
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setStyleSheet("color: white;")
            self.content_layout.addWidget(description_label)

        self._create_tag_row("Authors", "author", self.series.get('authors', []), "#D3B4E8")
        self._create_tag_row("Genres", "genre", self.series.get('genres', []), "#A7C7E7")
        self._create_tag_row("Themes", "theme", self.series.get('themes', []), "#E8B4B8")
        self._create_tag_row("Formats", "format", self.series.get('formats', []), "#B2D8B2")

        # --- Chapters Header ---
        db_chapters = self.series.get('chapters', [])
        self.display_chapters = list(db_chapters)

        if not self.display_chapters:
            series_path = Path(self.series['path'])
            if series_path.is_dir():
                images = [p for p in series_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}]
                if images:
                    dummy_chapter = {'path': str(series_path), 'name': self.series['name']}
                    self.display_chapters.append(dummy_chapter)

        if self.display_chapters:
            chapters_header_label = QLabel(f"Chapters ({len(self.display_chapters)})")
            chapters_header_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white; margin-top: 10px;")
            self.content_layout.addWidget(chapters_header_label)

        # --- Chapter List (Placeholders) ---
        last_read_chapter = self.series.get('last_read_chapter')
        self.chapter_widgets = []
        for i, chapter in enumerate(self.display_chapters):
            chapter_name = f"Ch {i+1}" if chapter.get('name') != self.series['name'] else self.series['name']
            item_widget = ChapterListItemWidget(chapter, self.series, chapter_name, self.library_manager, self)
            item_widget.chapter_selected.connect(self.on_chapter_selected)
            self.content_layout.addWidget(item_widget)
            self.chapter_widgets.append(item_widget)

            if chapter['path'] == last_read_chapter:
                item_widget.set_highlight(True)

            if i < len(self.display_chapters) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                self.content_layout.addWidget(line)

        self.content_layout.addStretch()

        # --- Background Loaders ---
        page_count_loader = ChapterListLoader(self.display_chapters)
        page_count_loader.signals.chapter_processed.connect(self.on_chapter_page_count_loaded)
        self.threadpool.start(page_count_loader)

        thumb_loader = ItemLoader(self.display_chapters, 0, item_type='chapter', thumb_width=150, thumb_height=75, library_manager=self.library_manager)
        thumb_loader.signals.item_loaded.connect(self.on_thumbnail_loaded)
        self.threadpool.start(thumb_loader)

    def on_chapter_selected(self, chapter):
        self.open_reader.emit(self.series, chapter)

    def on_thumbnail_loaded(self, pixmap, item, index, generation, item_type):
        if index < len(self.chapter_widgets):
            self.chapter_widgets[index].set_pixmap(pixmap)

    def go_back(self):
        self.back_to_library.emit()

    def start_reading(self):
        if self.display_chapters:
            first_chapter = self.display_chapters[0]
            self.open_reader.emit(self.series, first_chapter)

    def continue_reading(self):
        last_read_chapter_path = self.series.get('last_read_chapter')
        if last_read_chapter_path:
            chapter_to_open = next((ch for ch in self.series['chapters'] if ch['path'] == last_read_chapter_path), None)
            if chapter_to_open:
                self.open_reader.emit(self.series, chapter_to_open)
