import math
from pathlib import Path
import zipfile
from typing import List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsScene,QGraphicsPixmapItem, 
    QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QScrollArea, QSizePolicy, QPinchGesture
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor
from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins

from src.enums import ViewMode
from src.core.thumbnail_worker import ThumbnailWorker
from src.ui.collapsible_panel import CollapsiblePanel
from src.ui.vertical_collapsible_panel import VerticalCollapsiblePanel
from src.ui.image_view import ImageView
from src.ui.input_label import InputLabel
from src.ui.thumbnail_widget import ThumbnailWidget
from src.utils.img_utils import get_image_data_from_zip, load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path, empty_placeholder, load_pixmap_for_thumbnailing
from src.data.reader_model import ReaderModel, _get_first_image_path
from src.core.thumbnail_worker import get_common_size_ratio

class ReaderView(QMainWindow):
    def __init__(self, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None):
        super().__init__()
        self.setWindowTitle("Manga Reader")
        self.grabGesture(Qt.GestureType.PinchGesture)

        self.model = ReaderModel(manga_dirs, index, start_file, images)
        self.model.refreshed.connect(self.on_model_refreshed)
        self.model.image_loaded.connect(self._load_image)
        self.model.double_image_loaded.connect(self._load_double_images)
        self.model.layout_updated.connect(self.on_layout_updated)

        self.back_to_grid_callback = None

        self.scroll_area = None
        self.vertical_container = None
        self.vbox = None
        self.page_labels: list[QLabel] = []
        self.page_pixmaps: dict[int, QPixmap] = {}
        self.v_labels: list[QLabel] = []
        self.vertical_pixmaps: list[QPixmap] = []

        self._last_total_scale = 1.0

        self.thread_pool = QThreadPool()
        self.chapter_thumbnail_widgets = []
        self.page_thumbnail_widgets = []
        self.current_chapter_thumbnail = None
        self.current_page_thumbnail = None

        self.strip_mode_panel = None
        self.strip_thumbnail_widgets = []
        self.current_strip_thumbnail = None

        self._setup_ui()
        self.showFullScreen()
        self.model.refresh()
        self._update_chapter_selection()

    def _setup_ui(self):
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.setScene(self.scene)
        
        self.page_label = InputLabel("Page", 0,0)
        self.ch_label = InputLabel("Chapter", 0,0)

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
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(self.back_btn)
        top_layout.addWidget(self.ch_label, 1, Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.layout_btn)
        top_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.view, 1)

        container = QWidget()
        container.setLayout(main_layout)
        container.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(container)

        self.chapter_panel = CollapsiblePanel(self)
        self._setup_chapter_panel()

        self.page_panel = CollapsiblePanel(self)
        self._setup_page_panel()

        self.strip_mode_panel = VerticalCollapsiblePanel(self)
        self._setup_strip_mode_panel()

        self.chapter_panel.raise_()
        self.page_panel.raise_()
        self.strip_mode_panel.raise_()

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

        self.view.resizeEvent = self.resizeEvent

    def on_model_refreshed(self):
        if not self.model.images:
            QMessageBox.information(self, "No images", f"No images found in: {self.model.manga_dir}")
        self._update_page_thumbnails()
        self.model.update_layout()

    def on_layout_updated(self, view_mode):
        self._update_page_thumbnails()

        if view_mode == ViewMode.SINGLE:
            self.layout_btn.setText("Single")
            self._show_single_layout()
        elif view_mode == ViewMode.DOUBLE:
            self.layout_btn.setText("Double")
            self._show_double_layout()
        else:
            self.layout_btn.setText("Strip")
            self._show_vertical_layout()
            self._update_strip_mode_thumbnails()

        QTimer.singleShot(0, self._fit_current_image)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_panel_geometries()

    def _update_panel_geometries(self):
        chapter_panel_height = 170 if self.chapter_panel.content_area.isVisible() else 0
        self.chapter_panel.setGeometry(0, 50, self.width(), chapter_panel_height)

        page_panel_height = 170 if self.page_panel.content_area.isVisible() else 0
        self.page_panel.setGeometry(0, self.height() - page_panel_height - 50, self.width(), page_panel_height)

        strip_panel_width = 170 if self.strip_mode_panel.content_area.isVisible() else 0
        self.strip_mode_panel.setGeometry(self.width() - strip_panel_width, 0, strip_panel_width, self.height())

    def mouseMoveEvent(self, event):
        pos = event.pos()
        top_rect = self.rect()
        top_rect.setHeight(50)
        bottom_rect = self.rect()
        bottom_rect.setTop(self.height() - 50)
        right_rect = self.rect()
        right_rect.setLeft(self.width() - 50)

        if top_rect.contains(pos):
            self.chapter_panel.show_content()
        elif bottom_rect.contains(pos):
            self.page_panel.show_content()
        elif self.model.view_mode == ViewMode.STRIP and right_rect.contains(pos):
            self.strip_mode_panel.show_content()
        
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
        self.page_thumbnails_layout.setSpacing(0)
        self.page_thumbnails_layout.addStretch()
        self.page_panel.set_content_widget(self.page_thumbnails_widget)

    def _update_chapter_thumbnails(self):
        for i in reversed(range(self.chapter_thumbnails_layout.count() - 1)):
            self.chapter_thumbnails_layout.itemAt(i).widget().setParent(None)
        self.chapter_thumbnail_widgets.clear()

        for i, chapter in enumerate(self.model.chapters):
            chapter_name = Path(str(chapter)).name
            widget = ThumbnailWidget(i, chapter_name)
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

        images = self.model.images
        if self.model.view_mode == ViewMode.DOUBLE:
            images = self.model._get_double_view_images()

        for i, image_path in enumerate(images):
            widget = ThumbnailWidget(i, str(i+1))
            widget.clicked.connect(self._change_page_by_thumbnail)
            self.page_thumbnails_layout.insertWidget(i, widget)
            self.page_thumbnail_widgets.append(widget)

            if image_path == "placeholder":
                self._on_page_thumbnail_loaded(i, empty_placeholder())
            else:
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
        
        if self.model.chapter_index < len(self.chapter_thumbnail_widgets):
            self.current_chapter_thumbnail = self.chapter_thumbnail_widgets[self.model.chapter_index]
            self.current_chapter_thumbnail.set_selected(True)

    def _update_page_selection(self):
        if self.current_page_thumbnail:
            self.current_page_thumbnail.set_selected(False)

        if self.model.current_index < len(self.page_thumbnail_widgets):
            self.current_page_thumbnail = self.page_thumbnail_widgets[self.model.current_index]
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
        if self.model.view_mode == ViewMode.STRIP and self.scroll_area and obj is self.scroll_area.viewport():
            if event.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self._resize_vertical_images)
        return super().eventFilter(obj, event)

    def _load_pixmap(self, path: str) -> QPixmap:
        if path == "placeholder":
            common_size, _, _, _ = get_common_size_ratio(self.model.images)
            return empty_placeholder(common_size[0], common_size[1])

        pixmap = QPixmap()
        
        path_str = str(path)
        crop = None
        if path_str.endswith("_left"):
            path_str = path_str[:-5]
            crop = "left"
        elif path_str.endswith("_right"):
            path_str = path_str[:-6]
            crop = "right"

        if '|' in path_str:
            image_data = get_image_data_from_zip(path_str)
            if image_data:
                pixmap.loadFromData(image_data)
        else:
            pixmap.load(path_str)

        if crop and not pixmap.isNull():
            width = pixmap.width()
            height = pixmap.height()
            if crop == 'left':
                return pixmap.copy(0, 0, width // 2, height)
            elif crop == 'right':
                return pixmap.copy(width // 2, 0, width // 2, height)

        return pixmap

    def _load_thumbnail(self, path: str) -> QPixmap | None:
        crop = None
        if path.endswith("_left"):
            path = path[:-5]
            crop = "left"
        elif path.endswith("_right"):
            path = path[:-6]
            crop = "right"

        if '|' in path:
            return load_thumbnail_from_virtual_path(path=path, crop=crop)
        elif path.endswith('.zip'):
            return load_thumbnail_from_zip(path=path)
        else:
            return load_thumbnail_from_path(path=path, crop=crop)

    def _load_image(self, path: str):
        self.original_pixmap = self._load_pixmap(path)
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(self.original_pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.view.reset_zoom_state()
        self.page_label.set_total(len(self.model.images))
        self.ch_label.set_total(len(self.model.chapters))
        
        self.page_label.set_value(self.model.current_index + 1)
        self.ch_label.set_value(self.model.chapter_index + 1)

        self._update_page_selection()

        QTimer.singleShot(0, self._fit_current_image)
    
    def _load_double_images(self, image1_path, image2_path):
        self.scene.clear()

        pix1 = self._load_pixmap(image1_path)
        pix2 = self._load_pixmap(image2_path) if image2_path else None

        item1 = QGraphicsPixmapItem(pix1)
        item1.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        total_width = pix1.width()
        total_height = pix1.height()
        item1.setPos(0, 0)
        self.scene.addItem(item1)

        if pix2:
            item2 = QGraphicsPixmapItem(pix2)
            item2.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item2.setPos(pix1.width(), 0)
            self.scene.addItem(item2)

            total_width = pix1.width() + pix2.width()
            total_height = max(pix1.height(), pix2.height())

        self.scene.setSceneRect(0, 0, total_width, total_height)
        self.view.reset_zoom_state()
        self.page_label.set_total(len(self.model.images))
        self.page_label.set_value(self.model.current_index + 1)
        QTimer.singleShot(0, self._fit_current_image)

    def _update_zoom(self, factor: float):
        """Zoom the view using GPU-accelerated transformation.""" 
        self.view.resetTransform()  # reset previous zoom
        self.view.scale(factor, factor)
    
    def _fit_current_image(self):
        """Fit image to view and reset zoom factor (handles single-image and vertical modes)."""
        if self.model.view_mode == ViewMode.STRIP:
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
        self.model.show_next()
        self._update_page_selection()

    def show_prev(self):
        self.model.show_prev()
        self._update_page_selection()

    def change_page(self, page:int):
        self.model.change_page(page)
        self._update_page_selection()

    def change_chapter(self, chapter:int):
        self.model.change_chapter(chapter)
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

    def toggle_layout(self, mode:ViewMode=None):
        self.model.toggle_layout(mode)

    def _show_double_layout(self):
        self.strip_mode_panel.hide()
        for n, widget in enumerate(self.page_thumbnail_widgets):
            if n % 2 == 0:
                widget._update_margins(QMargins(0,0,0,0))
            else:
                widget._update_margins(QMargins(0,0,10,0))

        self.view.show()
        if self.scroll_area:
            self.scroll_area.hide()

    def _show_vertical_layout(self):
        self.page_panel.hide()
        self.chapter_panel.hide()
        self.view.hide()

        if self.scroll_area is None:
            self.scroll_area = QScrollArea(self.centralWidget())
            self.scroll_area.setWidgetResizable(True)
            self.vertical_container = QWidget()
            self.vbox = QVBoxLayout(self.vertical_container)
            self.vbox.setSpacing(0)
            self.vbox.setContentsMargins(0, 0, 0, 0)
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

        for i in range(len(self.model.images)):
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

        # Find the topmost visible label
        topmost_visible_index = -1
        for i, lbl in enumerate(self.page_labels):
            if lbl.y() >= viewport_top:
                topmost_visible_index = i
                break
        
        if topmost_visible_index != -1 and self.model.current_index != topmost_visible_index:
            self.model.current_index = topmost_visible_index
            self._update_strip_selection()
            self._update_page_selection()

        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()

            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                if i not in self.page_pixmaps:
                    # load original image
                    orig = self._load_pixmap(self.model.images[i])
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
        self.strip_mode_panel.hide()
        if len(self.page_thumbnail_widgets) > 0:
            for widget in self.page_thumbnail_widgets:
                widget._update_margins(QMargins(0,0,10,0))

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

    def _setup_strip_mode_panel(self):
        self.strip_thumbnails_widget = QWidget()
        self.strip_thumbnails_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        self.strip_thumbnails_layout = QVBoxLayout(self.strip_thumbnails_widget)
        self.strip_thumbnails_layout.setSpacing(0)
        self.strip_thumbnails_layout.addStretch()
        self.strip_mode_panel.set_content_widget(self.strip_thumbnails_widget)

    def _update_strip_mode_thumbnails(self):
        for i in reversed(range(self.strip_thumbnails_layout.count() - 1)):
            self.strip_thumbnails_layout.itemAt(i).widget().setParent(None)
        self.strip_thumbnail_widgets.clear()

        images = self.model.images
        for i, image_path in enumerate(images):
            widget = ThumbnailWidget(i, str(i+1), show_label=False, fixed_width=100)
            widget.clicked.connect(self._change_page_by_strip_thumbnail)
            self.strip_thumbnails_layout.insertWidget(i, widget)
            self.strip_thumbnail_widgets.append(widget)

            if image_path == "placeholder":
                self._on_strip_thumbnail_loaded(i, empty_placeholder())
            else:
                load_func = lambda path: load_pixmap_for_thumbnailing(path, target_width=100)
                worker = ThumbnailWorker(i, image_path, load_func)
                worker.signals.finished.connect(self._on_strip_thumbnail_loaded)
                self.thread_pool.start(worker)
        
        self._update_strip_selection()

    def _on_strip_thumbnail_loaded(self, index, pixmap):
        if index < len(self.strip_thumbnail_widgets):
            self.strip_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_strip_selection(self):
        if self.current_strip_thumbnail:
            self.current_strip_thumbnail.set_selected(False)

        if self.model.current_index < len(self.strip_thumbnail_widgets):
            self.current_strip_thumbnail = self.strip_thumbnail_widgets[self.model.current_index]
            self.current_strip_thumbnail.set_selected(True)

    def _change_page_by_strip_thumbnail(self, index: int):
        self._scroll_to_page(index)

    def _scroll_to_page(self, index: int):
        if self.scroll_area and 0 <= index < len(self.page_labels):
            label = self.page_labels[index]
            self.scroll_area.verticalScrollBar().setValue(label.y())

    def back_to_grid(self):
        if self.back_to_grid_callback:
            self.close()
            self.back_to_grid_callback()
