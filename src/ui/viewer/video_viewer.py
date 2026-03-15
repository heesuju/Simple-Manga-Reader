import os
import time
import shutil
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
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
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
        panel.seek_frame.connect(self._seek_to_frame)
        panel.step_frame.connect(self._step_video_frame)

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
            self.video_item.nativeSizeChanged.connect(self._on_native_size_changed)
            
        if self.video_last_frame_item is None:
            self.video_last_frame_item = QGraphicsPixmapItem()
            self.video_last_frame_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.video_last_frame_item.setZValue(-1)

        if self.video_item.scene() != self.reader_view.scene:
            self.video_item.setZValue(1) # Ensure video is on top of potential underlays/stale pixmaps
            self.reader_view.scene.addItem(self.video_item)
            
        if self.video_last_frame_item.scene() != self.reader_view.scene:
            self.video_last_frame_item.setZValue(0) # Underlay below active video
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
        
        # Initial size might be invalid if not loaded, wait for nativeSizeChanged
        # checking if valid immediately just in case
        if not self.video_item.nativeSize().isEmpty():
             self._on_native_size_changed(self.video_item.nativeSize())

        self.media_player.play()
        self.reader_view._reposition_video_control_panel()
        
    def _on_native_size_changed(self, size: QSizeF):
        self.video_item.setSize(size)
        self.video_item.setPos(0, 0)
        self.reader_view.scene.setSceneRect(QRectF(0, 0, size.width(), size.height()))
        self.reader_view.apply_last_zoom()
        
        # Update selection overlay bounds
        if hasattr(self.reader_view.view, '_update_overlay_bounds'):
            self.reader_view.view._update_overlay_bounds()

    def _stop_video(self):
        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.media_player.setVideoOutput(None)
        if self.video_item:
            self.video_item.setData(0, None)

    def _on_last_frame_extracted(self, path, q_image, total_frames, fps):
        if not self.media_player.source().toLocalFile():
            return
            
        # Normalize paths for comparison
        path_norm = os.path.normcase(os.path.normpath(path))
        current_norm = os.path.normcase(os.path.normpath(self.media_player.source().toLocalFile()))
        
        if path_norm == current_norm:
            pixmap = QPixmap.fromImage(q_image)
            self.last_frame_pixmap = pixmap
            # Pass metadata to panel
            self.reader_view.video_control_panel.set_video_metadata(total_frames, fps)
            self.reader_view.frame_panel.set_video(path, total_frames)
            if self.reader_view.panels_visible:
                self.reader_view.frame_panel.show()
            else:
                self.reader_view.frame_panel.hide()
            self.reader_view._update_side_panels_geometry()

    def _seek_to_frame(self, frame_index):
        panel = self.reader_view.video_control_panel
        if panel.fps > 0:
            self.media_player.pause() # Pause when clicking a frame
            timestamp_ms = int(frame_index * 1000 / panel.fps)
            self._set_video_position(timestamp_ms)
            
            # Ensure FramePanel knows we might be seeking to a different range
            # but usually it's already showing the frame we clicked.

    def _set_video_position(self, position):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            self.media_player.pause()
        self.media_player.setPosition(position)

    def _step_video_frame(self, step):
        panel = self.reader_view.video_control_panel
        if panel.fps <= 0: return

        current_pos = self.media_player.position()
        # Use round to find the closest frame to the current reported position
        current_frame = round(current_pos * panel.fps / 1000)
        target_frame = max(0, min(panel.total_frames, current_frame + step))
        
        # When stepping, seek to the MIDDLE of the target frame to avoid boundary precision issues
        # and ensure the decoder actually advances to the new frame.
        target_pos_ms = int((target_frame + 0.5) * 1000 / panel.fps)
        self._set_video_position(target_pos_ms)

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

        # Use actual video item size for underlay, or scene rect since they match now
        scene_rect = self.reader_view.scene.sceneRect()
        if scene_rect.width() <= 0: return

        scaled_pixmap = self.last_frame_pixmap.scaled(
            int(scene_rect.width()), int(scene_rect.height()), 
            Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.video_last_frame_item.setPixmap(scaled_pixmap)
        # Center if aspect ratio differs (unlikely for frame from same video)
        x = (scene_rect.width() - scaled_pixmap.width()) / 2
        y = (scene_rect.height() - scaled_pixmap.height()) / 2
        self.video_last_frame_item.setPos(x, y)

    def on_resize(self, event):
        self.reader_view._reposition_video_control_panel()

    def zoom(self, mode: str):
        # Video zoom implementation
        if not (self.video_item and self.video_item.isVisible()):
            return

        if mode == "Fit Page":
            self.reader_view.view.reset_zoom_state()
            self.reader_view.view.resetTransform()
            
            scene_rect = self.reader_view.scene.sceneRect()
            viewport_rect = self.reader_view.view.viewport().rect()
            
            if scene_rect.width() > 0 and scene_rect.height() > 0:
                scale_w = viewport_rect.width() / scene_rect.width()
                scale_h = viewport_rect.height() / scene_rect.height()
                scale = min(scale_w, scale_h)
                
                self.reader_view.view.scale(scale, scale)
                self.reader_view.view.centerOn(scene_rect.center())
                
                self.reader_view.view._zoom_factor = scale

            self.reader_view.zoom_changed.emit("Fit Page")
        else:
            try:
                zoom_value = float(mode.replace('%', '')) / 100.0
                
                self.reader_view.view.reset_zoom_state()
                self.reader_view.view.resetTransform()
                self.reader_view.view.scale(zoom_value, zoom_value)
                
                # Center on the image to ensure predictable positioning
                if self.reader_view.scene.sceneRect().isValid():
                     self.reader_view.view.centerOn(self.reader_view.scene.sceneRect().center())

                self.reader_view.view._zoom_factor = zoom_value
                
                # Manually update tracking in ReaderView to keep UI in sync
                self.reader_view.last_zoom_mode = f"{int(zoom_value*100)}%"
                self.reader_view.zoom_changed.emit(self.reader_view.last_zoom_mode)
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

    def _on_media_status_changed(self, status):
        # Fallback for formats that reach EndOfMedia but don't reliably trigger StoppedState
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.video_repeat:
                self.media_player.setPosition(0)
                self.media_player.play()
            elif self.auto_play:
                self._play_next_video()
            else:
                # Stay at end, but ensure we keep the frame visible for seeking
                # some backends clear the buffer on stop, so we stay in paused state at end
                self.media_player.pause()
                self.media_player.setPosition(self.media_player.duration())

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
        
        save_area_action = QAction("Save Area As...", self.reader_view)
        save_area_action.triggered.connect(self.reader_view.start_area_selection)
        menu.addAction(save_area_action)
        
        menu.addSeparator()

        add_file_action = QAction("Add Alternate from File...", self.reader_view)
        add_file_action.triggered.connect(self._add_alt_from_file)
        menu.addAction(add_file_action)

        add_dd_action = QAction("Add Alternates (Drag & Drop)...", self.reader_view)
        add_dd_action.triggered.connect(self._open_drag_drop_dialog)
        menu.addAction(add_dd_action)

        # Convert scene pos to screen pos for menu display
        view_pos = self.reader_view.view.mapFromScene(scene_pos)
        global_pos = self.reader_view.view.mapToGlobal(view_pos)
        
        menu.exec(global_pos)

    def _save_current_video(self):
        path = self.video_item.data(0)
        if not path:
            return
            
        is_virtual = '|' in path
        if not is_virtual and not os.path.exists(path):
            return

        was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if was_playing:
            self.media_player.pause()

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
                if '|' in path:
                    from src.utils.img_utils import get_image_data_from_zip
                    data = get_image_data_from_zip(path)
                    if data:
                        with open(file_path, "wb") as f:
                            f.write(data)
                    else:
                        raise Exception("Failed to extract video from zip")
                else:
                    shutil.copy2(path, file_path)
            except Exception as e:
                print(f"Error saving video: {e}")
        
        if was_playing:
            self.media_player.play()

    def _add_alt_from_file(self):
        default_dir = self.reader_view.model.manga_dir if self.reader_view.model else ""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self.reader_view, 
            "Select Images/Videos", 
            str(default_dir), 
            "Media Files (*.png *.jpg *.jpeg *.jpe *.webp *.gif *.mp4 *.webm *.mkv)"
        )
        if file_paths:
            self.reader_view._add_alts_from_files(file_paths)

    def _open_drag_drop_dialog(self):
        from src.ui.components.drag_drop_alt_dialog import DragDropAltDialog
        
        target_index = self.reader_view.model.current_index
        if target_index == -1: return
        
        page_obj = self.reader_view.model.images[target_index]
        existing_cats = list(page_obj.get_categorized_variants().keys())

        dialog = DragDropAltDialog(self.reader_view, existing_categories=existing_cats)
        if dialog.exec():
            files = dialog.get_files()
            cat = dialog.get_category()
            if files:
                 import src.ui.page_utils as page_utils
                 page_utils.process_add_alts(
                    self.reader_view.model,
                    files,
                    target_index,
                    lambda: self.reader_view.reload_chapter(),
                    lambda idx: self.reader_view.model.update_page_variants(idx),
                    category=cat if cat else None
                )

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
                "Images (*.png *.jpg *.jpeg *.jpe *.webp)"
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

    def save_area(self, scene_rect, size_limit_mb=None):
        if not self.video_item or self.media_player.source().isEmpty():
            return
            
        current_time = self.media_player.position()
        source_path = self.media_player.source().toLocalFile()
        
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # Default to jpg for better balance of size/quality from videos
        initial_path = os.path.join(downloads_dir, f"crop_frame_{timestamp}.jpg")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self.reader_view,
            "Save Cropped Frame As",
            initial_path,
            "JPEG Image (*.jpg *.jpeg *.jpe);;PNG Image (*.png);;WebP Image (*.webp);;All Files (*)"
        )
        
        if file_path:
            worker = VideoTimestampFrameExtractorWorker(source_path, current_time, file_path)
            # Pass metadata to handler
            worker.signals.finished.connect(
                lambda s, img, p: self._on_area_frame_extracted(idx=None, img=img, save_path=p, rect=scene_rect, limit=size_limit_mb)
            )
            self.reader_view.thread_pool.start(worker)

    def _on_area_frame_extracted(self, idx, img, save_path, rect, limit):
        # Crop
        intersected = rect.toRect().intersected(img.rect())
        if intersected.width() <= 0 or intersected.height() <= 0:
            return
        
        cropped = img.copy(intersected)
        ext = os.path.splitext(save_path)[1].lower()
        if ext in [".jpg", ".jpeg", ".jpe"]: fmt = "JPEG"
        elif ext == ".webp": fmt = "WEBP"
        else: fmt = "PNG"

        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtCore import QByteArray, QBuffer, Qt

        if limit:
            target_bytes = limit * 1024 * 1024
            
            # Fast path
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            quality = 95 if fmt in ["JPEG", "WEBP"] else -1
            cropped.save(buf, fmt, quality)
            
            if ba.size() <= target_bytes:
                try:
                    with open(save_path, "wb") as f:
                        f.write(ba.data())
                    return
                except Exception as e:
                    QMessageBox.warning(self.reader_view, "Error", f"Failed to save file:\n{e}")
                    return

            if fmt in ["JPEG", "WEBP"]:
                # Binary search quality
                low, high = 0, 100
                best_data = None
                for _ in range(8):
                    mid = (low + high) // 2
                    ba = QByteArray()
                    buf = QBuffer(ba)
                    buf.open(QBuffer.OpenModeFlag.WriteOnly)
                    cropped.save(buf, fmt, mid)
                    if ba.size() <= target_bytes:
                        best_data = ba
                        low = mid + 1
                    else:
                        high = mid - 1
                
                if best_data is None:
                    # Downscale
                    scale = 0.9
                    curr_img = cropped
                    while True:
                        w = int(curr_img.width() * scale)
                        h = int(curr_img.height() * scale)
                        if w < 10 or h < 10: break
                        curr_img = curr_img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QBuffer.OpenModeFlag.WriteOnly)
                        curr_img.save(buf, fmt, 0)
                        if ba.size() <= target_bytes:
                            best_data = ba
                            break
                
                if best_data:
                    try:
                        with open(save_path, "wb") as f:
                            f.write(best_data.data())
                    except Exception as e:
                        QMessageBox.warning(self.reader_view, "Error", f"Failed to save file:\n{e}")
                else:
                    QMessageBox.warning(self.reader_view, "Error", "Could not compress to the target size.")
            else:
                cropped.save(save_path, "PNG")
                if os.path.getsize(save_path) > target_bytes:
                    QMessageBox.warning(self.reader_view, "Warning", "Saved PNG exceeds the size limit. Use JPEG or WebP for better compression.")
        else:
            quality = 95 if fmt in ["JPEG", "WEBP"] else -1
            cropped.save(save_path, fmt, quality)

    def cleanup(self):
        self._stop_video()
        
    def reset(self):
        self._stop_video()
        self.video_item = None
        self.video_last_frame_item = None
        self.last_frame_pixmap = None
