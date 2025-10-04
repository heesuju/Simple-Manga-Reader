import math
from typing import List
import numpy as np
import cv2
import os
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsScene,QGraphicsView,QGraphicsPixmapItem, 
    QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QScrollArea, QSizePolicy, QPinchGesture
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QMovie, QImage, QMouseEvent
from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins, QPropertyAnimation, QSequentialAnimationGroup, QRectF, pyqtProperty

from src.enums import ViewMode
from src.ui.page_panel import PagePanel
from src.ui.chapter_panel import ChapterPanel
from src.ui.image_view import ImageView
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.data.reader_model import ReaderModel
from src.core.thumbnail_worker import get_common_size_ratio
from src.utils.segmentation import get_panel_coordinates
from src.utils.database_utils import get_db_connection
from src.utils.img_utils import get_chapter_number

class FitInViewAnimation(QPropertyAnimation):
    def __init__(self, target, parent=None):
        super().__init__(target, b"", parent)
        self.setTargetObject(target)

    def updateCurrentValue(self, value):
        self.targetObject().fitInView(value, Qt.AspectRatioMode.KeepAspectRatio)

from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins, QPropertyAnimation, QSequentialAnimationGroup, QRectF, QParallelAnimationGroup, pyqtSignal, QRunnable, pyqtSlot, QObject

class WorkerSignals(QObject):
    finished = pyqtSignal(int, QPixmap)

class PixmapLoader(QRunnable):
    def __init__(self, path: str, index: int, reader_view):
        super().__init__()
        self.path = path
        self.index = index
        self.reader_view = reader_view
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        pixmap = self.reader_view._load_pixmap(self.path)
        self.signals.finished.emit(self.index, pixmap)

class ReaderView(QMainWindow):
    back_pressed = pyqtSignal()

    def __init__(self, series: object, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None):
        super().__init__()
        self.setWindowTitle("Manga Reader")
        self.grabGesture(Qt.GestureType.PinchGesture)

        self.model = ReaderModel(series, manga_dirs, index, start_file, images)
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
        self._strip_zoom_factor = 1.0

        self.thread_pool = QThreadPool()

        self.original_view_mouse_press = None
        self.is_zoomed = False

        self.guided_reading_animation = None
        self.continuous_play = False
        self.page_slideshow_timer = QTimer(self)
        self.page_slideshow_timer.timeout.connect(self.show_next)

        self.user_interrupted_animation = False
        self.is_dragging_animation = False
        self.last_pan_pos = None

        self.panels_visible = True
        self.mouse_press_pos = None

        self.is_panning = False
        self.last_pan_pos = None

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

        self.chapter_panel = ChapterPanel(self, model=self.model, on_chapter_changed=self.change_chapter)
        self.chapter_panel.add_control_widget(self.back_btn, 0)
        self.chapter_panel.add_control_widget(self.layout_btn)
        self.chapter_panel.play_button_clicked.connect(self.start_guided_reading)
        self.chapter_panel.slideshow_button_clicked.connect(self.start_page_slideshow)
        self.chapter_panel.continuous_play_changed.connect(self.set_continuous_play)
        self.chapter_panel.translation_ready.connect(self._on_translation_ready)
        self.page_panel = PagePanel(self, model=self.model, on_page_changed=self.change_page)
        self.chapter_panel._update_chapter_thumbnails(self.model.chapters)

        self.chapter_panel.raise_()
        self.page_panel.raise_()

        self.chapter_panel.installEventFilter(self)
        self.page_panel.installEventFilter(self)
        
        self.original_view_mouse_press = self.view.mousePressEvent
        self.view.mousePressEvent = self._overlay_mouse_press
        self.view.mouseReleaseEvent = self._overlay_mouse_release
        self.view.resizeEvent = self.resizeEvent


    def start_guided_reading(self):
        if self.guided_reading_animation and self.guided_reading_animation.state() == QPropertyAnimation.State.Running:
            self.stop_guided_reading()
            return

        current_image_path = self.model.images[self.model.current_index]
        if '|' in current_image_path:
            # Not supported for zip files yet
            return

        panel_coordinates = get_panel_coordinates(current_image_path)
        if not panel_coordinates:
            return

        # Instantly move to the first panel
        x, y, w, h = panel_coordinates[0]
        self.view.setSceneRect(QRectF(x, y, w, h))
        view_rect = self.view.viewport().rect()
        x_zoom = view_rect.width() / w
        y_zoom = view_rect.height() / h
        target_zoom = min(x_zoom, y_zoom)
        self.view._zoom = target_zoom

        self.guided_reading_animation = QSequentialAnimationGroup(self)
        self.guided_reading_animation.addPause(500)

        for x, y, w, h in panel_coordinates[1:]:
            parallel_animation = QParallelAnimationGroup(self)

            rect_animation = QPropertyAnimation(self.view, b"sceneRect")
            rect_animation.setDuration(1000)
            rect_animation.setEndValue(QRectF(x, y, w, h))

            zoom_animation = QPropertyAnimation(self.view, b"_zoom")
            zoom_animation.setDuration(1000)
            view_rect = self.view.viewport().rect()
            x_zoom = view_rect.width() / w
            y_zoom = view_rect.height() / h
            target_zoom = min(x_zoom, y_zoom)
            zoom_animation.setEndValue(target_zoom)

            parallel_animation.addAnimation(rect_animation)
            parallel_animation.addAnimation(zoom_animation)

            self.guided_reading_animation.addAnimation(parallel_animation)
            self.guided_reading_animation.addPause(1000)

        self.guided_reading_animation.finished.connect(lambda: self.stop_guided_reading(user_interrupted=False))
        self.guided_reading_animation.start()
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)


    def set_continuous_play(self, enabled: bool):
        self.continuous_play = enabled

    def stop_guided_reading(self, user_interrupted=False):
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        if self.guided_reading_animation:
            self.guided_reading_animation.stop()
            self.guided_reading_animation = None

        if user_interrupted:
            return

        if self.continuous_play:
            self.show_next()
            QTimer.singleShot(1000, self.start_guided_reading)
        else:
            self._fit_current_image()

    def start_page_slideshow(self):
        if self.page_slideshow_timer.isActive():
            self.stop_page_slideshow()
        else:
            self.page_slideshow_timer.start(3000)

    def stop_page_slideshow(self):
        self.page_slideshow_timer.stop()

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


    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.BackButton:
            self.back_to_grid()
        return super().mousePressEvent(event)


    def _overlay_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press_pos = event.position()
        self.original_view_mouse_press(event)

    def _overlay_mouse_release(self, event):
        if self.mouse_press_pos is None or event.button() != Qt.MouseButton.LeftButton:
            return

        # Check if it was a brief click without dragging
        distance = (event.position() - self.mouse_press_pos).manhattanLength()
        if distance > 5:
            self.mouse_press_pos = None
            return

        self.mouse_press_pos = None

        if not math.isclose(self.view._zoom_factor, 1.0):
            return

        w = self.view.width()
        x = event.position().x()

        left_area = w * 0.2
        right_area = w * 0.8

        if x <= left_area:
            self.show_prev()
        elif x >= right_area:
            self.show_next()
        else:
            self._toggle_panels()

    def _toggle_panels(self, visible:bool=None):
        original_state = self.panels_visible

        if visible is not None:
            self.panels_visible = visible    
        else:
            self.panels_visible = not self.panels_visible

        if original_state == self.panels_visible:
            return

        if self.panels_visible:
            self.chapter_panel.show_content()
            self.page_panel.show_content()
        else:
            self.chapter_panel.hide_content()
            self.page_panel.hide_content()
        self._update_panel_geometries()

    def eventFilter(self, obj, event):
        if obj is self.view.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                if self.guided_reading_animation and self.guided_reading_animation.state() == QPropertyAnimation.State.Running:
                    self.stop_guided_reading(user_interrupted=True)

        # Handle resize for strip mode (existing logic)
        if self.model.view_mode == ViewMode.STRIP and self.scroll_area and obj is self.scroll_area.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = True
                    self.last_pan_pos = event.pos()
                    self.mouse_press_pos = event.pos() # For click-detection
                    self.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                if self.is_panning:
                    delta = event.pos() - self.last_pan_pos
                    self.last_pan_pos = event.pos()
                    self.scroll_area.horizontalScrollBar().setValue(self.scroll_area.horizontalScrollBar().value() - delta.x())
                    self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value() - delta.y())
                    self._toggle_panels(False)
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = False
                    self.last_pan_pos = None
                    self.scroll_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                    # Check if it was a click to toggle panels
                    if self.mouse_press_pos and (event.pos() - self.mouse_press_pos).manhattanLength() < 5:
                        self._toggle_panels()
                    return True

            elif event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._strip_zoom_factor = 1.0
                    self._resize_vertical_images()
                    return True

            elif event.type() == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    angle = event.angleDelta().y()
                    factor = 1.25 if angle > 0 else 0.8
                    self._strip_zoom_factor *= factor
                    self._resize_vertical_images()
                    return True # Consume the event to prevent scrolling
                self._toggle_panels(False)

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
        self.movie = None
        if path.lower().endswith(".gif"):
            # Use QMovie for animated gif
            self.movie = QMovie(path)
            self.movie.frameChanged.connect(self._update_movie_frame)
            self.movie.start()
            self.view.reset_zoom_state()
            QTimer.singleShot(0, self._fit_current_image)
            self.page_panel._update_page_selection(self.model.current_index)
        else:
            self.original_pixmap = self._load_pixmap(path)
            self._set_pixmap(self.original_pixmap)
            self.view.reset_zoom_state()
            QTimer.singleShot(0, self._fit_current_image)
            self.page_panel._update_page_selection(self.model.current_index)
            # QTimer.singleShot(0, self._fit_current_image)
    
    def _update_movie_frame(self, frame_number: int):
        if self.movie:
            pixmap = self.movie.currentPixmap()
            if pixmap.isNull():
                return

            # Scale GIF smoothly to match view size
            target_size = self.view.viewport().size()  # or any QSize you want
            scaled_pixmap = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            self._set_pixmap(scaled_pixmap)

    def _set_pixmap(self, pixmap: QPixmap):
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

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
            next_chapter_path = self._get_adjacent_chapter_from_db(1)
            if next_chapter_path:
                new_chapter = next((ch for ch in self.model.chapters if str(Path(ch)) == next_chapter_path), None)
                if new_chapter:
                    self.model.manga_dir = new_chapter
                    self.model.chapter_index = self.model.chapters.index(new_chapter)
                    self.model.images = [] # force reload
                    self.chapter_panel._update_chapter_selection(self.model.chapter_index)
                    self.model.refresh(start_from_end=False, preserve_view_mode=True)

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
            prev_chapter_path = self._get_adjacent_chapter_from_db(-1)
            if prev_chapter_path:
                new_chapter = next((ch for ch in self.model.chapters if str(Path(ch)) == prev_chapter_path), None)
                if new_chapter:
                    self.model.manga_dir = new_chapter
                    self.model.chapter_index = self.model.chapters.index(new_chapter)
                    self.model.images = [] # force reload
                    self.chapter_panel._update_chapter_selection(self.model.chapter_index)
                    self.model.refresh(start_from_end=True, preserve_view_mode=True)

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

    def _get_adjacent_chapter_from_db(self, direction: int):
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get current series ID
        cursor.execute("SELECT id FROM series WHERE path = ?", (self.model.series['path'],))
        series_id_row = cursor.fetchone()
        if not series_id_row:
            conn.close()
            return None
        series_id = series_id_row['id']

        # Get all chapters for the series
        cursor.execute("SELECT path FROM chapters WHERE series_id = ?", (series_id,))
        chapters = [row['path'] for row in cursor.fetchall()]
        conn.close()

        chapters.sort(key=get_chapter_number)

        try:
            if self.model.manga_dir is None:
                return None
            current_chapter_path = str(Path(self.model.manga_dir))
            current_db_index = chapters.index(current_chapter_path)
            next_db_index = current_db_index + direction

            if 0 <= next_db_index < len(chapters):
                return chapters[next_db_index]
        except ValueError:
            # The current chapter path is not in the database list, fall back to original behavior
            pass

        return None

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
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.vertical_container = QWidget()
            self.vbox = QVBoxLayout(self.vertical_container)
            self.vbox.setSpacing(0)
            self.vbox.setContentsMargins(0, 0, 0, 0)
            self.scroll_area.setWidget(self.vertical_container)
            self.scroll_area.setContentsMargins(0, 0, 0, 0)
            self.vertical_container.setContentsMargins(0, 0, 0, 0)

            main_layout = self.centralWidget().layout()
            main_layout.insertWidget(1, self.scroll_area)

            self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_images)
            self.scroll_area.viewport().installEventFilter(self)

        self.scroll_area.verticalScrollBar().setValue(0)

        self._strip_zoom_factor = 1.0

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

            worker = PixmapLoader(self.model.images[i], i, self)
            worker.signals.finished.connect(self._on_image_loaded)
            self.thread_pool.start(worker)

        QTimer.singleShot(0, self._update_visible_images)

    def _on_image_loaded(self, index: int, pixmap: QPixmap):
        if index < len(self.page_labels):
            self.page_pixmaps[index] = pixmap
            # Only resize if the label is visible
            lbl = self.page_labels[index]
            viewport_rect = self.scroll_area.viewport().rect()
            viewport_top = self.scroll_area.verticalScrollBar().value()
            viewport_bottom = viewport_top + viewport_rect.height()
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()
            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                self._resize_single_label(lbl, pixmap)

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
                if i in self.page_pixmaps:
                    self._resize_single_label(lbl, self.page_pixmaps[i])
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
        w = self.scroll_area.viewport().width() * self._strip_zoom_factor - (self.vbox.contentsMargins().left() + self.vbox.contentsMargins().right())
        if w <= 0 or orig_pix.isNull():
            return
        scaled = orig_pix.scaledToWidth(int(w), Qt.TransformationMode.SmoothTransformation)
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
        self.back_pressed.emit()

    def _on_translation_ready(self, modified_image):
        # Convert cv2 image (BGR) to QImage (RGB)
        height, width, channel = modified_image.shape
        bytes_per_line = 3 * width
        q_image = QImage(modified_image.data, width, height, bytes_per_line, QImage.Format.Format_BGR888)
        
        # Convert QImage to QPixmap
        pixmap = QPixmap.fromImage(q_image)
        
        # Update the scene
        self._set_pixmap(pixmap)
