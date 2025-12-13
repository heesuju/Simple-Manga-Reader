import math
from typing import List, Union
import numpy as np
import cv2
import os
import shutil
from pathlib import Path
import zipfile
import io
from PIL import Image, ImageQt


from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QScrollArea, QSizePolicy, QPinchGesture, QStackedWidget, QGridLayout
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QColor, QMovie, QImage, QMouseEvent, QIcon
from PyQt6.QtCore import Qt, QTimer, QEvent, QThreadPool, QMargins, QPropertyAnimation, pyqtSignal, QSize, QUrl, QRectF, QSizeF
# NEW imports for multimedia
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

from src.enums import ViewMode
from src.ui.page_panel import PagePanel
from src.ui.chapter_panel import ChapterPanel
from src.ui.top_panel import TopPanel
from src.ui.slider_panel import SliderPanel
from src.ui.video_control_panel import VideoControlPanel
from src.ui.image_view import ImageView
# removed: VideoPlayerWidget
from src.utils.img_utils import get_image_data_from_zip, empty_placeholder
from src.data.reader_model import ReaderModel
from src.utils.database_utils import get_db_connection
from src.utils.img_utils import get_chapter_number
from src.workers.view_workers import ChapterLoaderWorker, PixmapLoader, WorkerSignals, AnimationFrameLoaderWorker, VideoFrameExtractorWorker, VIDEO_EXTS


class FitInViewAnimation(QPropertyAnimation):
    def __init__(self, target, parent=None):
        super().__init__(target, b"", parent)
        self.setTargetObject(target)

    def updateCurrentValue(self, value):
        self.targetObject().fitInView(value, Qt.AspectRatioMode.KeepAspectRatio)


class ReaderView(QWidget):
    back_pressed = pyqtSignal()
    zoom_changed = pyqtSignal(str)
    request_fullscreen_toggle = pyqtSignal()

    def __init__(self, series: object, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None):
        super().__init__()
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

        self.slider_panel = None

        self._last_total_scale = 1.0
        self._strip_zoom_factor = 1.0

        self.thread_pool = QThreadPool()

        self.original_view_mouse_press = None
        self.is_zoomed = False

        self.guided_reading_animation = None
        self.continuous_play = False
        self.page_slideshow_timer = QTimer(self)
        self.page_slideshow_timer.timeout.connect(self.show_next)

        self.strip_scroll_timer = QTimer(self)
        self.strip_scroll_timer.timeout.connect(self._scroll_strip)
        self.scroll_interval = 3
        self.scroll_speeds = [5, 10, 20, 40]
        self.current_scroll_speed_index = 0

        self.slideshow_speeds = [4000, 2000, 500] # ms
        self.current_slideshow_speed_index = 0
        self.slideshow_repeat = False

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._show_next_frame)
        self.animation_frames = []
        self.current_frame_index = 0

        self.user_interrupted_animation = False
        self.is_dragging_animation = False
        self.last_pan_pos = None

        self.panels_visible = True
        self.mouse_press_pos = None

        self.is_panning = False
        self.last_pan_pos = None

        self.last_zoom_mode = "Fit Page"

        # Multimedia objects (Option C)
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.video_item: QGraphicsVideoItem | None = None  # will be created and added to scene when needed

        self.playback_speeds = [1.0, 1.25, 1.5, 1.75, 2.0, 0.5, 0.75]
        self.current_speed_index = 0
        self.video_repeat = False
        self.auto_play = False # Auto Play Next Video

        self._setup_ui()
        self._load_chapter_async(start_from_end=self.model.start_file is None and len(self.model.images) == 0)

    def _setup_ui(self):
        self.loading_label = QLabel("Loading...", self)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; font-size: 24px;")
        self.loading_label.hide()

        self.back_icon = QIcon("assets/icons/back.png")

        # Scene/view (we will render both pixmaps and video inside the same scene)
        self.scene = QGraphicsScene()
        self.view = ImageView(manga_reader=self)
        self.view.viewport().setMouseTracking(True)
        self.view.setScene(self.scene)
        self.view.viewport().installEventFilter(self)

        # NOTE: We removed the separate VideoPlayerWidget and will use a QGraphicsVideoItem in the scene.
        # Keep compatibility with your code that used a stacked widget by adding only the view.
        self.media_stack = QStackedWidget()
        self.media_stack.addWidget(self.view)
        # video widget is no longer a separate widget, so we do NOT add one here

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
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_images)
        self.scroll_area.viewport().installEventFilter(self)
        main_layout.addWidget(self.scroll_area, 0, 0)
        self.scroll_area.hide()

        # 1. Create all panel widgets first, with self as parent
        self.top_panel = TopPanel(self)
        self.page_panel = PagePanel(self, model=self.model, on_page_changed=self.change_page)
        self.video_control_panel = VideoControlPanel(self)
        self.video_control_panel.raise_()
        self.slider_panel = SliderPanel(self)
        self.chapter_panel = ChapterPanel(self, model=self.model, on_chapter_changed=self.set_chapter)

        # Add panels to the layout, stacked on top
        main_layout.addWidget(self.top_panel, 0, 0, Qt.AlignmentFlag.AlignTop)
        
        # Create a container for the bottom panels
        bottom_container = QWidget(self)
        bottom_layout = QVBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        bottom_container.setLayout(bottom_layout)

        bottom_layout.addWidget(self.page_panel)
        bottom_layout.addWidget(self.chapter_panel)
        # bottom_layout.addWidget(self.video_control_panel) # Removed from layout
        bottom_layout.addWidget(self.slider_panel)

        main_layout.addWidget(bottom_container, 0, 0, Qt.AlignmentFlag.AlignBottom)

        self.chapter_panel._update_chapter_thumbnails(self.model.chapters) # Load chapter thumbnails once

        # 2. Add control widgets to the panels
        self.top_panel.set_series_title(self.model.series.get("name"))
        self.top_panel.add_back_button(self.back_btn)
        self.top_panel.add_layout_button(self.layout_btn)

        # 3. Connect signals from all panels
        self.video_control_panel.play_pause_clicked.connect(self._toggle_play_pause)
        self.video_control_panel.volume_changed.connect(self._set_volume)
        self.video_control_panel.position_changed.connect(self._set_video_position)
        self.video_control_panel.speed_clicked.connect(self._change_playback_speed)
        self.video_control_panel.repeat_clicked.connect(self._set_video_repeat)
        self.video_control_panel.auto_play_toggled.connect(self._set_auto_play)
        self.video_control_panel.hide()

        self.slider_panel.valueChanged.connect(self.change_page_from_slider)
        self.slider_panel.slideshow_button_clicked.connect(self.start_page_slideshow)
        self.slider_panel.speed_changed.connect(self._on_slideshow_speed_changed)
        self.slider_panel.repeat_changed.connect(self._on_slideshow_repeat_changed)
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
        # removed: video_widget mouse event override (video is inside QGraphicsScene now)

        # Connect media player signals if you want to monitor playback state etc.
        # For example stop video when finished:
        self.media_player.playbackStateChanged.connect(self._on_media_playback_state_changed)
        self.media_player.durationChanged.connect(self.video_control_panel.set_duration)
        self.media_player.positionChanged.connect(self.video_control_panel.set_position)
        self.media_player.positionChanged.connect(self._check_underlay_visibility)


    # ---------- Multimedia helper methods (Option C) ----------
    def _ensure_video_item(self):
        """Create the QGraphicsVideoItem once and keep it in the scene (hidden until used)."""
        if self.video_item is None:
            # Create the last frame item which sits behind the video
            self.video_last_frame_item = QGraphicsPixmapItem()
            self.video_last_frame_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.video_last_frame_item.setZValue(-1) # Behind video
            self.scene.addItem(self.video_last_frame_item)
            
            self.video_item = QGraphicsVideoItem()
            # Start invisible
            self.video_item.setVisible(False)
            # Add to scene at z-value 0 (images will be z 0 too); pixmap_item will be managed separately.
            self.scene.addItem(self.video_item)

    def _update_video_underlay_geometry(self):
        """Scale and center the last frame underlay to match the video item behavior."""
        if not (hasattr(self, 'video_last_frame_item') and 
                self.video_last_frame_item and 
                self.video_last_frame_item.isVisible() and
                hasattr(self, 'last_frame_pixmap') and 
                self.last_frame_pixmap):
            return

        vp = self.view.viewport().size()
        
        # Scale pixmap to fit viewport maintaining aspect ratio
        scaled_pixmap = self.last_frame_pixmap.scaled(
            vp.width(), vp.height(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.video_last_frame_item.setPixmap(scaled_pixmap)
        
        # Center the item
        x = (vp.width() - scaled_pixmap.width()) / 2
        y = (vp.height() - scaled_pixmap.height()) / 2
        self.video_last_frame_item.setPos(x, y)

    def _play_video(self, path: str):
        """Play a local file path in the scene via QGraphicsVideoItem."""
        self._ensure_video_item()
        # Stop any previous media
        try:
            self.media_player.stop()
        except Exception:
            pass

        # --- EXTRACT LAST FRAME LOGIC (ASYNC) ---
        worker = VideoFrameExtractorWorker(path)
        worker.signals.finished.connect(self._on_last_frame_extracted)
        self.thread_pool.start(worker)
        # ----------------------------------------
        
        # Delay visibility until video starts to avoid showing end frame at start
        # This will be handled by _check_underlay_visibility via positionChanged
        if hasattr(self, 'video_last_frame_item') and self.video_last_frame_item:
            self.video_last_frame_item.setVisible(False)
        self.last_frame_pixmap = None # Clear until loaded
    


        self.media_player.setVideoOutput(self.video_item)
        self.media_player.setSource(QUrl.fromLocalFile(path))
        # Make video item visible and sized to the view/scene
        self.video_item.setVisible(True)
        # Hide pixmap item if present
        if hasattr(self, "pixmap_item") and self.pixmap_item:
            self.pixmap_item.setVisible(False)

        # set size to match viewport (we'll update size on resizeEvent / fit)
        vp = self.view.viewport().size()
        self.video_item.setSize(QSizeF(vp.width(), vp.height()))
        # Position at origin of scene
        self.video_item.setPos(0, 0)
        
        # Update underlay geometry
        self._update_video_underlay_geometry()
        
        self.scene.setSceneRect(QRectF(0, 0, vp.width(), vp.height()))
        self.media_player.play()
        self._reposition_video_control_panel()

    def _on_last_frame_extracted(self, path, q_image):
        # Verify if we are still playing the same video
        current_source = self.media_player.source().toLocalFile()
        
        # Normalize paths for comparison (handle case and separators)
        path_norm = os.path.normcase(os.path.normpath(path))
        current_norm = os.path.normcase(os.path.normpath(current_source))
        if path_norm != current_norm:
             return

        pixmap = QPixmap.fromImage(q_image)
        self.last_frame_pixmap = pixmap
        # NOTE: We do NOT make it visible here. We wait for _check_underlay_visibility 
        # (connected to positionChanged) to show it once playback has started.

    def _check_underlay_visibility(self, position):
        """Show the underlay only after video has started playing to avoid glitches."""
        # Check if we have a valid underlay to show
        if (hasattr(self, 'video_last_frame_item') and 
            self.video_last_frame_item and 
            hasattr(self, 'last_frame_pixmap') and 
            self.last_frame_pixmap):
            
            # If currently hidden and we are playing (position > 100ms), show it.
            # 100ms is a heuristic to ensure first frame of video is likely rendered.
            if not self.video_last_frame_item.isVisible() and position > 100:
                self.video_last_frame_item.setVisible(True)
                # Ensure geometry is correct
                self._update_video_underlay_geometry()

    def _stop_video(self):
        """Stop playback, hide the video item, and completely detach audio/source."""
        self.video_control_panel.hide()
        if self.panels_visible:
            self.slider_panel.show()
        # Stop playback
        if self.media_player:
            try:
                self.media_player.stop()
            except Exception:
                pass

            # Clear source to ensure backend releases the file/stream
            try:
                # Setting an empty QUrl clears the current source
                self.media_player.setSource(QUrl())
            except Exception:
                # older/newer Qt versions differ; ignore if not supported
                pass

            # Detach the video output (so it's not holding references)
            try:
                self.media_player.setVideoOutput(None)
            except Exception:
                pass

            # Detach audio output as well
            try:
                # stop audio output explicitly
                if self.audio_output:
                    self.audio_output.stop()
                # detach audio output from media_player
                self.media_player.setAudioOutput(None)
            except Exception:
                pass

        # Hide or remove the video item in the scene
        if self.video_item:
            try:
                self.video_item.setVisible(False)
                # Also hide the last frame underlay
                if hasattr(self, 'video_last_frame_item'):
                    self.video_last_frame_item.setVisible(False)
            except Exception:
                pass

        # Restore pixmap visibility if present
        if hasattr(self, "pixmap_item") and self.pixmap_item:
            try:
                self.pixmap_item.setVisible(True)
            except Exception:
                pass

    # ... (rest of file) ...
    # Skip unchanged methods until resizeEvent

    # override resizeEvent to keep video item sized to viewport and keep overlay panels visible
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Update video item size & scene rect so it fits the view
        if self.video_item and self.video_item.isVisible():
            vp = self.view.viewport().size()
            self.video_item.setSize(QSizeF(vp.width(), vp.height()))
            self.video_item.setPos(0, 0)
            
            # Updating last frame item size to match
            self._update_video_underlay_geometry()
            
            self.scene.setSceneRect(QRectF(0, 0, vp.width(), vp.height()))
        
        self._reposition_video_control_panel()
        
        # if pixmap present, keep fit behavior (call fit on next tick)
        QTimer.singleShot(0, self.apply_last_zoom)

    def _on_media_playback_state_changed(self, state):
        self.video_control_panel.set_playing(state == QMediaPlayer.PlaybackState.PlayingState)
        if state == QMediaPlayer.PlaybackState.StoppedState:
            if self.video_repeat:
                self.media_player.play()
            elif self.auto_play:
                # Search for the next video file in the list
                start_index = self.model.current_index + 1
                found_index = -1
                for i in range(start_index, len(self.model.images)):
                    next_file = self.model.images[i]
                    ext = os.path.splitext(next_file)[1].lower()
                    if ext in VIDEO_EXTS:
                        found_index = i
                        break
                
                if found_index != -1:
                    # Found a video! Jump to it.
                    # change_page expects 1-based index
                    self.change_page(found_index + 1)

    def _toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _set_volume(self, volume):
        self.audio_output.setVolume(volume / 100.0)

    def _set_video_position(self, position):
        self.media_player.setPosition(position)

    def _change_playback_speed(self):
        self.current_speed_index = (self.current_speed_index + 1) % len(self.playback_speeds)
        speed = self.playback_speeds[self.current_speed_index]
        self.media_player.setPlaybackRate(speed)
        self.video_control_panel.set_speed_text(f"{speed}x")

    def _set_video_repeat(self, repeat):
        self.video_repeat = repeat

    def _set_auto_play(self, enabled):
        self.auto_play = enabled

    # ---------- End multimedia helpers ----------

    def _show_next_frame(self):
        if not self.animation_frames:
            return


        self.current_frame_index = (self.current_frame_index + 1) % len(self.animation_frames)
        self._set_pixmap(self.animation_frames[self.current_frame_index])
        self.apply_last_zoom()

    def _on_animation_loaded(self, result: dict):
        self.loading_label.hide()
        frames = result["frames"]
        duration = result["duration"]
        path = result["path"]
        if path != self.model.images[self.model.current_index]:
            return  # Ignore if not the current image

        if frames:
            self.animation_frames = frames
            # The first frame is already displayed, so we start the timer
            # to show the next one.
            self.animation_timer.start(duration)

    def _on_slideshow_speed_changed(self):
        if self.model.view_mode == ViewMode.STRIP:
            self.current_scroll_speed_index = (self.current_scroll_speed_index + 1) % len(self.scroll_speeds)
            speed_text = f"{int(self.scroll_speeds[self.current_scroll_speed_index]/5)}x"
            self.slider_panel.speed_button.setText(speed_text)
            if self.strip_scroll_timer.isActive():
                self.strip_scroll_timer.start(self.scroll_interval)
            return

        self.current_slideshow_speed_index = (self.current_slideshow_speed_index + 1) % len(self.slideshow_speeds)
        current_speed_s = 4000 / self.slideshow_speeds[self.current_slideshow_speed_index]
        if current_speed_s < 1.0 and current_speed_s % 1 != 0:
            self.slider_panel.speed_button.setText(f"{round(current_speed_s, 1)}x".replace("0", ""))
        else:
            self.slider_panel.speed_button.setText(f"{int(current_speed_s)}x")

        if self.page_slideshow_timer.isActive():
            self.page_slideshow_timer.start(self.slideshow_speeds[self.current_slideshow_speed_index])

    def _on_slideshow_repeat_changed(self, is_checked: bool):
        self.slideshow_repeat = is_checked

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

    def _scroll_strip(self):
        if not self.scroll_area:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        new_value = scrollbar.value() + self.scroll_speeds[self.current_scroll_speed_index]

        if new_value >= scrollbar.maximum():
            if self.slideshow_repeat:
                scrollbar.setValue(0)
            else:
                self.stop_page_slideshow()
        else:
            scrollbar.setValue(new_value)

    def start_page_slideshow(self):
        if self.model.view_mode == ViewMode.STRIP:
            if self.strip_scroll_timer.isActive():
                self.stop_page_slideshow()
            else:
                self.strip_scroll_timer.start(self.scroll_interval)
                self.slider_panel.set_slideshow_state(True)
            return

        if self.page_slideshow_timer.isActive():
            self.stop_page_slideshow()
        else:
            self.page_slideshow_timer.start(self.slideshow_speeds[self.current_slideshow_speed_index])
            self.slider_panel.set_slideshow_state(True)

    def stop_page_slideshow(self):
        self.page_slideshow_timer.stop()
        self.strip_scroll_timer.stop()
        self.slider_panel.set_slideshow_state(False)

    def on_model_refreshed(self):
        if not self.model.images:
            QMessageBox.information(self, "No images", f"No images found in: {self.model.manga_dir}")

        self.page_panel._update_page_thumbnails(self.model)
        self.chapter_panel._update_chapter_selection(self.model.chapter_index)

        if self.model.images:
            self.slider_panel.set_range(len(self.model.images) - 1)
            self.slider_panel.set_value(self.model.current_index)
        else:
            self.slider_panel.set_range(0)
            self.slider_panel.set_value(0)

        total_chapters = len(self.model.chapters)
        current_chapter = self.model.chapter_index + 1
        self.slider_panel.set_chapter(current_chapter, total_chapters)

        self.model.update_layout()

    def on_layout_updated(self, view_mode):
        # The number of thumbnails is the number of steps for the slider
        images = self.model.images
        if self.model.view_mode == ViewMode.DOUBLE:
            images = self.model._get_double_view_images()
        num_pages = len(images)

        if num_pages > 0:
            self.slider_panel.set_range(num_pages - 1)
            self.slider_panel.set_value(self.model.current_index)
        else:
            self.slider_panel.set_range(0)
            self.slider_panel.set_value(0)

        if view_mode == ViewMode.SINGLE:
            self.layout_btn.setText("Single")
            self._show_single_layout()
        elif view_mode == ViewMode.DOUBLE:
            self.layout_btn.setText("Double")
            self._show_double_layout()
        else:
            self.layout_btn.setText("Strip")
            self._show_vertical_layout()

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
        if obj is self.view.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                if self.guided_reading_animation and self.guided_reading_animation.state() == QPropertyAnimation.State.Running:
                    self.stop_guided_reading(user_interrupted=True)
            elif event.type() == QEvent.Type.MouseMove:
                if self.video_item and self.video_item.isVisible():
                    view_height = self.height()
                    y = event.position().y()

                    bottom_area_height = view_height * 0.3  # pixels

                    # Show when cursor is in the bottom area
                    if view_height - y < bottom_area_height:
                        if not self.video_control_panel.isVisible():
                            self.video_control_panel.show()
                            self._reposition_video_control_panel()
                    # Hide when cursor is outside the bottom area
                    else:
                        if self.video_control_panel.isVisible():
                            # don't hide if mouse is over the panel itself
                            if not self.video_control_panel.underMouse():
                                self.video_control_panel.hide()

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
                    self.reset_zoom()
                    return True

            elif event.type() == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    angle = event.angleDelta().y()
                    factor = 1.25 if angle > 0 else 0.8
                    self._strip_zoom_factor *= factor
                    self._resize_vertical_images()
                    zoom_str = f"{self._strip_zoom_factor*100:.0f}%"
                    self.last_zoom_mode = zoom_str
                    self.zoom_changed.emit(zoom_str)
                    return True # Consume the event to prevent scrolling
                self._toggle_panels(False)

            if event.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self._resize_vertical_images)

        return super().eventFilter(obj, event)

    def _load_pixmap(self, image_source: Union[str, bytes]) -> QPixmap:
        if image_source == "placeholder":
            return empty_placeholder()

        pixmap = QPixmap()

        path_str = ""
        crop = None

        if isinstance(image_source, str):
            path_str = image_source
            if path_str.endswith("_left"):
                path_str = path_str[:-5]
                crop = "left"
            elif path_str.endswith("_right"):
                path_str = path_str[:-6]
                crop = "right"

        if isinstance(image_source, bytes) or '|' in path_str:
            image_data = image_source if isinstance(image_source, bytes) else get_image_data_from_zip(path_str)
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
        # Stop any ongoing animations or video
        self.animation_timer.stop()
        self.animation_frames.clear()
        self.current_frame_index = 0
        # Stop any playing video (now using media player)
        self._stop_video()

        video_extensions = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
        is_video = os.path.splitext(path)[1].lower() in video_extensions

        if is_video:
            if self.model.view_mode != ViewMode.SINGLE:
                self.model.toggle_layout(ViewMode.SINGLE)
            self._play_video(path)
            self.layout_btn.hide()
        else:
            self._stop_video()
            self.layout_btn.show()

            self.media_stack.setCurrentWidget(self.view)
            # Handle animated images
            if path.lower().endswith((".gif", ".webp")):
                image_data = None
                if '|' in path:
                    image_data = get_image_data_from_zip(path)
                elif os.path.exists(path):
                    with open(path, 'rb') as f:
                        image_data = f.read()

                if image_data:
                    try:
                        img = Image.open(io.BytesIO(image_data))
                        # Display first frame synchronously
                        img.seek(0)
                        first_frame_pixmap = ImageQt.toqpixmap(img)
                        self._set_pixmap(first_frame_pixmap)

                        # If animated, start worker for the rest
                        if img.is_animated and img.n_frames > 1:
                            self.loading_label.show()
                            worker = AnimationFrameLoaderWorker(path, image_data)
                            worker.signals.finished.connect(self._on_animation_loaded)
                            self.thread_pool.start(worker)

                    except Exception:
                        # Fallback to static image loading on error
                        self.original_pixmap = self._load_pixmap(path)
                        self._set_pixmap(self.original_pixmap)

            else:
                # Fallback for non-animated types
                self.original_pixmap = self._load_pixmap(path)
                self._set_pixmap(self.original_pixmap)

        # Common UI updates for all image types
        self.view.reset_zoom_state()
        QTimer.singleShot(0, self.apply_last_zoom)
        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model.current_index)

    def _set_pixmap(self, pixmap: QPixmap):
        # Clear scene except keep video_item if exists
        if self.video_item:
            # keep the video_item in the scene but hide it
            self.video_item.setVisible(False)
            if hasattr(self, 'video_last_frame_item') and self.video_last_frame_item:
                self.video_last_frame_item.setVisible(False)

        # remove all previous pixmap items
        for item in self.scene.items():
            if isinstance(item, QGraphicsPixmapItem):
                # Don't remove the video last frame item if it exists
                if hasattr(self, 'video_last_frame_item') and item == self.video_last_frame_item:
                    continue
                self.scene.removeItem(item)

        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        # place pixmap at origin
        self.pixmap_item.setPos(0, 0)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        # make sure pixmap is visible (video_item will be hidden if any)
        if hasattr(self, "pixmap_item"):
            self.pixmap_item.setVisible(True)

    def _load_double_images(self, image1_path, image2_path):
        # stop any video
        self._stop_video()

        self.media_stack.setCurrentWidget(self.view)
        # remove previous pixmap(s)
        # clear scene but keep video item if present
        if self.video_item:
            self.video_item.setVisible(False)

        self.scene.clear()
        # Since we cleared the scene, the video items are removed.
        # We reset them to None so they are recreated next time _play_video is called.
        self.video_item = None
        self.video_last_frame_item = None

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
        # keep a reference to last pixmap item (pointing to item1)
        self.pixmap_item = item1

        self.view.reset_zoom_state()
        QTimer.singleShot(0, self.apply_last_zoom)
        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model.current_index)

    def _update_zoom(self, factor: float):
        """Zoom the view using GPU-accelerated transformation.""" 
        self.view.resetTransform()  # reset previous zoom
        self.view.scale(factor, factor)
        zoom_str = f"{factor*100:.0f}%"
        self.last_zoom_mode = zoom_str
        self.zoom_changed.emit(zoom_str)

    def set_zoom_mode(self, mode: str):
        self.last_zoom_mode = mode
        if self.model.view_mode == ViewMode.STRIP:
            if mode == "Fit Page" or mode == "Fit Width":
                self._strip_zoom_factor = 1.0
                self.zoom_changed.emit("Fit Width")
            else:
                try:
                    self._strip_zoom_factor = float(mode.replace('%', '')) / 100.0
                except ValueError:
                    return # Ignore
            self._resize_vertical_images()
            return

        # Handle video zoom
        if self.video_item and self.video_item.isVisible():
            if mode == "Fit Page":
                self.view.resetTransform()
                self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                self.view.reset_zoom_state()
                self.zoom_changed.emit("Fit Page")
            else:
                try:
                    # Handle percentages like "150%"
                    zoom_value = float(mode.replace('%', '')) / 100.0
                    self.view._zoom_factor = zoom_value
                    self._update_zoom(zoom_value)
                except ValueError:
                    pass # Ignore invalid text
            return

        if not hasattr(self, "pixmap_item") or not self.pixmap_item:
            return

        if mode == "Fit Page":
            self._fit_current_image()
            self.zoom_changed.emit("Fit Page")
        elif mode == "Fit Width":
            scene_rect = self.scene.sceneRect()
            if scene_rect.width() > 0:
                view_width = self.view.viewport().width()
                factor = view_width / scene_rect.width()
                self.view._zoom_factor = factor
                self._update_zoom(factor)
                self.zoom_changed.emit("Fit Width")
        else:
            try:
                # Handle percentages like "150%"
                zoom_value = float(mode.replace('%', '')) / 100.0
                self.view._zoom_factor = zoom_value
                self._update_zoom(zoom_value)
            except ValueError:
                pass # Ignore invalid text

    def reset_zoom(self):
        self.set_zoom_mode("Fit Page")

    def apply_last_zoom(self):
        self.set_zoom_mode(self.last_zoom_mode)

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
        self.zoom_changed.emit("Fit Page")

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
            # If slideshow is active and repeat is on, loop back to the start
            if self.page_slideshow_timer.isActive() and self.slideshow_repeat:
                self.model.current_index = 0
                self.model.load_image()
            else:
                self._change_chapter(1)

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
            self._change_chapter(-1)

    def change_page(self, page:int):
        if self.model.view_mode == ViewMode.STRIP:
            self._scroll_to_page(page - 1)
            self.page_panel._update_page_selection(page - 1)
            self.slider_panel.set_value(page - 1)
            return

        self.model.change_page(page)
        self.page_panel._update_page_selection(self.model.current_index)
        self.slider_panel.set_value(self.model.current_index)

    def change_page_from_slider(self, page_index: int):
        if self.model.view_mode == ViewMode.STRIP:
            self._scroll_to_page(page_index)
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

    def _change_chapter(self, direction: int):
        start_from_end = direction == -1
        if self.model.change_chapter(direction):
            self._load_chapter_async(start_from_end=start_from_end)
            self.chapter_panel._update_chapter_selection(self.model.chapter_index)

    def _load_chapter_async(self, start_from_end: bool):
        self.loading_label.show()
        self.scene.clear()
        # keep video_item if exists (recreate later)
        self.video_item = None
        worker = ChapterLoaderWorker(
            manga_dir=self.model.manga_dir,
            start_from_end=start_from_end,
            load_pixmap_func=self._load_pixmap
        )
        worker.signals.finished.connect(self._on_chapter_loaded)
        self.thread_pool.start(worker)

    def _on_chapter_loaded(self, result: dict):
        # Ensure this result is for the currently selected chapter
        if result["manga_dir"] != self.model.manga_dir:
            return

        self.loading_label.hide()

        self.model.images = result["images"]
        self.model.current_index = result["initial_index"]

        if result["initial_pixmap"]:
            self._set_pixmap(result["initial_pixmap"])
            self.view.reset_zoom_state()
            QTimer.singleShot(0, self.apply_last_zoom)
        else:
            self.scene.clear() # Clear if no image was loaded

        # Now that the model is updated, refresh all UI components
        self.model.refresh()
        self.model.layout_updated.emit(self.model.view_mode)

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
        self.request_fullscreen_toggle.emit()

    def exit_if_not_fullscreen(self):
        self.request_fullscreen_toggle.emit()

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

        self.media_stack.show()
        if self.scroll_area:
            self.scroll_area.hide()

    def _show_vertical_layout(self):
        self.page_panel.hide()
        self.media_stack.hide()
        self.scroll_area.show()
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
            lbl.setContentsMargins(0,0,0,0)
            lbl.setStyleSheet("border: 0px; padding: 0px; margin: 0px;")
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
            self.slider_panel.set_value(self.model.current_index)

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
            self.scroll_area.hide()
        self.media_stack.show()

    def _change_page_by_strip_thumbnail(self, index: int):
        self._scroll_to_page(index)

    def _scroll_to_page(self, index: int):
        if self.scroll_area and 0 <= index < len(self.page_labels):
            label = self.page_labels[index]
            self.scroll_area.verticalScrollBar().setValue(label.y())

    def back_to_grid(self):
        # ensure media fully stopped before navigating away
        try:
            self._stop_video()
        except Exception:
            pass
        # emit after stopping to avoid race conditions
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

    def _on_translation_ready(self, modified_image):
        # Convert cv2 image (BGR) to QImage (RGB)
        height, width, channel = modified_image.shape
        bytes_per_line = 3 * width
        q_image = QImage(modified_image.data, width, height, bytes_per_line, QImage.Format.Format_BGR888)

        # Convert QImage to QPixmap
        pixmap = QPixmap.fromImage(q_image)

        # Update the scene
        self._set_pixmap(pixmap)

    # override resizeEvent to keep video item sized to viewport and keep overlay panels visible
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Update video item size & scene rect so it fits the view
        if self.video_item and self.video_item.isVisible():
            vp = self.view.viewport().size()
            self.video_item.setSize(QSizeF(vp.width(), vp.height()))
            self.video_item.setPos(0, 0)
            self.scene.setSceneRect(QRectF(0, 0, vp.width(), vp.height()))
        
        self._reposition_video_control_panel()
        
        # if pixmap present, keep fit behavior (call fit on next tick)
        QTimer.singleShot(0, self.apply_last_zoom)
