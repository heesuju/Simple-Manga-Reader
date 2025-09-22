import math
from typing import List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsScene,QGraphicsPixmapItem, 
    QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QScrollArea, QSizePolicy, QPinchGesture
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor
from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins

from src.enums import ViewMode
from src.ui.page_panel import PagePanel
from src.ui.chapter_panel import ChapterPanel
from src.ui.image_view import ImageView
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.data.reader_model import ReaderModel
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

        self.original_view_mouse_press = None
        self.is_zoomed = False

        self._setup_ui()
        self.showFullScreen()
        self.model.refresh()
        self.chapter_panel._update_chapter_selection(self.model.chapter_index)

    def _setup_ui(self):
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.setScene(self.scene)

        self.back_btn = QPushButton("⬅ Back to Grid")
        self.back_btn.clicked.connect(self.back_to_grid)

        self.layout_btn = QPushButton("Double")
        self.layout_btn.clicked.connect(self.toggle_layout)
        
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.back_to_grid)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.view, 1)

        container = QWidget()
        container.setLayout(main_layout)
        container.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(container)

        self.chapter_panel = ChapterPanel(self, self.change_chapter)
        self.chapter_panel.add_control_widget(self.back_btn, 0)
        self.chapter_panel.add_control_widget(self.layout_btn)
        self.page_panel = PagePanel(self, model=self.model, on_page_changed=self.change_page)
        self.chapter_panel._update_chapter_thumbnails(self.model.chapters)

        self.chapter_panel.raise_()
        self.page_panel.raise_()

        self.chapter_panel.installEventFilter(self)
        self.page_panel.installEventFilter(self)
        
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().installEventFilter(self)
        self.original_view_mouse_press = self.view.mousePressEvent
        self.view.mousePressEvent = self._overlay_mouse_press
        self.view.resizeEvent = self.resizeEvent

    def on_model_refreshed(self):
        if not self.model.images:
            QMessageBox.information(self, "No images", f"No images found in: {self.model.manga_dir}")
        self.page_panel._update_page_thumbnails(self.model)
        self.model.update_layout()

    def on_layout_updated(self, view_mode):
        self.page_panel._update_page_thumbnails(self.model)

        if view_mode == ViewMode.SINGLE:
            self.layout_btn.setText("Single")
            self._show_single_layout()
        elif view_mode == ViewMode.DOUBLE:
            self.layout_btn.setText("Double")
            self._show_double_layout()
        else:
            self.layout_btn.setText("Strip")
            self._show_vertical_layout()

        QTimer.singleShot(0, self._fit_current_image)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_panel_geometries()

    def _update_panel_geometries(self):
        chapter_panel_height = 200 if self.chapter_panel.content_area.isVisible() else 0
        self.chapter_panel.setGeometry(0, 0, self.width(), chapter_panel_height)

        page_panel_height = 200 if self.page_panel.content_area.isVisible() else 0
        self.page_panel.setGeometry(0, self.height() - page_panel_height, self.width(), page_panel_height)

    def mouseMoveEvent(self, event):
        self._handle_panel_visibility(event.pos())
        super().mouseMoveEvent(event)

    def _handle_panel_visibility(self, pos):
        y = pos.y()
        height = self.height()

        top_area_height = height * 0.15
        bottom_area_start = height * 0.85
        
        right_rect = self.rect()
        right_rect.setLeft(int(self.width() * 0.85))

        show_chapter = y <= top_area_height
        show_page = (y >= bottom_area_start) and (self.model.view_mode != ViewMode.STRIP)
        show_strip = (self.model.view_mode == ViewMode.STRIP) and right_rect.contains(pos)

        if show_chapter:
            self.chapter_panel.show_content()
        else:
            self.chapter_panel.hide_content()

        if show_page:
            self.page_panel.show_content()
        else:
            self.page_panel.hide_content()
        
        self._update_panel_geometries()

    
    def _overlay_mouse_press(self, event):
        """Trigger prev/next when clicking on left/right 20% of screen."""
        if not math.isclose(self.view._zoom_factor, 1.0):
            self.original_view_mouse_press(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            w = self.view.width()
            x = event.position().x()

            left_area = w * 0.2
            right_area = w * 0.8

            if x <= left_area:
                self.show_prev()
                event.accept()
            elif x >= right_area:
                self.show_next()
                event.accept()
            else:
                self.original_view_mouse_press(event)
        else:
            self.original_view_mouse_press(event)

    def event(self, e):
        if e.type() == QEvent.Type.Gesture:
            gesture = e.gesture(Qt.GestureType.PinchGesture)
            if gesture:
                self.handle_pinch(gesture)
                return True
        return super().event(e)

    def eventFilter(self, obj, event):
        # Unified mouse move handling using global coordinates
        if event.type() == QEvent.Type.MouseMove and obj in (
            self.chapter_panel, self.page_panel,
            self.view.viewport(), 
            self.scroll_area.viewport() if self.scroll_area else None
        ):
            global_pos = event.globalPosition().toPoint()
            window_pos = self.mapFromGlobal(global_pos)
            
            if self.rect().contains(window_pos):
                self._handle_panel_visibility(window_pos)
            
            return False # Pass event to original widget

        # Handle resize for strip mode (existing logic)
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

    def _load_image(self, path: str):
        self.original_pixmap = self._load_pixmap(path)
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(self.original_pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.view.reset_zoom_state()
        self.page_panel._update_page_selection(self.model.current_index)
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

    def show_next(self):
        if not self.model.images:
            return

        if self.model.view_mode == ViewMode.STRIP:
            self._change_chapter(1)  # Go to next chapter
            return

        # Existing logic for Single/Double mode
        step = 2 if self.model.view_mode == ViewMode.DOUBLE else 1
        if self.model.current_index + step < len(self.model.images):
            self.model.current_index += step
            self.model.load_image()
        else:
            self._change_chapter(1)  # Go to next chapter

        self.page_panel._update_page_selection(self.model.current_index)

    def show_prev(self):
        if not self.model.images:
            return

        if self.model.view_mode == ViewMode.STRIP:
            self._change_chapter(-1)  # Go to previous chapter
            return

        # Existing logic for Single/Double mode
        step = 2 if self.model.view_mode == ViewMode.DOUBLE else 1
        if self.model.current_index - step >= 0:
            self.model.current_index -= step
            self.model.load_image()
        else:
            self._change_chapter(-1)  # Go to previous chapter

        self.page_panel._update_page_selection(self.model.current_index)

    def change_page(self, page:int):
        self.model.change_page(page)
        self.page_panel._update_page_selection(self.model.current_index)

    def change_chapter(self, chapter:int):
        self.model.change_chapter(chapter)
        self.chapter_panel._update_chapter_selection(self.model.chapter_index)

    def _change_chapter(self, direction: int):
        new_index = self.model.chapter_index + direction
        total_chapters = len(self.model.chapters)

        if 0 <= new_index < total_chapters:
            self.model.chapter_index = new_index
            self.model.manga_dir = self.model.chapters[self.model.chapter_index]
            self.model.images = []  # force reload
            self.chapter_panel._update_chapter_selection(self.model.chapter_index)

            # For 'prev', start from the end of the chapter
            start_from_end = (direction == -1)
            self.model.refresh(start_from_end=start_from_end, preserve_view_mode=True)

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
        # self.strip_mode_panel.hide()
        for n, widget in enumerate(self.page_panel.page_thumbnail_widgets):
            if n % 2 == 0:
                widget._update_margins(QMargins(0,0,0,0))
            else:
                widget._update_margins(QMargins(0,0,10,0))

        self.view.show()
        if self.scroll_area:
            self.scroll_area.hide()

    def _show_vertical_layout(self):
        self.page_panel.hide()
        self.view.hide()

        if self.scroll_area is None:
            self.scroll_area = QScrollArea(self.centralWidget())
            self.scroll_area.setMouseTracking(True)
            self.scroll_area.viewport().setMouseTracking(True)
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.vertical_container = QWidget()
            self.vbox = QVBoxLayout(self.vertical_container)
            self.vbox.setSpacing(0)
            self.vbox.setContentsMargins(0, 0, 0, 0)
            self.scroll_area.setWidget(self.vertical_container)

            main_layout = self.centralWidget().layout()
            main_layout.insertWidget(1, self.scroll_area)

            self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_images)
            self.scroll_area.viewport().installEventFilter(self)

        self.scroll_area.verticalScrollBar().setValue(0)

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
            self.page_panel._update_page_selection(self.model.current_index)

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
        if len(self.page_panel.page_thumbnail_widgets) > 0:
            for widget in self.page_panel.page_thumbnail_widgets:
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

    def _change_page_by_strip_thumbnail(self, index: int):
        self._scroll_to_page(index)

    def _scroll_to_page(self, index: int):
        if self.scroll_area and 0 <= index < len(self.page_labels):
            label = self.page_labels[index]
            self.scroll_area.verticalScrollBar().setValue(label.y())

    def back_to_grid(self):
        if self.back_to_grid_callback:
            self.close()
            self.back_to_grid_callback(self.model.manga_dir)
