from typing import List
import zipfile
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QFrame, QScrollArea, QSizePolicy, QPinchGesture
)
from PyQt6.QtGui import QPixmap, QKeySequence, QPainter, QShortcut, QMouseEvent
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QRunnable, QObject, QThreadPool
from src.collapsible_panel import CollapsiblePanel
from src.image_view import ImageView

class ThumbnailWorker(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(int, QPixmap)

    def __init__(self, index, path, load_thumb_func):
        super().__init__()
        self.index = index
        self.path = path
        self.load_thumb = load_thumb_func
        self.signals = self.Signals()

    def run(self):
        thumb = self.load_thumb(self.path)
        if thumb:
            self.signals.finished.emit(self.index, thumb)
from src.page_input import PageInput
import math
from src.enums import ViewMode
from src.core.image_loader import ImageLoader
from src.utils import get_image_data_from_zip, get_chapter_number, load_thumbnail, load_thumbnail_from_zip, load_thumbnail_from_virtual_path

def crop_pixmap(pixmap: QPixmap, width: int, height: int) -> QPixmap:
    if pixmap.isNull():
        return pixmap
    
    scaled_pixmap = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled_pixmap.width() - width) // 2
    y = (scaled_pixmap.height() - height) // 2
    return scaled_pixmap.copy(x, y, width, height)

class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, index, text, parent=None):
        super().__init__(parent)
        self.index = index
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFixedSize(100, 140)

        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)

        self.layout.addWidget(self.image_label)
        self.layout.addWidget(self.text_label)
        self.set_selected(False)

    def set_pixmap(self, pixmap: QPixmap):
        if not pixmap.isNull():
            cropped = crop_pixmap(pixmap, 100, 140)
            self.image_label.setPixmap(cropped)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        return super().mousePressEvent(ev)

    def set_selected(self, selected: bool):
        if selected:
            self.setStyleSheet("background-color: #4a86e8; border-radius: 4px;")
        else:
            self.setStyleSheet("background-color: none; border-radius: 4px;")

def _get_first_image_path(chapter_dir):
    if isinstance(chapter_dir, str) and chapter_dir.endswith('.zip'):
        try:
            with zipfile.ZipFile(chapter_dir, 'r') as zf:
                image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                if image_files:
                    return f"{chapter_dir}|{image_files[0]}"
        except zipfile.BadZipFile:
            return None
    elif isinstance(chapter_dir, Path) and chapter_dir.is_dir():
        exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
        image_files = [p for p in sorted(chapter_dir.iterdir()) if p.suffix.lower() in exts and p.is_file()]
        if image_files:
            return str(image_files[0])
    return None

class MangaReader(QMainWindow):
    def __init__(self, manga_dirs: List[object], index:int, start_file: str = None):
        super().__init__()
        self.setWindowTitle("Manga Reader")
        self.grabGesture(Qt.GestureType.PinchGesture)
        if index > len(manga_dirs) - 1:
            return
        
        self.start_file = start_file
        self.view_mode = ViewMode.SINGLE
        self.scroll_area = None
        self.vertical_container = None
        self.vbox = None
        self.page_labels: list[QLabel] = []
        self.page_pixmaps: dict[int, QPixmap] = {}
        self.v_labels: list[QLabel] = []
        self.vertical_pixmaps: list[QPixmap] = []
        self.loader: ImageLoader | None = None

        self._last_total_scale = 1.0
        self.chapter_index = index
        self.chapters = manga_dirs
        self.manga_dir = self.chapters[index]
        self.back_to_grid_callback = None

        self.thread_pool = QThreadPool()
        self.chapter_thumbnail_widgets = []
        self.page_thumbnail_widgets = []
        self.current_chapter_thumbnail = None
        self.current_page_thumbnail = None

        self.showFullScreen()
        self._setup_ui()
        self.refresh()
        self._update_chapter_selection()

    def _setup_ui(self):
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.setScene(self.scene)
        
        self.page_label = PageInput("Page", 0,0)
        self.ch_label = PageInput("Chapter", 0,0)

        self.page_label.enterPressed.connect(self.change_page)
        self.ch_label.enterPressed.connect(self.change_chapter)

        self.back_btn = QPushButton("⬅ Back to Grid")
        self.back_btn.clicked.connect(self.back_to_grid)

        self.layout_btn = QPushButton("Double")
        self.layout_btn.clicked.connect(self.toggle_layout)
        
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.back_to_grid)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(0)
        top_layout.addWidget(self.back_btn)
        top_layout.addWidget(self.ch_label, 1, Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.layout_btn)
        top_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.view, 1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.chapter_panel = CollapsiblePanel(self)
        self._setup_chapter_panel()

        self.page_panel = CollapsiblePanel(self)
        self._setup_page_panel()

        self.chapter_panel.raise_()
        self.page_panel.raise_()

        self.chapter_panel.show()
        self.page_panel.show()

        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)
        self.view.setMouseTracking(True)

        self.overlay_container = QWidget(self.centralWidget())
        self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.overlay_container.setStyleSheet("background: transparent;")
        self.overlay_container.raise_()
                
        self.prev_btn = QPushButton("", self.overlay_container)
        self.next_btn = QPushButton("", self.overlay_container)
        for btn in (self.prev_btn, self.next_btn):
            btn.setStyleSheet("background-color: rgba(0,0,0,0.0); color: white; font-size: 32px; border: none;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.clicked.connect(self.show_prev)
        self.next_btn.clicked.connect(self.show_next)

        overlay_layout = QHBoxLayout(self.overlay_container)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addWidget(self.prev_btn)
        overlay_layout.addWidget(self.next_btn)
        overlay_layout.setStretch(0, 1)
        overlay_layout.setStretch(1, 1)

        original_resize = self.view.resizeEvent
        def resizeEvent(event):
            self._update_overlay_size(event)
            self._update_panel_geometries()
            if original_resize:
                original_resize(event)
        self.view.resizeEvent = resizeEvent

    def _update_panel_geometries(self):
        chapter_panel_height = 170 if self.chapter_panel.content_area.isVisible() else 0
        self.chapter_panel.setGeometry(0, 50, self.width(), chapter_panel_height)

        page_panel_height = 170 if self.page_panel.content_area.isVisible() else 0
        self.page_panel.setGeometry(0, self.height() - page_panel_height - 50, self.width(), page_panel_height)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        top_rect = self.rect()
        top_rect.setHeight(50)
        bottom_rect = self.rect()
        bottom_rect.setTop(self.height() - 50)

        if top_rect.contains(pos):
            self.chapter_panel.show_content()
        elif bottom_rect.contains(pos):
            self.page_panel.show_content()
        
        self._update_panel_geometries()
        super().mouseMoveEvent(event)



    def _setup_chapter_panel(self):
        self.chapter_thumbnails_widget = QWidget()
        self.chapter_thumbnails_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        self.chapter_thumbnails_layout = QHBoxLayout(self.chapter_thumbnails_widget)
        self.chapter_thumbnails_layout.setSpacing(10)
        self.chapter_thumbnails_layout.addStretch()
        self.chapter_panel.set_content_widget(self.chapter_thumbnails_widget)
        self._update_chapter_thumbnails()

    def _setup_page_panel(self):
        self.page_thumbnails_widget = QWidget()
        self.page_thumbnails_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        self.page_thumbnails_layout = QHBoxLayout(self.page_thumbnails_widget)
        self.page_thumbnails_layout.setSpacing(10)
        self.page_thumbnails_layout.addStretch()
        self.page_panel.set_content_widget(self.page_thumbnails_widget)

    def _update_chapter_thumbnails(self):
        for i in reversed(range(self.chapter_thumbnails_layout.count() - 1)):
            self.chapter_thumbnails_layout.itemAt(i).widget().setParent(None)
        self.chapter_thumbnail_widgets.clear()

        self.chapters = sorted(self.chapters, key=lambda x: get_chapter_number(str(x)))

        for i, chapter in enumerate(self.chapters):
            chapter_name = Path(str(chapter)).name
            widget = ThumbnailWidget(i, f"{i+1}. {chapter_name}")
            widget.clicked.connect(self._change_chapter_by_thumbnail)
            self.chapter_thumbnails_layout.insertWidget(i, widget)
            self.chapter_thumbnail_widgets.append(widget)

            first_image_path = _get_first_image_path(chapter)
            if first_image_path:
                worker = ThumbnailWorker(i, first_image_path, self._load_thumbnail)
                worker.signals.finished.connect(self._on_chapter_thumbnail_loaded)
                self.thread_pool.start(worker)

    def _on_chapter_thumbnail_loaded(self, index, pixmap):
        if index < len(self.chapter_thumbnail_widgets):
            self.chapter_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_page_thumbnails(self):
        for i in reversed(range(self.page_thumbnails_layout.count() - 1)):
            self.page_thumbnails_layout.itemAt(i).widget().setParent(None)
        self.page_thumbnail_widgets.clear()

        for i, image_path in enumerate(self.images):
            page_name = Path(image_path).name
            widget = ThumbnailWidget(i, f"{i+1}. {page_name}")
            widget.clicked.connect(self._change_page_by_thumbnail)
            self.page_thumbnails_layout.insertWidget(i, widget)
            self.page_thumbnail_widgets.append(widget)

            worker = ThumbnailWorker(i, image_path, self._load_thumbnail)
            worker.signals.finished.connect(self._on_page_thumbnail_loaded)
            self.thread_pool.start(worker)
        
        self._update_page_selection()

    def _on_page_thumbnail_loaded(self, index, pixmap):
        if index < len(self.page_thumbnail_widgets):
            self.page_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_chapter_selection(self):
        if self.current_chapter_thumbnail:
            self.current_chapter_thumbnail.set_selected(False)
        
        if self.chapter_index < len(self.chapter_thumbnail_widgets):
            self.current_chapter_thumbnail = self.chapter_thumbnail_widgets[self.chapter_index]
            self.current_chapter_thumbnail.set_selected(True)

    def _update_page_selection(self):
        if self.current_page_thumbnail:
            self.current_page_thumbnail.set_selected(False)

        if self.current_index < len(self.page_thumbnail_widgets):
            self.current_page_thumbnail = self.page_thumbnail_widgets[self.current_index]
            self.current_page_thumbnail.set_selected(True)

    def _change_chapter_by_thumbnail(self, index: int):
        self.change_chapter(index + 1)

    def _change_page_by_thumbnail(self, index: int):
        self.change_page(index + 1)

    def event(self, e):
        if e.type() == QEvent.Type.Gesture:
            gesture = e.gesture(Qt.GestureType.PinchGesture)
            if gesture:
                self.handle_pinch(gesture)
                return True
        return super().event(e)

    def eventFilter(self, obj, event):
        if self.view_mode == ViewMode.STRIP and self.scroll_area and obj is self.scroll_area.viewport():
            if event.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self._resize_vertical_images)
        return super().eventFilter(obj, event)

    def _update_overlay_size(self, event=None):
        if self.view_mode == ViewMode.STRIP and self.scroll_area is not None:
            target = self.scroll_area
        else:
            target = self.view

        geo = target.geometry()
        self.overlay_container.setGeometry(geo)

        w, h = geo.width(), geo.height()
        self.prev_btn.setGeometry(0, 0, w // 2, h)
        self.next_btn.setGeometry(w // 2, 0, w - (w // 2), h)

    def refresh(self, start_from_end:bool=False):
        self.images = self._get_image_list()
        self.images = sorted(self.images, key=get_chapter_number)
        if hasattr(self, 'start_file') and self.start_file:
            try:
                self.current_index = self.images.index(self.start_file)
            except (ValueError, IndexError):
                self.current_index = 0
            self.start_file = None
        elif start_from_end:
            self.current_index = len(self.images) - 1
        else:
            self.current_index = 0

        if not self.images:
            QMessageBox.information(self, "No images", f"No images found in: {self.manga_dir}")
        else:
            self._load_image(self.images[self.current_index])
        
        self._update_page_thumbnails()

    def _get_image_list(self):
        if isinstance(self.manga_dir, str) and self.manga_dir.endswith('.zip'):
            try:
                with zipfile.ZipFile(self.manga_dir, 'r') as zf:
                    image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                    return [f"{self.manga_dir}|{name}" for name in image_files]
            except zipfile.BadZipFile:
                return []
        elif isinstance(self.manga_dir, Path) and self.manga_dir.is_dir():
            exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
            return [str(p) for p in sorted(self.manga_dir.iterdir()) if p.suffix.lower() in exts and p.is_file()]
        return []

    def _load_pixmap(self, path: str) -> QPixmap:
        pixmap = QPixmap()
        if '|' in path:
            image_data = get_image_data_from_zip(path)
            if image_data:
                pixmap.loadFromData(image_data)
        else:
            pixmap.load(path)
        return pixmap

    def _load_thumbnail(self, path: str) -> QPixmap | None:
        if '|' in path:
            return load_thumbnail_from_virtual_path(path)
        elif path.endswith('.zip'):
            return load_thumbnail_from_zip(path)
        else:
            return load_thumbnail(path)

    def _load_image(self, path: str):
        self.original_pixmap = self._load_pixmap(path)
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(self.original_pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.view.reset_zoom_state()
        self.page_label.set_total(len(self.images))
        self.ch_label.set_total(len(self.chapters))
        
        self.page_label.set_value(self.current_index + 1)
        self.ch_label.set_value(self.chapter_index + 1)

        self._update_page_selection()

        QTimer.singleShot(0, self._fit_current_image)
    
    def _load_double_images(self):
        self.scene.clear()

        pix1 = self._load_pixmap(self.images[self.current_index])
        if self.current_index + 1 < len(self.images):
            pix2 = self._load_pixmap(self.images[self.current_index + 1])
        else:
            pix2 = None

        item1 = QGraphicsPixmapItem(pix1)
        item1.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        if pix2:
            item2 = QGraphicsPixmapItem(pix2)
            item2.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item2.setPos(0, 0)
            self.scene.addItem(item2)

            total_width = pix1.width() + pix2.width()
            total_height = max(pix1.height(), pix2.height())
            item1.setPos(pix2.width(), 0)
        else:
            total_width = pix1.width()
            total_height = pix1.height()
            item1.setPos(0, 0)

        self.scene.addItem(item1)

        self.scene.setSceneRect(0, 0, total_width, total_height)
        self.view.reset_zoom_state()
        self.page_label.set_total(len(self.images))
        self.page_label.set_value(self.current_index + 1)
        QTimer.singleShot(0, self._fit_current_image)

    def _update_zoom(self, factor: float):
        """Zoom the view using GPU-accelerated transformation."""
        self.view.resetTransform()  # reset previous zoom
        self.view.scale(factor, factor)
    
    def _fit_current_image(self):
        """Fit image to view and reset zoom factor (handles single-image and vertical modes)."""
        if self.view_mode == ViewMode.STRIP:
            # In vertical mode we want all labels resized to viewport width
            QTimer.singleShot(0, self._resize_vertical_images)
            return

        # single-image behavior (unchanged)
        if not hasattr(self, "pixmap_item"):
            return
        self.view.resetTransform()  # remove any previous zoom
        self.view.reset_zoom_state()
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def show_next(self):
        if not self.images: 
            return
        if self.view_mode == ViewMode.DOUBLE:
            step = 2
        else:
            step = 1

        if self.current_index + step < len(self.images):
            self.current_index += step
            if self.view_mode == ViewMode.SINGLE:
                self._load_image(self.images[self.current_index])
            elif self.view_mode == ViewMode.DOUBLE:
                self._load_double_images()
            self._update_page_selection()
        else:
            total_chapters = len(self.chapters)
            if self.chapter_index < total_chapters - 1:
                self.chapter_index += 1
                self.manga_dir = self.chapters[self.chapter_index]
                self.refresh()

    def show_prev(self):
        if not self.images: 
            return
        if self.view_mode == ViewMode.DOUBLE:
            step = 2
        else:
            step = 1

        if self.current_index - step >= 0:
            self.current_index -= step
            if self.view_mode == ViewMode.SINGLE:
                self._load_image(self.images[self.current_index])
            elif self.view_mode == ViewMode.DOUBLE:
                self._load_double_images()
            self._update_page_selection()
        else:
            if self.chapter_index - 1 >= 0:
                self.chapter_index -= 1
                self.manga_dir = self.chapters[self.chapter_index]
                self.refresh(True)

    def change_page(self, page:int):
        img_count = len(self.images)
        index = page - 1
        
        if index < 0:
            index = 0
        elif index > img_count - 1:
            index = img_count - 1
            
        self.current_index = index
        self._load_image(self.images[self.current_index])
        self._update_page_selection()

    def change_chapter(self, chapter:int):
        index = chapter - 1
        total_chapters = len(self.chapters)
        
        if index < 0:
            index = 0
        elif index > total_chapters - 1:
            index = total_chapters - 1
        
        self.chapter_index = index
        self.manga_dir = self.chapters[self.chapter_index]
        self.refresh()
        self._update_chapter_selection()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        QTimer.singleShot(0, self._fit_current_image)

    def exit_if_not_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            QTimer.singleShot(0, self._fit_current_image)

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._fit_current_image)
        QTimer.singleShot(50, self._update_overlay_size)

    def wheelEvent(self, event):
        self.view.wheelEvent(event)
        if not math.isclose(self.view._zoom_factor, 1.0):
            self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def handle_pinch(self, gesture: QPinchGesture):
        if gesture.state() == Qt.GestureState.GestureStarted:
            self._gesture_start_zoom = self.view._zoom_factor

        if gesture.changeFlags() & QPinchGesture.ChangeFlag.ScaleFactorChanged:
            new_zoom = self._gesture_start_zoom * gesture.totalScaleFactor()
            scale_delta = new_zoom / self.view._zoom_factor

            if abs(scale_delta - 1.0) < 0.02:
                return

            self.view.scale(scale_delta, scale_delta)
            self.view._zoom_factor = new_zoom

            if not math.isclose(self.view._zoom_factor, 1.0, rel_tol=1e-2):
                self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            else:
                self.overlay_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def toggle_layout(self):
        if self.view_mode == ViewMode.SINGLE:
            self.view_mode = ViewMode.DOUBLE
            self.layout_btn.setText("Double")
            self._show_double_layout()
        elif self.view_mode == ViewMode.DOUBLE:
            self.view_mode = ViewMode.STRIP
            self.layout_btn.setText("Strip")
            self._show_vertical_layout()
        else:
            self.view_mode = ViewMode.SINGLE
            self.layout_btn.setText("Single")
            self._show_single_layout()

        QTimer.singleShot(0, self._update_overlay_size)
        QTimer.singleShot(0, self._fit_current_image)

    def _show_double_layout(self):
        self.view.show()
        if self.scroll_area:
            self.scroll_area.hide()
        self._load_double_images()

    def _show_vertical_layout(self):
        self.view.hide()

        if self.scroll_area is None:
            self.scroll_area = QScrollArea(self.centralWidget())
            self.scroll_area.setWidgetResizable(True)
            self.vertical_container = QWidget()
            self.vbox = QVBoxLayout(self.vertical_container)
            self.vbox.setSpacing(8)
            self.vbox.setContentsMargins(8, 8, 8, 8)
            self.scroll_area.setWidget(self.vertical_container)

            main_layout = self.centralWidget().layout()
            main_layout.insertWidget(1, self.scroll_area)

            self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_images)
            self.scroll_area.viewport().installEventFilter(self)

        while self.vbox.count():
            item = self.vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.page_labels.clear()
        self.page_pixmaps.clear()

        for i in range(len(self.images)):
            lbl = QLabel("Loading...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(300)
            self.vbox.addWidget(lbl)
            self.page_labels.append(lbl)

        QTimer.singleShot(0, self._update_visible_images)

    def _update_visible_images(self):
        if not self.scroll_area:
            return
        viewport_rect = self.scroll_area.viewport().rect()
        viewport_top = self.scroll_area.verticalScrollBar().value()
        viewport_bottom = viewport_top + viewport_rect.height()

        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()

            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                if i not in self.page_pixmaps:
                    # load original image
                    orig = self._load_pixmap(self.images[i])
                    self.page_pixmaps[i] = orig
                else:
                    orig = self.page_pixmaps[i]

                self._resize_single_label(lbl, orig)
            else:
                lbl.clear()

    def _add_vertical_image(self, pixmap: QPixmap, idx: int):
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.vbox.addWidget(lbl)
        self.v_labels.append(lbl)
        self.vertical_pixmaps.append(pixmap)

        QTimer.singleShot(0, lambda l=lbl, p=pixmap: self._resize_single_label(l, p))

    def _resize_single_label(self, label: QLabel, orig_pix: QPixmap):
        if not self.scroll_area:
            return
        w = self.scroll_area.viewport().width() - (self.vbox.contentsMargins().left() + self.vbox.contentsMargins().right())
        if w <= 0 or orig_pix.isNull():
            return
        scaled = orig_pix.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(scaled)
        label.setFixedHeight(scaled.height())

    def _resize_vertical_images(self):
        if not self.scroll_area:
            return
        viewport_rect = self.scroll_area.viewport().rect()
        viewport_top = self.scroll_area.verticalScrollBar().value()
        viewport_bottom = viewport_top + viewport_rect.height()

        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()
            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                if i in self.page_pixmaps:
                    self._resize_single_label(lbl, self.page_pixmaps[i])

    def _show_single_layout(self):
        if self.scroll_area:
            main_layout = self.centralWidget().layout()
            main_layout.removeWidget(self.scroll_area)
            self.scroll_area.deleteLater()
            self.scroll_area = None
            self.vertical_container = None
            self.vbox = None
            self.v_labels = []
            self.vertical_pixmaps = []
        self.view.show()
        self._load_image(self.images[self.current_index])

    def back_to_grid(self):
        if self.back_to_grid_callback:
            self.close()
            self.back_to_grid_callback()