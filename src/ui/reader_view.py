from typing import List, Union, Tuple
from pathlib import Path
import math
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QPushButton, QHBoxLayout, QVBoxLayout, QLabel, QApplication,
    QMessageBox, QScrollArea, QSizePolicy, QPinchGesture, QStackedWidget, QGridLayout,
    QFrame
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QMovie, QImage, QMouseEvent, QIcon
from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins, QPropertyAnimation, pyqtSignal, QSize, QUrl, QRectF, QSizeF
from src.utils.resource_utils import resource_path
from src.ui.styles import FLAT_BUTTON_STYLE

from src.enums import ViewMode
from src.ui.page_panel import PagePanel
from src.ui.alt_panel import AltPanel
from src.ui.chapter_panel import ChapterPanel
from src.ui.top_panel import TopPanel
from src.ui.slider_panel import SliderPanel
from src.ui.video_control_panel import VideoControlPanel
from src.ui.image_view import ImageView
from src.enums import Language
from src.ui.components.selection_panel import SelectionPanel

from src.data.reader_model import ReaderModel
from src.utils.database_utils import get_db_connection
from src.utils.img_utils import get_chapter_number
from src.workers.view_workers import ChapterLoaderWorker, PixmapLoader, WorkerSignals, VIDEO_EXTS, IMAGE_EXTS, ArchiveExtractionWorker, ImageInfoWorker
# from src.workers.translate_worker import TranslateWorker
from src.core.translation_service import TranslationService

from src.ui.viewer.image_viewer import ImageViewer
from src.ui.viewer.video_viewer import VideoViewer
from src.ui.viewer.strip_viewer import StripViewer


class ReaderView(QWidget):
    back_pressed = pyqtSignal()
    zoom_changed = pyqtSignal(str)
    request_fullscreen_toggle = pyqtSignal()
    current_chapter_changed = pyqtSignal(object, str)

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
        
        
        TranslationService.instance().task_status_changed.connect(self._on_translation_status_changed_global)

        self._load_chapter_async(start_from_end=False)


    def _on_translation_status_changed_global(self, image_path: str, lang_code: str, status: str):
        """
        Handle updates from the global translation service via fast O(1) lookup.
        """
        if not self.model.images or not self.model.manga_dir:
             return

        # Optimization 1: Quick check if path belongs to current chapter folder
        if str(self.model.manga_dir) not in str(image_path):
             # Not in current chapter -> ignore
             pass

        # Optimization 2: Use Model's Hash Map (O(1))
        found_page_index = self.model.get_page_index(image_path)

        if found_page_index == -1:
            return

        # 2. Update the model for that page if finished
        if status == "finished":
             self.model.update_page_variants(found_page_index)

        # 3. If it is the CURRENT page (or visible), update UI
        is_visible = False
        if found_page_index == self.model.current_index:
            is_visible = True
        elif self.model.view_mode == ViewMode.DOUBLE and abs(found_page_index - self.model.current_index) <= 1:
            is_visible = True
        
        if is_visible:
             self.update_top_panel()
             
             if status == "translating":
                  self.loading_label.setText(f"Translating to {lang_code}...")
                  self.loading_label.show()
             elif status == "finished":
                  self.loading_label.hide()
                  self.model.load_image()
             elif status == "queued":
                 self.top_panel.update_translate_button("QUEUED")
             elif status is None:
                 self.top_panel.update_translate_button(None)

    def _setup_ui(self):
        self.loading_label = QLabel("Loading...", self)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; font-size: 24px;")
        self.loading_label.hide()
        
        self.setAcceptDrops(True)

        self.back_icon = QIcon(resource_path("assets/icons/back.svg"))
        self.layout_single_icon = QIcon(resource_path("assets/icons/layout_single.svg"))
        self.layout_double_icon = QIcon(resource_path("assets/icons/layout_double.svg"))
        self.layout_strip_icon = QIcon(resource_path("assets/icons/layout_strip.svg"))

        # Scene/view
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.viewport().setMouseTracking(True)
        self.view.setScene(self.scene)
        self.view.viewport().installEventFilter(self)
        self.view.translate_requested.connect(self.translate_page)
        # Connect zoom signal to handle HQ restoration
        self.view.zoom_started.connect(self._on_view_zoom_started)

        self.media_stack = QStackedWidget()
        self.media_stack.setFrameShape(QFrame.Shape.NoFrame)
        self.media_stack.setLineWidth(0)
        self.media_stack.setContentsMargins(0, 0, 0, 0)
        self.media_stack.setStyleSheet("border: none; padding: 0px; margin: 0px;")
        self.media_stack.addWidget(self.view)

        self.back_btn = QPushButton()
        self.back_btn.setIcon(self.back_icon)
        self.back_btn.setIconSize(QSize(24, 24))
        self.back_btn.setFixedSize(QSize(32, 32))
        self.back_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.back_btn.clicked.connect(self.back_to_grid)

        self.layout_btn = QPushButton()
        self.layout_btn.setIcon(self.layout_single_icon)
        self.layout_btn.setIconSize(QSize(24, 24))
        self.layout_btn.setFixedSize(QSize(32, 32))
        self.layout_btn.setStyleSheet(FLAT_BUTTON_STYLE)
        self.layout_btn.clicked.connect(self.toggle_layout)

        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next)
        QShortcut(QKeySequence(Qt.Key.Key_Tab), self, activated=self.cycle_current_variant)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_playback)
        QShortcut(QKeySequence(Qt.Key.Key_Paste), self, activated=self._paste_as_alternate_action)
        # Also handle Ctrl+V just in case QKeySequence.StandardKey.Paste is picky
        QShortcut(QKeySequence("Ctrl+V"), self, activated=self._paste_as_alternate_action)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.start_area_selection)

        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self.media_stack, 0, 0)

        # Create and add the scroll area for vertical view, but hide it initially
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("border: none; padding: 0px; margin: 0px;")
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
        self.scroll_area.installEventFilter(self)
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
        self.alt_panel = AltPanel(self, model=self.model)
        self.selection_panel = SelectionPanel(self)

        # Add panels to the layout
        main_layout.addWidget(self.top_panel, 0, 0, Qt.AlignmentFlag.AlignTop)
        
        # Create a container for the bottom panels
        self.bottom_container = QWidget(self)
        self.bottom_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        bottom_layout = QVBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        self.bottom_container.setLayout(bottom_layout)

        bottom_layout.addWidget(self.page_panel)        
        bottom_layout.addWidget(self.chapter_panel)
        bottom_layout.addWidget(self.slider_panel)
                
        main_layout.addWidget(self.bottom_container, 0, 0, Qt.AlignmentFlag.AlignBottom)
        main_layout.addWidget(self.selection_panel, 0, 0, Qt.AlignmentFlag.AlignBottom)
        self.selection_panel.hide()

        # Alt panel is NOT added to the layout manager so we can manually control its geometry
        # as a floating overlay that doesn't trigger grid layout shifts.
        self.alt_panel.setParent(self)


        self.chapter_panel._update_chapter_thumbnails(self.model.chapters)

        # 2. Add control widgets to the panels
        self._update_top_panel_title()
        self.top_panel.add_back_button(self.back_btn)
        self.top_panel.add_layout_button(self.layout_btn)

        # 3. Connect signals from all panels (VideoControlPanel connected in VideoViewer)
        self.video_control_panel.hide()

        self.slider_panel.valueChanged.connect(self.change_page_from_slider)
        self.top_panel.slideshow_clicked.connect(self.start_page_slideshow)
        self.top_panel.speed_changed.connect(self._on_slideshow_speed_changed)
        self.top_panel.repeat_changed.connect(self._on_slideshow_repeat_changed)
        self.top_panel.translate_clicked.connect(self.translate_page)
        self.top_panel.lang_changed.connect(self._on_lang_changed)
        self.slider_panel.page_changed.connect(self.change_page_from_input)
        self.slider_panel.chapter_changed.connect(self.set_chapter)
        self.slider_panel.page_input_clicked.connect(self._show_page_panel)
        self.slider_panel.chapter_input_clicked.connect(self._show_chapter_panel)
        self.slider_panel.zoom_mode_changed.connect(self.set_zoom_mode)
        self.slider_panel.zoom_reset.connect(self.reset_zoom)
        self.slider_panel.fullscreen_requested.connect(self.toggle_fullscreen)

        self.selection_panel.ratio_selected.connect(self.view.set_selection_ratio)
        self.selection_panel.apply_clicked.connect(self._apply_area_selection)
        self.selection_panel.cancel_clicked.connect(self._cancel_area_selection)
        self.view.ratio_changed.connect(self.selection_panel.set_ratio)

        self.zoom_changed.connect(self.slider_panel.set_zoom_text)

        self.page_panel.hide_content()
        self.chapter_panel.hide_content()

        self.page_panel.expand_toggled.connect(lambda expanded: self._on_panel_expand_toggled(self.page_panel, expanded))
        self.chapter_panel.expand_toggled.connect(lambda expanded: self._on_panel_expand_toggled(self.chapter_panel, expanded))
        
        self.page_panel.content_hidden.connect(lambda: QTimer.singleShot(100, self._update_alt_panel_height))
        self.chapter_panel.content_hidden.connect(lambda: QTimer.singleShot(100, self._update_alt_panel_height))

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
        
        if hasattr(self.current_viewer, 'on_zoom_changed'):
            self.current_viewer.on_zoom_changed(zoom_str)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.current_viewer:
            self.current_viewer.on_resize(ev)
        
        # Update expanded panel height if necessary
        if self.page_panel.is_expanded:
            self._update_expanded_panel_height(self.page_panel)
        elif self.chapter_panel.is_expanded:
            self._update_expanded_panel_height(self.chapter_panel)

        # Update alt panel height to fill available vertical space
        self._update_alt_panel_height()

        QTimer.singleShot(0, self.apply_last_zoom)

    def _update_alt_panel_height(self):
        if not hasattr(self, 'alt_panel') or not self.alt_panel.isVisible():
            return
        
        # Ensure layout has run
        self.layout().activate()
        
        total_h = self.height()
        # top_panel.height() can be unreliable during layout transitions, sizeHint is more stable
        top_h = self.top_panel.sizeHint().height() if self.top_panel.isVisible() else 0
        bottom_h = self.bottom_container.height() if self.bottom_container.isVisible() else 0
        
        available_h = total_h - top_h - bottom_h
        if available_h < 100:
            available_h = 100
        
        # Position exactly below top_panel
        self.alt_panel.setGeometry(0, top_h, self.alt_panel.width(), available_h)

        # Ensure top_panel and bottom_container are always on top of alt_panel 
        # to prevent it from covering our interactive controls.
        self.alt_panel.raise_()
        self.top_panel.raise_()
        self.bottom_container.raise_()

        
    def _on_panel_expand_toggled(self, panel, expanded: bool):
        if expanded:
            if panel == self.page_panel and self.chapter_panel.content_area.isVisible():
                 self.chapter_panel.hide_content()
            elif panel == self.chapter_panel and self.page_panel.content_area.isVisible():
                 self.page_panel.hide_content()
            
            panel.show_content()
            self._update_expanded_panel_height(panel)
        else:
            panel.setMinimumHeight(0)
            panel.setMaximumHeight(16777215)
            panel.updateGeometry()
        
        QTimer.singleShot(100, self._update_alt_panel_height)

    def _update_expanded_panel_height(self, panel):
        total_h = self.height()
        top_h = self.top_panel.height()
        slider_h = self.slider_panel.height() if self.slider_panel.isVisible() else 0
        
        padding = 20
        
        available_h = total_h - top_h - slider_h - padding
        if available_h < 100: available_h = 100
        
        panel.setFixedHeight(available_h)

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
            self.slider_panel.set_chapter(self.model.chapter_index + 1, len(self.model.chapters))
        self._update_slider_state()

        self.page_panel._update_page_selection(self.model.current_index)

        self.model.update_layout()

        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer.refresh()

        self._update_top_panel_title()

    def on_layout_updated(self):
        self.page_panel.model = self.model
        self.page_panel._update_page_thumbnails(self.model)
        self.page_panel._update_page_selection(self.model.current_index)
        
        self._update_slider_state()

        # Switch Viewer
        if self.model.view_mode == ViewMode.STRIP:
             new_viewer = self.strip_viewer
        else:
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
            if hasattr(self.view, '_update_overlay_bounds'):
                self.view._update_overlay_bounds()
            
        self.layout_btn.setText("")
        if self.model.view_mode == ViewMode.SINGLE:
            self.layout_btn.setIcon(self.layout_single_icon)
            self.layout_btn.setToolTip("Single Page")
        elif self.model.view_mode == ViewMode.DOUBLE:
            self.layout_btn.setIcon(self.layout_double_icon)
            self.layout_btn.setToolTip("Double Page")
        else:
            self.layout_btn.setIcon(self.layout_strip_icon)
            self.layout_btn.setToolTip("Long Strip")

        # Reload content
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer.load(None)
            if self.model.images and self.model.current_index < len(self.model.images):
                self._update_image_info([self.model.images[self.model.current_index].path])
        else:
             if self.model.images and self.model.current_index < len(self.model.images):
                  self.model.load_image()

    def on_page_updated(self, page_index: int):
        self.page_panel.refresh_thumbnail(page_index)
        
        self._update_slider_state()
        
        # If the updated page is the current one (or visible in double view), reload the viewer
        should_reload = False
        if self.model.view_mode == ViewMode.SINGLE:
            if self.model.current_index == page_index:
                should_reload = True
        elif self.model.view_mode == ViewMode.DOUBLE:
             # Check if page_index is currently visible
             if abs(page_index - self.model.current_index) <= 1:
                 should_reload = True
        elif self.model.view_mode == ViewMode.STRIP:
            should_reload = True

        if should_reload:
            self.model.load_image()
            if self.model.view_mode == ViewMode.STRIP:
                self.strip_viewer.refresh(page_index)
        
        self.update_top_panel()
                 
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
            # Re-trigger alt panel visibility check
            if self.alt_panel:
                self.alt_panel._update_panel(self.model.current_index)
                QTimer.singleShot(100, self._update_alt_panel_height)
        else:
            self.top_panel.hide()
            self.slider_panel.hide()
            if self.alt_panel:
                self.alt_panel.hide()

            if self.page_panel.content_area.isVisible():
                self.page_panel.hide_content()

            if self.chapter_panel.content_area.isVisible():
                self.chapter_panel.hide_content()

    def eventFilter(self, obj, event):
        if self.current_viewer:
            if self.current_viewer == self.strip_viewer:
                if obj is self.scroll_area.viewport() or obj is self.scroll_area:
                    if self.strip_viewer.handle_event(event):
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # Check if at least one URL is a local file with a valid extension
            valid_exts = tuple(list(IMAGE_EXTS) + list(VIDEO_EXTS))
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isfile(path) and path.lower().endswith(valid_exts):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
            self._add_alts_from_files(file_paths)
            event.acceptProposedAction()
        super().dropEvent(event)

    def _paste_as_alternate_action(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if mime_data.hasUrls():
            file_paths = [url.toLocalFile() for url in mime_data.urls()]
            self._add_alts_from_files(file_paths)

    def _add_alts_from_files(self, file_paths: List[str]):
        if not file_paths: return
        
        # Target the current page
        target_idx = self.model.current_index
        if target_idx == -1: return

        from src.ui.components.drag_drop_alt_dialog import DragDropAltDialog
        
        page_obj = self.model.images[target_idx]
        existing_cats = list(page_obj.get_categorized_variants().keys())

        dialog = DragDropAltDialog(self, existing_categories=existing_cats)
        # Pre-load the files into the dialog
        if dialog.add_files(file_paths) > 0:
            if dialog.exec():
                files = dialog.get_files()
                cat = dialog.get_category()
                if files:
                    import src.ui.page_utils as page_utils
                    page_utils.process_add_alts(
                        self.model,
                        files,
                        target_idx,
                        lambda: self.reload_chapter(),
                        lambda idx: self.model.update_page_variants(idx),
                        category=cat if cat else None
                    )

    def resolve_path(self, path: str) -> str:
        """Resolves a virtual archive path to a real local file path if it exists in cache."""
        if not path or '|' not in path:
            return path
            
        archive_path, internal = path.split('|', 1)
        ext = os.path.splitext(archive_path)[1].lower()
        
        if ext in {'.7z', '.rar', '.cbr', '.cb7', '.zip', '.cbz'}:
            from src.utils.archive_utils import SevenZipHandler
            extract_dir = SevenZipHandler.get_extract_dir(archive_path)
            target = extract_dir / internal.replace('/', os.sep).replace('\\', os.sep)
            
            if target.exists():
                return str(target)
            
            SevenZipHandler.read_file(archive_path, internal)
            if target.exists():
                return str(target)
                
        return path

    def _load_image(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        is_video = ext in VIDEO_EXTS
        resolved_path = self.resolve_path(path)
        
        target_viewer = self.video_viewer if is_video else self.image_viewer
        
        if self.model.view_mode != ViewMode.STRIP:
             if self.current_viewer != target_viewer:
                 self.current_viewer.set_active(False)
                 self.current_viewer = target_viewer
                 self.current_viewer.set_active(True)
                 if hasattr(self.view, '_update_overlay_bounds'):
                     self.view._update_overlay_bounds()
        
        if self.current_viewer == self.strip_viewer:
             # Refresh current index just in case, though on_page_updated handles specific updates
             self.strip_viewer.refresh(self.model.current_index)
        else:
             self.current_viewer.load(resolved_path)

        self.page_panel._update_page_selection(self.model.current_index)
        
        if self.model.view_mode == ViewMode.DOUBLE:
             self.slider_panel.set_value(self.model._get_current_layout_index())
        else:
             self.slider_panel.set_value(self.model.current_index)
             
        self.update_top_panel()
        self._update_image_info([resolved_path])

    def _load_double_images(self, image1_path, image2_path):
        if self.current_viewer != self.image_viewer:
             self.current_viewer.set_active(False)
             self.current_viewer = self.image_viewer
             self.current_viewer.set_active(True)
             
        self.image_viewer.load((image1_path, image2_path))
        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model._get_current_layout_index())
        
        paths = []
        if image1_path and image1_path != "placeholder":
            paths.append(self.resolve_path(image1_path))
        if image2_path and image2_path != "placeholder":
            paths.append(self.resolve_path(image2_path))
        self._update_image_info(paths)

    def _update_image_info(self, paths: List[str]):
        if not paths:
            self.slider_panel.set_info_text("")
            return

        items = []
        for path in paths:
            if not path or path == "placeholder":
                continue
                
            resolved = self.resolve_path(path)
            # If it's a virtual path (e.g. zip|image.jpg), show only the image filename
            display_path = path.split('|')[-1] if '|' in path else path
            name = os.path.basename(display_path)
            items.append((name, resolved))

        if not items:
            self.slider_panel.set_info_text("")
            return

        worker = ImageInfoWorker(items)
        worker.signals.finished.connect(self.slider_panel.set_info_text)
        self.thread_pool.start(worker)

    def set_zoom_mode(self, mode: str):
        self.last_zoom_mode = mode
        self.current_viewer.zoom(mode)

    def save_area(self, scene_rect: QRectF, size_limit_mb=None):
        if self.current_viewer:
            self.current_viewer.save_area(scene_rect, size_limit_mb=size_limit_mb)

    def start_area_selection(self):
        """Triggers the area selection UI on the current view."""
        if hasattr(self.view, 'start_area_selection'):
            self.view.start_area_selection()

    def _on_area_selection_started(self):
        self._toggle_panels(visible=False)
        self.selection_panel.reset()
        self.selection_panel.show()

    def _apply_area_selection(self):
        rect = self.view.get_selection_rect()
        if rect:
            size_limit = self.selection_panel.get_size_limit()
            self.save_area(rect, size_limit_mb=size_limit)
            self._cancel_area_selection()
        else:
            QMessageBox.information(self, "No Selection", "Please select an area first.")

    def _cancel_area_selection(self):
        self.view.clear_selection()
        self.selection_panel.hide()
        self._toggle_panels(visible=True)

    def reset_zoom(self):
        self.set_zoom_mode("Fit Page")

    def apply_last_zoom(self):
        self.set_zoom_mode(self.last_zoom_mode)

    def cycle_current_variant(self):
        # Cycles the "main" page variant
        if self.model.view_mode == ViewMode.SINGLE:
            self.model.cycle_variant(self.model.current_index)
        elif self.model.view_mode == ViewMode.DOUBLE:
             # Cycle both current and next page if valid (since double view shows 2 pages)
             # Ensure we start at the beginning of the pair (even index)
             current_idx = self.model.current_index
             if current_idx % 2 != 0:
                 current_idx -= 1
                 
             self.model.cycle_variant(current_idx)
             if current_idx + 1 < len(self.model.images):
                 self.model.cycle_variant(current_idx + 1)
        elif self.model.view_mode == ViewMode.STRIP:
             idx = self.model.current_index
             self.model.cycle_variant(idx)

    def _on_view_zoom_started(self):
        if self.current_viewer == self.image_viewer:
            self.image_viewer._restore_original_pixmap()

    def show_next(self):
        if not self.model.images:
            return
        if self.model.view_mode == ViewMode.STRIP:
            self._change_chapter(1)
            return
            
        if self.model.navigate(1):
            return
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

        if self.model.navigate(-1):
            return
        else:
            self._change_chapter(-1)

    def _update_slider_state(self):
        if not self.slider_panel or not self.model.images:
            self.slider_panel.set_range(0)
            self.slider_panel.set_value(0)
            return

        if self.model.view_mode == ViewMode.DOUBLE:
            max_val = max(0, len(self.model._layout_pairs) - 1)
            current_val = self.model._get_current_layout_index()
            
            self.slider_panel.set_range(max_val)
            self.slider_panel.set_value(current_val)
            
            # Map alt indices
            alt_indices = []
            for i, pair in enumerate(self.model._layout_pairs):
                has_alt = False
                for p in pair:
                    if p and hasattr(p, 'images') and len(p.images) > 1:
                        has_alt = True
                        break
                if has_alt:
                    alt_indices.append(i)
            self.slider_panel.set_alt_indices(alt_indices)

        else:
            max_val = len(self.model.images) - 1
            current_val = self.model.current_index
            
            self.slider_panel.set_range(max_val)
            self.slider_panel.set_value(current_val)
            
            # Map alt indices
            alt_indices = []
            for i, page in enumerate(self.model.images):
                if page and len(page.images) > 1:
                    alt_indices.append(i)
            self.slider_panel.set_alt_indices(alt_indices)

    def _slider_val_to_page(self, val_0b: int) -> int:
        """Convert 0-based Slider/Layout index to 1-based Page index."""
        if self.model.view_mode == ViewMode.DOUBLE:
             # val_0b is Layout Index
             if 0 <= val_0b < len(self.model._layout_pairs):
                  pair = self.model._layout_pairs[val_0b]
                  # Find first valid page in pair to navigate to
                  target = pair[0]
                  if not (target and hasattr(target, 'path')):
                      target = pair[1]
                  
                  if target and hasattr(target, 'path'):
                      return self.model.get_page_index(target.path) + 1
             return 1 # Fallback
        else:
             # val_0b is Page Index
             return val_0b + 1

    def change_page(self, page: int):
        # page is ALWAYS 1-based raw page index
        if self.model.view_mode == ViewMode.STRIP:
            self.strip_viewer._scroll_to_page(page - 1)
            self.page_panel._update_page_selection(page - 1)
            self.slider_panel.set_value(page - 1)
            self._update_image_info([self.model.images[page - 1].path])
            return

        self.model.change_page(page)

    def change_page_from_slider(self, val: int):
        # val is 0-based index from Slider (Page Index or Layout Index)
        target_page = self._slider_val_to_page(val)
        self.change_page(target_page)

    def change_page_from_input(self, val: int):
        # val is 1-based index from Input (Page Number or Layout Number)
        target_page = self._slider_val_to_page(val - 1)
        self.change_page(target_page)

    def _show_page_panel(self):
        if self.chapter_panel.content_area.isVisible():
            self.chapter_panel.hide_content()
        self.page_panel.show_content()
        QTimer.singleShot(100, self._update_alt_panel_height)

    def _show_chapter_panel(self):
        if self.page_panel.content_area.isVisible():
            self.page_panel.hide_content()
        self.chapter_panel.show_content()
        QTimer.singleShot(100, self._update_alt_panel_height)

    def set_chapter(self, chapter:int):
        if self.model.set_chapter(chapter):
            self._load_chapter_async(start_from_end=False)
            self.chapter_panel._update_chapter_selection(self.model.chapter_index)
            self.current_chapter_changed.emit(self.model.series, self.model.chapters[self.model.chapter_index])

    def reload_chapter(self):
        self._load_chapter_async(start_from_end=False)

    def _change_chapter(self, direction: int):
        start_from_end = direction == -1
        if self.model.change_chapter(direction):
            self._load_chapter_async(start_from_end=start_from_end)
            self.chapter_panel._update_chapter_selection(self.model.chapter_index)
            self.current_chapter_changed.emit(self.model.series, self.model.chapters[self.model.chapter_index])

    def _load_chapter_async(self, start_from_end: bool):
        self.page_panel.stop_loading_thumbnails()
        self.loading_label.show()
        # Clean current view
        if self.current_viewer:
             self.current_viewer.cleanup()
             
        self.image_viewer.reset()
        self.video_viewer.reset()
        
        self.scene.clear()
        
        worker = ChapterLoaderWorker(
            manga_dir=self.model.manga_dir,
            series_path=str(self.model.series['path']),
            start_from_end=start_from_end,
            load_pixmap_func=self.image_viewer._load_pixmap
        )
        worker.signals.finished.connect(self._on_chapter_loaded)
        self.thread_pool.start(worker)

        if self.model.manga_dir:
            path_str = str(self.model.manga_dir)
            if path_str.lower().endswith(('.7z', '.rar', '.cbr', '.cb7', '.zip', '.cbz')):
                extract_worker = ArchiveExtractionWorker(path_str)
                self.thread_pool.start(extract_worker)
            elif '|' in path_str:
                zip_path, _ = path_str.split('|', 1)
                if zip_path.lower().endswith(('.7z', '.rar', '.cbr', '.cb7', '.zip', '.cbz')):
                    extract_worker = ArchiveExtractionWorker(zip_path)
                    self.thread_pool.start(extract_worker)

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

    def toggle_playback(self):
        if self.current_viewer == self.video_viewer:
            self.video_viewer._toggle_play_pause()

    def _on_lang_changed(self, text: str):
        if not self.model.images:
             return
             
        if text == "Original":
            self.model.set_preferred_language(None)
        else:
            try:
                lang = Language(text).value
                self.model.set_preferred_language(lang)
            except ValueError:
                self.model.set_preferred_language(None)
                
        # self.model.load_image() handled by set_preferred_language
        self.update_top_panel()

    def update_top_panel(self, _=None):
        """Update top panel translate button state based on current page."""
        if not hasattr(self, 'top_panel') or not self.model.images:
            return
            
        if not (0 <= self.model.current_index < len(self.model.images)):
            self.top_panel.update_translate_button('TRANSLATE')
            return

        # Check if reading from archive - disable translation
        if str(self.model.series['path']).lower().endswith(('.zip', '.cbz')) or \
           str(self.model.manga_dir).lower().endswith(('.zip', '.cbz')):
            self.top_panel.update_translate_button('DISABLED')
            return

        page = self.model.images[self.model.current_index]
        combo_text = self.top_panel.lang_combo.currentText()
        
        if combo_text == "Original":
             # Cannot translate Original to Original
             # Cannot translate Original to Original
             self.top_panel.update_translate_button('DISABLED')
             return

        target_lang = Language(combo_text).value
        
        # Check global status first
        page_source_path = ""
        if 0 <= page.current_variant_index < len(page.images):
            page_source_path = page.images[page.current_variant_index]
        elif page.images:
            page_source_path = page.images[0]
            
        status = TranslationService.instance().get_status(page_source_path, target_lang)
        
        if status:
            self.top_panel.update_translate_button(status.upper())
        elif target_lang in page.translations:
             # Translation exists -> Offer Redo
             self.top_panel.update_translate_button('REDO')
        else:
             # Translation missing -> Offer Translate
             self.top_panel.update_translate_button('TRANSLATE')

    def translate_page(self, arg=None):
        if not self.model.images or self.model.current_index >= len(self.model.images):
            return

        # Fetch target language from combo
        if not hasattr(self, 'top_panel'):
            return
            
        combo_text = self.top_panel.lang_combo.currentText()
        if combo_text == "Original":
            return # Cannot translate

        target_lang_enum = Language(combo_text)
        target_lang = target_lang_enum.value
        page = self.model.images[self.model.current_index]
        
        # Always translate from source (Redo or First Time)
        # Use explicit source variant path
        if 0 <= page.current_variant_index < len(page.images):
            path = page.images[page.current_variant_index]
        else:
            path = page.images[0]
           
        series_path = str(self.model.series['path'])
        chapter_name = Path(self.model.manga_dir).name
        
        worker = TranslateWorker(path, series_path, chapter_name, target_lang=target_lang_enum)
        worker.signals.finished.connect(self._on_translation_finished)
        
        TranslationService.instance().submit(worker)
        self.update_top_panel() # Update immediately to show Queued status
        
    def _on_translation_finished(self, original_path: str, saved_path: str, overlays: list, lang_code: str, history: list):
        if not self.model.images:
             self.loading_label.hide()
             return

        # 1. Find the page object that this translation belongs to
        target_page = None
        for p in self.model.images:
            # Check if original_path is one of the variants
            if original_path in p.images:
                target_page = p
                break
            # Check if original_path was itself a translation (edge case)
            if original_path in p.translations.values():
                target_page = p
                break
        
        if not target_page:
            # If saved_path is None, it means the worker failed/aborted
            if saved_path is None:
                self.loading_label.hide()
                QMessageBox.critical(self, "Translation Failed", "The translation process failed. Please check the logs or your connection.")
                return

            print(f"Translation finished for {original_path}, but could not find corresponding page in model.")
            self.loading_label.hide()
            return

        current_page = self.model.images[self.model.current_index]

        # 2. Update the Page data
        if saved_path:
            target_page.translations[lang_code] = saved_path
        else:
             # Translation failed
             if target_page == current_page:
                  self.loading_label.hide()
                  QMessageBox.critical(self, "Translation Failed", "The translation process failed. Please check your connection.")
             return
            
        # 3. If this is the currently viewed page, update the UI        
        if target_page == current_page:
            self.loading_label.hide()
            self.loading_label.setText("Loading...") # Reset
            
            current_ui_lang = Language(self.top_panel.lang_combo.currentText()).value
            
            # Only switch view if the finished translation matches the currently selected UI language
            if lang_code == current_ui_lang:
                if saved_path:
                    # Switch to it
                    current_page.set_translation(lang_code)
                    self.model.load_image()
                    self.update_top_panel()
                elif overlays:
                    # Fallback
                    if self.current_viewer == self.image_viewer:
                        self.image_viewer.show_overlays(overlays)
            else:
                # User changed language while translating? 
                # Just update button state to show translation is available
                self.update_top_panel()

    def _update_top_panel_title(self):
        """Update top panel title with chapter information if different from series."""
        if not self.model.series or not hasattr(self, 'top_panel'):
            return
            
        series_name = self.model.series.get("name", "Unknown")
        series_path = Path(str(self.model.series.get("path", "")))
        
        current_chapter_path = Path(str(self.model.manga_dir)) if self.model.manga_dir else None
        
        if current_chapter_path and current_chapter_path != series_path:
            # Different chapter, show Series - Chapter
            chapter_name = current_chapter_path.name
            self.top_panel.set_series_title(f"{series_name} - {chapter_name}")
        else:
            # Same folder, just show Series
            self.top_panel.set_series_title(series_name)

