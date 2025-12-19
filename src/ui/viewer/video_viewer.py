import os
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtGui import QPixmap, QAction
from PyQt6.QtWidgets import QMenu, QFileDialog, QGraphicsPixmapItem
from PyQt6.QtCore import QUrl, QSizeF, QRectF, Qt, pyqtSignal, QPointF

from src.ui.viewer.base_viewer import BaseViewer
from src.workers.view_workers import VideoFrameExtractorWorker, VideoTimestampFrameExtractorWorker, VIDEO_EXTS

class VideoItem(QGraphicsVideoItem):
    context_menu_requested = pyqtSignal(object) # QPointF (scene pos)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(event.scenePos())


class VideoViewer(BaseViewer):
    def __init__(self, reader_view):
        super().__init__(reader_view)
        
        self.media_player = QMediaPlayer(reader_view)
        self.audio_output = QAudioOutput(reader_view)
        self.media_player.setAudioOutput(self.audio_output)
        
        self.video_item: VideoItem | None = None
        self.video_last_frame_item: QGraphicsPixmapItem | None = None
        self.last_frame_pixmap: QPixmap | None = None
        
        self.playback_speeds = [1.0, 1.25, 1.5, 1.75, 2.0, 0.5, 0.75]
        self.current_speed_index = 0
        self.video_repeat = True
        self.auto_play = False
        
        self._connect_signals()

    def _connect_signals(self):
        self.media_player.playbackStateChanged.connect(self._on_media_playback_state_changed)
        self.media_player.durationChanged.connect(self.reader_view.video_control_panel.set_duration)
        self.media_player.positionChanged.connect(self.reader_view.video_control_panel.set_position)
        self.media_player.positionChanged.connect(self._check_underlay_visibility)

        # Connect panel signals
        panel = self.reader_view.video_control_panel
        panel.play_pause_clicked.connect(self._toggle_play_pause)
        panel.volume_changed.connect(self._set_volume)
        panel.position_changed.connect(self._set_video_position)
        panel.speed_clicked.connect(self._change_playback_speed)
        panel.repeat_clicked.connect(self._set_video_repeat)
        panel.auto_play_toggled.connect(self._set_auto_play)

    def set_active(self, active: bool):
        if active:
            self._ensure_items_in_scene()
            if self.video_item:
                self.video_item.setVisible(True)
            self.reader_view.media_stack.show()
            self.reader_view.media_stack.setCurrentWidget(self.reader_view.view)
            self.reader_view.layout_btn.hide()
            self.reader_view.video_control_panel.show() # Will be positioned by event filter or manual call
        else:
            self._stop_video()
            if self.video_item:
                self.video_item.setVisible(False)
            if self.video_last_frame_item:
                self.video_last_frame_item.setVisible(False)
            self.reader_view.video_control_panel.hide()

    def load(self, path: str):
        self._play_video(path)

    def _ensure_items_in_scene(self):
        if self.video_item is None:
            self.video_item = VideoItem()
            self.video_item.context_menu_requested.connect(self._show_context_menu)
            # self.reader_view.scene.addItem(self.video_item) handled below logic 
            
        if self.video_last_frame_item is None:
            self.video_last_frame_item = QGraphicsPixmapItem()
            self.video_last_frame_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.video_last_frame_item.setZValue(-1)

        # Add to scene if not present
        if self.video_item.scene() != self.reader_view.scene:
            self.reader_view.scene.addItem(self.video_item)
            
        if self.video_last_frame_item.scene() != self.reader_view.scene:
            self.reader_view.scene.addItem(self.video_last_frame_item)

    def _play_video(self, path: str):
        self._ensure_items_in_scene()
        
        try:
            self.media_player.stop()
        except Exception:
            pass

        # Extract last frame
        worker = VideoFrameExtractorWorker(path)
        worker.signals.finished.connect(self._on_last_frame_extracted)
        self.reader_view.thread_pool.start(worker)

        self.video_last_frame_item.setVisible(False)
        self.last_frame_pixmap = None

        self.media_player.setVideoOutput(self.video_item)
        self.media_player.setSource(QUrl.fromLocalFile(path))
        self.video_item.setData(0, path)
        self.video_item.setVisible(True)
        
        vp = self.reader_view.view.viewport().size()
        self.video_item.setSize(QSizeF(vp.width(), vp.height()))
        self.video_item.setPos(0, 0)
        
        self.reader_view.scene.setSceneRect(QRectF(0, 0, vp.width(), vp.height()))
        self.media_player.play()
        self.reader_view._reposition_video_control_panel()
        self.reader_view.apply_last_zoom()

    def _stop_video(self):
        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.media_player.setVideoOutput(None)
        if self.video_item:
            self.video_item.setData(0, None)

    def _on_last_frame_extracted(self, path, q_image):
        if not self.media_player.source().toLocalFile():
            return
            
        # Normalize paths for comparison
        path_norm = os.path.normcase(os.path.normpath(path))
        current_norm = os.path.normcase(os.path.normpath(self.media_player.source().toLocalFile()))
        
        if path_norm == current_norm:
            pixmap = QPixmap.fromImage(q_image)
            self.last_frame_pixmap = pixmap

    def _check_underlay_visibility(self, position):
        if (self.video_last_frame_item and 
            self.last_frame_pixmap and 
            not self.video_last_frame_item.isVisible() and 
            position > 100):
            
            self.video_last_frame_item.setVisible(True)
            self._update_video_underlay_geometry()

    def _update_video_underlay_geometry(self):
        if not (self.video_last_frame_item and self.video_last_frame_item.isVisible() and self.last_frame_pixmap):
            return

        vp = self.reader_view.view.viewport().size()
        scaled_pixmap = self.last_frame_pixmap.scaled(
            vp.width(), vp.height(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.video_last_frame_item.setPixmap(scaled_pixmap)
        x = (vp.width() - scaled_pixmap.width()) / 2
        y = (vp.height() - scaled_pixmap.height()) / 2
        self.video_last_frame_item.setPos(x, y)

    def on_resize(self, event):
        if self.video_item and self.video_item.isVisible():
            vp = self.reader_view.view.viewport().size()
            self.video_item.setSize(QSizeF(vp.width(), vp.height()))
            self.video_item.setPos(0, 0)
            self._update_video_underlay_geometry()
            self.reader_view.scene.setSceneRect(QRectF(0, 0, vp.width(), vp.height()))
            
        self.reader_view._reposition_video_control_panel()

    def zoom(self, mode: str):
        # Video zoom implementation
        if not (self.video_item and self.video_item.isVisible()):
            return

        if mode == "Fit Page":
            self.reader_view.view.resetTransform()
            self.reader_view.view.fitInView(self.reader_view.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.reader_view.view.reset_zoom_state()
            self.reader_view.zoom_changed.emit("Fit Page")
        else:
            try:
                zoom_value = float(mode.replace('%', '')) / 100.0
                self.reader_view.view._zoom_factor = zoom_value
                self.reader_view._update_zoom(zoom_value)
            except ValueError:
                pass

    def _on_media_playback_state_changed(self, state):
        self.reader_view.video_control_panel.set_playing(state == QMediaPlayer.PlaybackState.PlayingState)
        if state == QMediaPlayer.PlaybackState.StoppedState:
            if self.video_repeat:
                self.media_player.play()
            elif self.auto_play:
                # Logic to find next video. 
                # Ideally we ask ReaderView to "go to next video"
                self._play_next_video()

    def _play_next_video(self):
        # Logic extracted from ReaderView._on_media_playback_state_changed
        start_index = self.reader_view.model.current_index + 1
        found_index = -1
        images = self.reader_view.model.images
        for i in range(start_index, len(images)):
            next_file = images[i]
            ext = os.path.splitext(next_file)[1].lower()
            if ext in VIDEO_EXTS:
                found_index = i
                break
        
        if found_index != -1:
            self.reader_view.change_page(found_index + 1)

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
        self.reader_view.video_control_panel.set_speed_text(f"{speed}x")

    def _set_video_repeat(self, repeat):
        self.video_repeat = repeat

    def _set_auto_play(self, enabled):
        self.auto_play = enabled

    def _show_context_menu(self, scene_pos: QPointF):
        menu = QMenu()
        
        save_frame_action = QAction("Save Current Frame", self.reader_view)
        save_frame_action.triggered.connect(self._save_current_frame)
        menu.addAction(save_frame_action)
        
        save_video_action = QAction("Save Video As...", self.reader_view)
        save_video_action.triggered.connect(self._save_current_video)
        menu.addAction(save_video_action)
        
        # Convert scene pos to screen pos for menu display
        view_pos = self.reader_view.view.mapFromScene(scene_pos)
        global_pos = self.reader_view.view.mapToGlobal(view_pos)
        
        menu.exec(global_pos)

    def _save_current_video(self):
        path = self.video_item.data(0)
        if not path or not os.path.exists(path):
            return

        was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if was_playing:
            self.media_player.pause()

        import shutil
        base_name = os.path.basename(path)
        ext = os.path.splitext(base_name)[1]
        
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        initial_path = os.path.join(downloads_dir, base_name)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self.reader_view,
            "Save Video As",
            initial_path,
            f"Video (*{ext});;All Files (*)"
        )
        
        if file_path:
            try:
                shutil.copy2(path, file_path)
            except Exception as e:
                print(f"Error copying video: {e}")
        
        if was_playing:
            self.media_player.play()

    def _save_current_frame(self):
        # Pause video while saving
        was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if was_playing:
            self.media_player.pause()
            
        current_time = self.media_player.position()
        
        # Determine default filename
        if self.media_player.source().toLocalFile():
            base_name = os.path.splitext(os.path.basename(self.media_player.source().toLocalFile()))[0]
            default_name = f"{base_name}_frame_{current_time}ms.png"
            
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            initial_path = os.path.join(downloads_dir, default_name)
            
            file_path, _ = QFileDialog.getSaveFileName(
                self.reader_view,
                "Save Current Frame",
                initial_path,
                "Images (*.png *.jpg *.webp)"
            )
            
            if file_path:
                source_path = self.media_player.source().toLocalFile()
                worker = VideoTimestampFrameExtractorWorker(source_path, current_time, file_path)
                worker.signals.finished.connect(self._on_frame_saved)
                self.reader_view.thread_pool.start(worker)
            elif was_playing:
                # Resume if user cancelled and it was playing
                self.media_player.play()
        elif was_playing:
            self.media_player.play()

    def _on_frame_saved(self, source_path, q_image, save_path):
        q_image.save(save_path)
        # Optional: Show a small notification or status bar message
        # For now we assume typical user flow, maybe just log or do nothing.
        # Could verify by checking if file exists.
        pass

    def cleanup(self):
        self._stop_video()
        
    def reset(self):
        self._stop_video()
        self.video_item = None
        self.video_last_frame_item = None
        self.last_frame_pixmap = None
