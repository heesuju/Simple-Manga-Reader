import math
import os
from typing import List, Union
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QScrollArea, QSizePolicy, QPinchGesture, QStackedWidget, QGridLayout
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QMovie, QImage, QMouseEvent, QIcon
from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins, QPropertyAnimation, pyqtSignal, QSize, QUrl, QRectF, QSizeF

from src.enums import ViewMode
from src.ui.page_panel import PagePanel
from src.ui.chapter_panel import ChapterPanel
from src.ui.top_panel import TopPanel
from src.ui.slider_panel import SliderPanel
from src.ui.video_control_panel import VideoControlPanel
from src.ui.image_view import ImageView



from src.data.reader_model import ReaderModel
from src.utils.database_utils import get_db_connection
from src.utils.img_utils import get_chapter_number
from src.workers.view_workers import ChapterLoaderWorker, PixmapLoader, WorkerSignals, VIDEO_EXTS

from src.ui.viewer.image_viewer import ImageViewer
from src.ui.viewer.video_viewer import VideoViewer
from src.ui.viewer.strip_viewer import StripViewer





class ReaderView(QWidget):
    back_pressed = pyqtSignal()
    zoom_changed = pyqtSignal(str)
    request_fullscreen_toggle = pyqtSignal()

    def __init__(self, series: object, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None):
        super().__init__()
        self.current_viewer = None
        self.grabGesture(Qt.GestureType.PinchGesture)

        self.model = ReaderModel(series, manga_dirs, index, start_file, images)
        self.model.refreshed.connect(self.on_model_refreshed)
        self.model.image_loaded.connect(self._load_image)
        self.model.double_image_loaded.connect(self._load_double_images)
        self.model.layout_updated.connect(self.on_layout_updated)
        self.model.page_updated.connect(self.on_page_updated)

        self.back_to_grid_callback = None

        self.scroll_area = None
        self.vertical_container = None
        self.vbox = None
        
        self.slider_panel = None

        self._last_total_scale = 1.0
        
        self.thread_pool = QThreadPool()

        self.original_view_mouse_press = None
        self.is_zoomed = False

        self.page_slideshow_timer = QTimer(self)
        self.page_slideshow_timer.timeout.connect(self.show_next)

        self.slideshow_speeds = [4000, 2000, 500] # ms
        self.current_slideshow_speed_index = 0
        self.slideshow_repeat = False

        self.panels_visible = True
        self.mouse_press_pos = None

        self.last_zoom_mode = "Fit Page"
        
        self._setup_ui()

        # Viewers
        self.image_viewer = ImageViewer(self)
        self.video_viewer = VideoViewer(self)
        self.strip_viewer = StripViewer(self)
        self.current_viewer = self.image_viewer
        
        self._load_chapter_async(start_from_end=self.model.start_file is None and len(self.model.images) == 0)

    def _setup_ui(self):
        self.loading_label = QLabel("Loading...", self)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; font-size: 24px;")
        self.loading_label.hide()

        self.back_icon = QIcon("assets/icons/back.png")

        # Scene/view
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.viewport().setMouseTracking(True)
        self.view.setScene(self.scene)
        self.view.viewport().installEventFilter(self)

        self.media_stack = QStackedWidget()
        self.media_stack.addWidget(self.view)

        self.back_btn = QPushButton()
        self.back_btn.setIcon(self.back_icon)
        self.back_btn.setIconSize(QSize(32, 32))
        self.back_btn.setFixedSize(QSize(32, 32))
        self.back_btn.setStyleSheet("border: none; background: transparent;")
        self.back_btn.clicked.connect(self.back_to_grid)

        self.layout_btn = QPushButton("Double")
        self.layout_btn.clicked.connect(self.toggle_layout)

        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)

        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self.media_stack, 0, 0)

        # Create and add the scroll area for vertical view, but hide it initially
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setMouseTracking(True)
        self.scroll_area.viewport().setMouseTracking(True)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.vertical_container = QWidget()
        self.vbox = QVBoxLayout(self.vertical_container)
        self.vbox.setSpacing(0)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.vertical_container)
        
        # Note: Connection to valueChanged handled by StripViewer now
        self.scroll_area.viewport().installEventFilter(self)
        main_layout.addWidget(self.scroll_area, 0, 0)
        self.scroll_area.hide()

        # 1. Create all panel widgets first
        self.top_panel = TopPanel(self)
        self.page_panel = PagePanel(self, model=self.model, on_page_changed=self.change_page)
        self.page_panel.reload_requested.connect(self.reload_chapter)
        self.video_control_panel = VideoControlPanel(self)
        self.video_control_panel.raise_()
        self.slider_panel = SliderPanel(self, model=self.model)
        self.chapter_panel = ChapterPanel(self, model=self.model, on_chapter_changed=self.set_chapter)

        # Add panels to the layout
        main_layout.addWidget(self.top_panel, 0, 0, Qt.AlignmentFlag.AlignTop)
        
        # Create a container for the bottom panels
        bottom_container = QWidget(self)
        bottom_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        bottom_layout = QVBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        bottom_container.setLayout(bottom_layout)

        bottom_layout.addWidget(self.page_panel)        
        bottom_layout.addWidget(self.chapter_panel)
        bottom_layout.addWidget(self.slider_panel)
                
        main_layout.addWidget(bottom_container, 0, 0, Qt.AlignmentFlag.AlignBottom)

        self.chapter_panel._update_chapter_thumbnails(self.model.chapters)

        # 2. Add control widgets to the panels
        self.top_panel.set_series_title(self.model.series.get("name"))
        self.top_panel.add_back_button(self.back_btn)
        self.top_panel.add_layout_button(self.layout_btn)

        # 3. Connect signals from all panels (VideoControlPanel connected in VideoViewer)
        self.video_control_panel.hide()

        self.slider_panel.valueChanged.connect(self.change_page_from_slider)
        self.top_panel.slideshow_clicked.connect(self.start_page_slideshow)
        self.top_panel.speed_changed.connect(self._on_slideshow_speed_changed)
        self.top_panel.repeat_changed.connect(self._on_slideshow_repeat_changed)
        self.slider_panel.page_changed.connect(self.change_page)
        self.slider_panel.chapter_changed.connect(self.set_chapter)
        self.slider_panel.page_input_clicked.connect(self._show_page_panel)
        self.slider_panel.chapter_input_clicked.connect(self._show_chapter_panel)
        self.slider_panel.zoom_mode_changed.connect(self.set_zoom_mode)
        self.slider_panel.zoom_reset.connect(self.reset_zoom)
        self.slider_panel.fullscreen_requested.connect(self.toggle_fullscreen)

        self.zoom_changed.connect(self.slider_panel.set_zoom_text)

        self.page_panel.hide_content()
        self.chapter_panel.hide_content()

        self.original_view_mouse_press = self.view.mousePressEvent
        self.original_view_mouse_release = self.view.mouseReleaseEvent
        self.view.mousePressEvent = self._overlay_mouse_press
        self.view.mouseReleaseEvent = self._overlay_mouse_release

    def _update_zoom(self, factor: float, update_last_mode: bool = True):
        """Zoom the view using GPU-accelerated transformation.""" 
        self.view.resetTransform()  # reset previous zoom
        self.view.scale(factor, factor)
        zoom_str = f"{factor*100:.0f}%"
        if update_last_mode:
            self.last_zoom_mode = zoom_str
        self.zoom_changed.emit(zoom_str)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.current_viewer:
            self.current_viewer.on_resize(ev)
        
        QTimer.singleShot(0, self.apply_last_zoom)

    def _on_slideshow_speed_changed(self):
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer.current_scroll_speed_index = (self.strip_viewer.current_scroll_speed_index + 1) % len(self.strip_viewer.scroll_speeds)
            speed_text = f"{int(self.strip_viewer.scroll_speeds[self.strip_viewer.current_scroll_speed_index]/5)}x"
            self.top_panel.speed_button.setText(speed_text)
            if self.strip_viewer.strip_scroll_timer.isActive():
                self.strip_viewer.strip_scroll_timer.start(self.strip_viewer.scroll_interval)
            return

        self.current_slideshow_speed_index = (self.current_slideshow_speed_index + 1) % len(self.slideshow_speeds)
        current_speed_s = 4000 / self.slideshow_speeds[self.current_slideshow_speed_index]
        if current_speed_s < 1.0 and current_speed_s % 1 != 0:
            self.top_panel.speed_button.setText(f"{round(current_speed_s, 1)}x".replace("0", ""))
        else:
            self.top_panel.speed_button.setText(f"{int(current_speed_s)}x")

        if self.page_slideshow_timer.isActive():
            self.page_slideshow_timer.start(self.slideshow_speeds[self.current_slideshow_speed_index])

    def _on_slideshow_repeat_changed(self, is_checked: bool):
        self.slideshow_repeat = is_checked
        # VideoViewer uses this? Or its own? VideoViewer has self.video_repeat. 
        # But maybe we should sync them?
        # VideoViewer updates its own repetition via signal from VideoControlPanel, which is separate from SliderPanel.
        pass

    def start_page_slideshow(self):
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer.start_page_slideshow()
            return

        if self.page_slideshow_timer.isActive():
            self.stop_page_slideshow()
        else:
            self.page_slideshow_timer.start(self.slideshow_speeds[self.current_slideshow_speed_index])
            self.top_panel.set_slideshow_state(True)

    def stop_page_slideshow(self):
        self.page_slideshow_timer.stop()
        self.strip_viewer.stop_page_slideshow()
        self.top_panel.set_slideshow_state(False)

    def on_model_refreshed(self):
        if not self.model.images:
            QMessageBox.information(self, "No images", f"No images found in: {self.model.manga_dir}")

        self.page_panel._update_page_thumbnails(self.model)
        self.chapter_panel._update_chapter_selection(self.model.chapter_index)

        if self.slider_panel:
            self.slider_panel.set_range(len(self.model.images) - 1)
            self.slider_panel.set_value(self.model.current_index)
            self.slider_panel.set_chapter(self.model.chapter_index + 1, len(self.model.chapters))
            self.slider_panel.update_alt_indicators(self.model.images)
        else:
            self.slider_panel.set_range(0)
            self.slider_panel.set_value(0)

        self.page_panel._update_page_selection(self.model.current_index)

        self.model.update_layout()

        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer.setup_items(self.model.images)

    def on_layout_updated(self):
        self.page_panel.model = self.model
        self.page_panel._update_page_thumbnails(self.model)
        self.page_panel._update_page_selection(self.model.current_index)
        
        if self.slider_panel:
            self.slider_panel.set_range(len(self.model.images) - 1)
            self.slider_panel.set_value(self.model.current_index)
            self.slider_panel.update_alt_indicators(self.model.images)
        else:
            self.slider_panel.set_range(0)
            self.slider_panel.set_value(0)

        # Switch Viewer
        if self.model.view_mode == ViewMode.STRIP:
             new_viewer = self.strip_viewer
        else:
             # Default to image viewer, but if it is actually video, _load_image will handle deferred?
             # But we need basic UI setup.
             # If we are in Single mode, we might be watching a video.
             # But on layout update, we transition.
             if self.model.images and self.model.current_index < len(self.model.images):
                 ext = os.path.splitext(self.model.images[self.model.current_index].path)[1].lower()
                 if ext in VIDEO_EXTS:
                     new_viewer = self.video_viewer
                 else:
                     new_viewer = self.image_viewer
             else:
                 new_viewer = self.image_viewer
        
        if self.current_viewer != new_viewer:
            self.current_viewer.set_active(False)
            self.current_viewer = new_viewer
            self.current_viewer.set_active(True)
            
        if self.model.view_mode == ViewMode.SINGLE:
            self.layout_btn.setText("Single")
        elif self.model.view_mode == ViewMode.DOUBLE:
            self.layout_btn.setText("Double")
        else:
            self.layout_btn.setText("Strip")

        # Reload content
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer.load(None) 
        else:
             if self.model.images and self.model.current_index < len(self.model.images):
                  self.model.load_image()

    def on_page_updated(self, page_index: int):
        self.page_panel.refresh_thumbnail(page_index)
        
        # Update slider indicators
        if self.slider_panel:
            self.slider_panel.update_alt_indicators(self.model.images)
        
        # If the updated page is the current one (or visible in double view), reload the viewer
        should_reload = False
        if self.model.view_mode == ViewMode.SINGLE:
            if self.model.current_index == page_index:
                should_reload = True
        elif self.model.view_mode == ViewMode.DOUBLE:
             # Check if page_index is currently visible
             # In double mode logic (ReaderModel.load_image), we load current_index and next if applicable.
             # Actually, ReaderModel.load_image uses:
             # page1 = images[self.current_index]
             # page2 = images[self.current_index + 1]
             # So we check if page_index matches either.
             if abs(page_index - self.model.current_index) <= 1:
                 should_reload = True
        elif self.model.view_mode == ViewMode.STRIP:
            should_reload = True

        if should_reload:
            self.model.load_image()
            if self.model.view_mode == ViewMode.STRIP:
                self.strip_viewer.load(None)
                 
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.BackButton:
            self.back_to_grid()
        return super().mousePressEvent(event)

    def _overlay_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press_pos = event.position()
        self.original_view_mouse_press(event)

    def _overlay_mouse_release(self, event):
        self.original_view_mouse_release(event)

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

        left_area = w * 0.3
        right_area = w * 0.7

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
            self.top_panel.show()
            self.slider_panel.show()
        else:
            self.top_panel.hide()
            self.slider_panel.hide()

            if self.page_panel.content_area.isVisible():
                self.page_panel.hide_content()

            if self.chapter_panel.content_area.isVisible():
                self.chapter_panel.hide_content()

    def eventFilter(self, obj, event):
        if self.current_viewer:
             if self.current_viewer == self.strip_viewer and obj is self.scroll_area.viewport():
                 if self.strip_viewer.handle_event(event):
                     # handled
                     return True
             # Delegate other events if needed
             
        if obj is self.view.viewport():
            if event.type() == QEvent.Type.MouseMove:
                if self.video_viewer.video_item and self.video_viewer.video_item.isVisible():
                    view_height = self.height()
                    y = event.position().y()
                    bottom_area_height = view_height * 0.3
                    if view_height - y < bottom_area_height:
                        if not self.video_control_panel.isVisible():
                            self.video_control_panel.show()
                            self._reposition_video_control_panel()
                    else:
                        if self.video_control_panel.isVisible() and not self.video_control_panel.underMouse():
                            self.video_control_panel.hide()

        return super().eventFilter(obj, event)

    def _load_image(self, path: str):
        # Determine viewer type
        ext = os.path.splitext(path)[1].lower()
        is_video = ext in VIDEO_EXTS
        
        target_viewer = self.video_viewer if is_video else self.image_viewer
        
        if self.model.view_mode != ViewMode.STRIP:
             if self.current_viewer != target_viewer:
                 self.current_viewer.set_active(False)
                 self.current_viewer = target_viewer
                 self.current_viewer.set_active(True)
        
        if self.current_viewer == self.strip_viewer:
             # Already handled by setup?
             pass
        else:
             self.current_viewer.load(path)

        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model.current_index)

    def _load_double_images(self, image1_path, image2_path):
        if self.current_viewer != self.image_viewer:
             self.current_viewer.set_active(False)
             self.current_viewer = self.image_viewer
             self.current_viewer.set_active(True)
             
        self.image_viewer.load((image1_path, image2_path))
        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model.current_index)

    def set_zoom_mode(self, mode: str):
        self.last_zoom_mode = mode
        self.current_viewer.zoom(mode)

    def reset_zoom(self):
        self.set_zoom_mode("Fit Page")

    def apply_last_zoom(self):
        self.set_zoom_mode(self.last_zoom_mode)
        


    def show_next(self):
        if not self.model.images:
            return
        if self.model.view_mode == ViewMode.STRIP:
            self._change_chapter(1)
            return
        step = 2 if self.model.view_mode == ViewMode.DOUBLE else 1
        if self.model.current_index + step < len(self.model.images):
            self.model.current_index += step
            self.model.load_image()
        else:
            if self.page_slideshow_timer.isActive() and self.slideshow_repeat:
                self.model.current_index = 0
                self.model.load_image()
            else:
                self._change_chapter(1)

    def show_prev(self):
        if not self.model.images:
            return
        if self.model.view_mode == ViewMode.STRIP:
            self._change_chapter(-1)
            return
        step = 2 if self.model.view_mode == ViewMode.DOUBLE else 1
        if self.model.current_index - step >= 0:
            self.model.current_index -= step
            self.model.load_image()
        else:
            self._change_chapter(-1)

    def change_page(self, page:int):
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer._scroll_to_page(page - 1)
            self.page_panel._update_page_selection(page - 1)
            self.slider_panel.set_value(page - 1)
            return

        self.model.change_page(page)
        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model.current_index)

    def change_page_from_slider(self, page_index: int):
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer._scroll_to_page(page_index)
            return
        self.model.change_page(page_index+1)

    def _show_page_panel(self):
        if self.chapter_panel.content_area.isVisible():
            self.chapter_panel.hide_content()
        self.page_panel.show_content()

    def _show_chapter_panel(self):
        if self.page_panel.content_area.isVisible():
            self.page_panel.hide_content()
        self.chapter_panel.show_content()

    def set_chapter(self, chapter:int):
        if self.model.set_chapter(chapter):
            self._load_chapter_async(start_from_end=False)
            self.chapter_panel._update_chapter_selection(self.model.chapter_index)

    def reload_chapter(self):
        self._load_chapter_async(start_from_end=False)

    def _change_chapter(self, direction: int):
        start_from_end = direction == -1
        if self.model.change_chapter(direction):
            self._load_chapter_async(start_from_end=start_from_end)
            self.chapter_panel._update_chapter_selection(self.model.chapter_index)

    def _load_chapter_async(self, start_from_end: bool):
        self.page_panel.stop_loading_thumbnails()
        self.loading_label.show()
        # Clean current view
        if self.current_viewer:
             self.current_viewer.cleanup()
             
        self.scene.clear()
        self.image_viewer.reset()
        self.video_viewer.reset()
        
        worker = ChapterLoaderWorker(
            manga_dir=self.model.manga_dir,
            series_path=str(self.model.series['path']),
            start_from_end=start_from_end,
            load_pixmap_func=self.image_viewer._load_pixmap
        )
        worker.signals.finished.connect(self._on_chapter_loaded)
        self.thread_pool.start(worker)

    def _on_chapter_loaded(self, result: dict):
        if result["manga_dir"] != self.model.manga_dir:
            return

        self.loading_label.hide()
        # Use set_images to trigger Page creation and grouping
        self.model.set_images(result["images"])
        
        if result.get("start_from_end", False):
            self.model.current_index = max(0, len(self.model.images) - 1)
        else:
            self.model.current_index = 0

        self.model.refresh()
        self.model.layout_updated.emit(self.model.view_mode)
        
        if self.model.images:
             # Pass the path string of the current page
             self.model.load_image()


    def back_to_grid(self):
        self.page_panel.stop_loading_thumbnails()
        if self.current_viewer:
             self.current_viewer.cleanup()
        self.back_pressed.emit()

    def _reposition_video_control_panel(self):
        view_width = self.width()
        panel_width = int(view_width * 0.6)
        panel_height = self.video_control_panel.sizeHint().height()
        x = (view_width - panel_width) // 2
        slider_height = self.slider_panel.height() if self.slider_panel.isVisible() else 0
        margin = 40
        y = self.height() - panel_height - slider_height - margin
        self.video_control_panel.setGeometry(x, y, panel_width, panel_height)

    def toggle_fullscreen(self):
        self.request_fullscreen_toggle.emit()
    
    def exit_if_not_fullscreen(self):
        self.request_fullscreen_toggle.emit()
    
    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self.apply_last_zoom)
    
    def toggle_layout(self, mode:ViewMode=None):
        self.model.toggle_layout(mode)
