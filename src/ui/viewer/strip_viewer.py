from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget, QAbstractSlider
from PyQt6.QtGui import QPixmap, QMouseEvent, QWheelEvent, QImage
from PyQt6.QtCore import Qt, QTimer, QCoreApplication, QEvent

from src.ui.viewer.base_viewer import BaseViewer
from src.workers.view_workers import PixmapLoader, AsyncScaleWorker

class StripViewer(BaseViewer):
    def __init__(self, reader_view):
        super().__init__(reader_view)
        # Move state variables from ReaderView
        self.page_labels: list[QLabel] = []
        self.page_pixmaps: dict[int, QPixmap] = {}
        self.v_labels: list[QLabel] = []
        self.vertical_pixmaps: list[QPixmap] = []
        
        self.strip_scroll_timer = QTimer(reader_view)
        self.strip_scroll_timer.timeout.connect(self._scroll_strip)
        self.scroll_interval = 3
        self.scroll_speeds = [5, 10, 20, 40]
        self.current_scroll_speed_index = 0
        
        self._strip_zoom_factor = 1.0
        self.is_panning = False
        self.last_pan_pos = None
        self.mouse_press_pos = None

        # Performance optimizations
        self.scaled_pixmaps: dict[int, QPixmap] = {}
        self.load_queue: list[int] = []  # Indices waiting to load
        self.loading_indices: set[int] = set() # Indices currently loading
        self.scaling_indices: set[int] = set() # Indices currently scaling
        self.eager_scale_queue: list[int] = [] 
        self.eager_scale_timer = QTimer(reader_view)
        self.eager_scale_timer.timeout.connect(self._process_eager_queue)
        self.MAX_CONCURRENT_LOADS = 4
        self.layout_generation = 0
        self.current_model_images = None
        self.pending_anchor = None

        
    def set_active(self, active: bool):
        if active:
            self.reader_view.page_panel.hide()
            self.reader_view.media_stack.hide()
            self.reader_view.scroll_area.show()
            self.reader_view.scroll_area.verticalScrollBar().setValue(0)
            
            try:
                self.reader_view.scroll_area.verticalScrollBar().valueChanged.disconnect(self._update_visible_images)
            except Exception:
                pass
            self.reader_view.scroll_area.verticalScrollBar().valueChanged.connect(self._update_visible_images)
            
            self.reader_view.layout_btn.setText("Strip")
            self.reader_view.layout_btn.show()

        else:
            self.reader_view.scroll_area.hide()
            self.strip_scroll_timer.stop()
            self.reader_view.top_panel.set_slideshow_state(False)
            try:
                self.reader_view.scroll_area.verticalScrollBar().valueChanged.disconnect(self._update_visible_images)
            except Exception:
                pass


    def load(self, item):
        self._show_vertical_layout()

    def _show_vertical_layout(self):
        self.layout_generation += 1
        self.current_model_images = self.reader_view.model.images

        # Initialize zoom from ReaderView state
        mode = getattr(self.reader_view, 'last_zoom_mode', "Fit Width")
        if mode == "Fit Page" or mode == "Fit Width":
            self._strip_zoom_factor = 1.0
        else:
            try:
                self._strip_zoom_factor = float(mode.replace('%', '')) / 100.0
            except ValueError:
                self._strip_zoom_factor = 1.0

        # Clear existing
        while self.reader_view.vbox.count():
            item = self.reader_view.vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Enforce zero spacing
        self.reader_view.vbox.setSpacing(0)
        self.reader_view.vbox.setContentsMargins(0, 0, 0, 0)
        
        self.page_labels.clear()
        self.page_pixmaps.clear()
        self.scaled_pixmaps.clear()
        self.load_queue.clear()
        self.scaling_indices.clear()
        self.eager_scale_queue.clear()
        self.eager_scale_timer.stop()

        # Load new
        images = self.reader_view.model.images
        for i in range(len(images)):
            lbl = QLabel("Loading...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            lbl.setFixedHeight(300)
            lbl.setContentsMargins(0,0,0,0)
            lbl.setStyleSheet("border: 0px; padding: 0px; margin: 0px; background-color: transparent;")
            self.reader_view.vbox.addWidget(lbl)
            self.page_labels.append(lbl)

        # Prepare load queue
        self.load_queue = list(range(len(images)))
        self.loading_indices.clear()
        
        # Initial load trigger
        self._process_load_queue()


        QTimer.singleShot(0, self._update_visible_images)
        
        # Reset scroll position
        if self.reader_view.model.current_index == 0:
            self.reader_view.scroll_area.verticalScrollBar().setValue(0)
        else:
            QTimer.singleShot(0, lambda: self._scroll_to_page(self.reader_view.model.current_index))

    def _process_load_queue(self):
        # Sort queue based on distance to current view center to prioritize visible images
        if not self.reader_view.scroll_area.isVisible():
            return
            
        scrollbar = self.reader_view.scroll_area.verticalScrollBar()
        viewport_center = scrollbar.value() + self.reader_view.scroll_area.viewport().height() / 2
        
        # Simple heuristic: sort by distance to estimated position
        # Since we don't know exact positions of unloaded images, we rely on index proximity
        # to the currently visible index.
        
        # Find approximate visible index
        visible_index = 0
        min_dist = float('inf')
        for i, lbl in enumerate(self.page_labels):
            center = lbl.y() + lbl.height() / 2
            dist = abs(center - viewport_center)
            if dist < min_dist:
                min_dist = dist
                visible_index = i
                
        self.load_queue.sort(key=lambda x: abs(x - visible_index))

        while len(self.loading_indices) < self.MAX_CONCURRENT_LOADS and self.load_queue:
            index = self.load_queue.pop(0)
            if index in self.page_pixmaps:
                continue # Already loaded
                
            self.loading_indices.add(index)
            images = self.reader_view.model.images
            
            # Guard against outdated queue (model changed but viewer not reloaded yet)
            if index >= len(images) or images is not self.current_model_images:
                if index in self.loading_indices:
                    self.loading_indices.remove(index)
                continue
                
            # images[i] is a Page object
            worker = PixmapLoader(images[index].path, index, self.reader_view.image_viewer._load_pixmap, self.layout_generation)
            worker.signals.finished.connect(self._on_image_loaded)
            self.reader_view.thread_pool.start(worker)

    def _on_image_loaded(self, index: int, pixmap: QPixmap, generation_id: int):
        if generation_id != self.layout_generation:
            return

        if index in self.loading_indices:
            self.loading_indices.remove(index)
            
        if index < len(self.page_labels):
            self.page_pixmaps[index] = pixmap
            
            # Scroll Anchoring Logic
            lbl = self.page_labels[index]
            scrollbar = self.reader_view.scroll_area.verticalScrollBar()
            current_scroll = scrollbar.value()
            
            # Check if this label is strictly above the viewport
            # We use a threshold to determine if it affects the current view
            is_above = (lbl.y() + lbl.height()) < current_scroll
            
            old_height = lbl.height()
            self._resize_single_label(lbl, pixmap, index)
            new_height = lbl.height()
            
            if is_above:
                delta = new_height - old_height
                if delta != 0:
                    # Force layout update to ensure scrollbar maximum is updated
                    self.reader_view.vertical_container.adjustSize()
                    scrollbar.setValue(current_scroll + delta)
            
            # If it's visible, ensure it's polished? _resize_single_label does that.
            
        # Trigger next loads
        self._process_load_queue()

    def _update_visible_images(self):
        if not self.reader_view.scroll_area.isVisible():
            return
            
        viewport_rect = self.reader_view.scroll_area.viewport().rect()
        viewport_top = self.reader_view.scroll_area.verticalScrollBar().value()
        viewport_bottom = viewport_top + viewport_rect.height()

        # Find the topmost visible label
        topmost_visible_index = -1
        for i, lbl in enumerate(self.page_labels):
            if lbl.y() >= viewport_top:
                topmost_visible_index = i
                break

        if topmost_visible_index != -1 and self.reader_view.model.current_index != topmost_visible_index:
            self.reader_view.model.current_index = topmost_visible_index
            self.reader_view.page_panel._update_page_selection(self.reader_view.model.current_index)
            self.reader_view.slider_panel.set_value(self.reader_view.model.current_index)

        # Trigger priority update
        if self.load_queue or self.loading_indices:
             QTimer.singleShot(100, self._process_load_queue)

        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()

            if lbl_bottom >= viewport_top - 1000 and lbl_top <= viewport_bottom + 1000:
                if i in self.page_pixmaps:
                    # Optimize: only resize if needed (e.g. placeholder or size mismatch)
                    # _resize_single_label handles caching
                    # Calculate target width
                    target_w = int(self.reader_view.scroll_area.viewport().width() * self._strip_zoom_factor - (self.reader_view.vbox.contentsMargins().left() + self.reader_view.vbox.contentsMargins().right()))
                    
                    # Check if resize is needed:
                    # 1. No pixmap (Loading...)
                    # 2. Pixmap width doesn't match target (Zoom changed)
                    needs_resize = False
                    if not lbl.pixmap() or lbl.text() == "Loading...":
                        needs_resize = True
                    elif lbl.pixmap() and abs(lbl.pixmap().width() - target_w) > 1:
                        needs_resize = True
                        
                    if needs_resize:
                         self._resize_single_label(lbl, self.page_pixmaps[i], i)
            else:
                 # Optional: Unload pixmap from label to save GPU memory if very far?
                 # For now, keep it simple.
                 pass

    def _resize_single_label(self, label: QLabel, orig_pix: QPixmap, index: int):
        w = self.reader_view.scroll_area.viewport().width() * self._strip_zoom_factor - (self.reader_view.vbox.contentsMargins().left() + self.reader_view.vbox.contentsMargins().right())
        if w <= 0 or orig_pix.isNull():
            return
            
        target_w = int(w)
        
        # Check cache
        if index in self.scaled_pixmaps:
            cached = self.scaled_pixmaps[index]
            if cached.width() == target_w:
                if label.pixmap() != cached:
                    label.setPixmap(cached)
                    label.setFixedHeight(cached.height())
                return
        
        # Check if already scaling
        if index in self.scaling_indices:
            # If label has no pixmap, maybe show a low-res placeholder or just wait?
            # It currently shows "Loading..." or old pixmap.
            return

        # Start Async Scale
        self.scaling_indices.add(index)
        # Convert QPixmap to QImage for thread safety
        q_image = orig_pix.toImage()
        worker = AsyncScaleWorker(q_image, target_w, index, self.layout_generation, high_quality=False)
        worker.signals.finished.connect(self._on_image_scaled)
        self.reader_view.thread_pool.start(worker)

    def _on_image_scaled(self, index: int, q_image: QImage, generation_id: int):
        if generation_id != self.layout_generation:
            return

        if index in self.scaling_indices:
            self.scaling_indices.remove(index)
            
        # Check for stale result
        target_w = int(self.reader_view.scroll_area.viewport().width() * self._strip_zoom_factor - (self.reader_view.vbox.contentsMargins().left() + self.reader_view.vbox.contentsMargins().right()))
        if abs(q_image.width() - target_w) > 5:
            # Stale result (user probably resized again while this was processing)
            return

        # Convert back to QPixmap on main thread
        pixmap = QPixmap.fromImage(q_image)
        self.scaled_pixmaps[index] = pixmap
        
        # Memory Safety: Cache Pruning
        if len(self.scaled_pixmaps) > 50:
            # Remove furthest items
            current_idx = min(index, len(self.page_labels)-1) # approximation
            keys_to_remove = sorted(self.scaled_pixmaps.keys(), key=lambda k: abs(k - current_idx), reverse=True)
            # Remove top 10 furthest
            for k in keys_to_remove[:10]:
                del self.scaled_pixmaps[k]
        
        # Update label if still valid
        if index < len(self.page_labels):
             lbl = self.page_labels[index]
             # Double check target width in case it changed while scaling?
             # For now just set it, if it's wrong it will be fixed on next scroll/resize check
             lbl.setPixmap(pixmap)
             lbl.setFixedHeight(pixmap.height())

    def _resize_vertical_images(self):
        if not self.reader_view.scroll_area.isVisible():
            return
            
        viewport_rect = self.reader_view.scroll_area.viewport().rect()
        viewport_top = self.reader_view.scroll_area.verticalScrollBar().value()
        viewport_bottom = viewport_top + viewport_rect.height()

        # Anchoring Logic: Determine which image is at the top of the viewport
        anchor_index = -1
        anchor_ratio = 0.0
        
        for i, lbl in enumerate(self.page_labels):
            lb_y = lbl.y()
            lb_h = lbl.height()
            if lb_y + lb_h > viewport_top:
                anchor_index = i
                if lb_h > 0:
                    anchor_ratio = (viewport_top - lb_y) / lb_h
                break

        # Invalidate cache on resize/zoom
        self.scaled_pixmaps.clear()
        
        self.scaling_indices.clear()
        
        # 1. Iterate visible range first
        visible_indices = []
        
        # Track Y position for anchoring since layout hasn't updated yet
        running_y = 0 
        new_anchor_y = 0
        
        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()
            
            # Pre-calculate target height for stability
            if i in self.page_pixmaps:
                orig_pix = self.page_pixmaps[i]
                if not orig_pix.isNull() and orig_pix.width() > 0:
                    aspect_ratio = orig_pix.height() / orig_pix.width()
                    target_w = self.reader_view.scroll_area.viewport().width() * self._strip_zoom_factor
                    # Adjust for margins if any (currently 0)
                    margins = self.reader_view.vbox.contentsMargins()
                    target_w -= (margins.left() + margins.right())
                    target_h = int(target_w * aspect_ratio)
                    target_h = int(target_w * aspect_ratio)
                    if lbl.height() != target_h:
                        lbl.setFixedHeight(target_h)
            
            # If this is our anchor, record its new expected Y position
            if i == anchor_index:
                new_anchor_y = running_y
            
            # Accumulate height for next items
            running_y += lbl.height()

            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                visible_indices.append(i)
                if i in self.page_pixmaps:
                    self._resize_single_label(lbl, self.page_pixmaps[i], i)
        
        # 2. Iterate ALL other loaded images (Eager Scaling)
        visible_set = set(visible_indices)
        self.eager_scale_queue = []
        for i, pixmap in self.page_pixmaps.items():
            if i not in visible_set and i < len(self.page_labels):
                lbl = self.page_labels[i]
                
                # Pre-calculate target height for off-screen images too
                if not pixmap.isNull() and pixmap.width() > 0:
                     aspect_ratio = pixmap.height() / pixmap.width()
                     target_w = self.reader_view.scroll_area.viewport().width() * self._strip_zoom_factor
                     target_h = int(target_w * aspect_ratio)
                     if lbl.height() != target_h:
                        lbl.setFixedHeight(target_h)

                self.eager_scale_queue.append(i)
        
        if self.eager_scale_queue:
            self.eager_scale_timer.start(50) # Process every 50ms

        # Restore Anchor
        if anchor_index != -1:
            new_scroll = new_anchor_y + (self.page_labels[anchor_index].height() * anchor_ratio)
            self.reader_view.scroll_area.verticalScrollBar().setValue(int(new_scroll))

    def _process_eager_queue(self):
        # Process a small batch to keep UI responsive
        BATCH_SIZE = 2
        
        count = 0
        while self.eager_scale_queue and count < BATCH_SIZE:
            index = self.eager_scale_queue.pop(0)
            if index in self.page_pixmaps:
                lbl = self.page_labels[index]
                self._resize_single_label(lbl, self.page_pixmaps[index], index)
            count += 1
            
        if not self.eager_scale_queue:
            self.eager_scale_timer.stop()

    def zoom(self, mode: str):
        self.reader_view.last_zoom_mode = mode
        if mode == "Fit Page" or mode == "Fit Width":
            self._strip_zoom_factor = 1.0
            self.reader_view.zoom_changed.emit("Fit Width")
        else:
            try:
                self._strip_zoom_factor = float(mode.replace('%', '')) / 100.0
            except ValueError:
                return # Ignore
        self._resize_vertical_images()

    def on_resize(self, event):
        QTimer.singleShot(0, self._resize_vertical_images)

    def _scroll_strip(self):
        scrollbar = self.reader_view.scroll_area.verticalScrollBar()
        new_value = scrollbar.value() + self.scroll_speeds[self.current_scroll_speed_index]

        if new_value >= scrollbar.maximum():
            if getattr(self.reader_view, 'slideshow_repeat', False):
                scrollbar.setValue(0)
            else:
                self.stop_page_slideshow()
        else:
            scrollbar.setValue(new_value)

    def start_page_slideshow(self):
        if self.strip_scroll_timer.isActive():
            self.stop_page_slideshow()
        else:
            self.strip_scroll_timer.start(self.scroll_interval)
            self.reader_view.top_panel.set_slideshow_state(True)

    def stop_page_slideshow(self):
        self.strip_scroll_timer.stop()
        self.reader_view.top_panel.set_slideshow_state(False)

    def handle_event(self, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_panning = True
                self.last_pan_pos = event.pos()
                self.mouse_press_pos = event.pos()
                self.reader_view.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
        elif event.type() == QEvent.Type.MouseMove:
            if self.is_panning:
                delta = event.pos() - self.last_pan_pos
                self.last_pan_pos = event.pos()
                self.reader_view.scroll_area.horizontalScrollBar().setValue(self.reader_view.scroll_area.horizontalScrollBar().value() - delta.x())
                self.reader_view.scroll_area.verticalScrollBar().setValue(self.reader_view.scroll_area.verticalScrollBar().value() - delta.y())
                self.reader_view._toggle_panels(False)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_panning = False
                self.last_pan_pos = None
                self.reader_view.scroll_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                if self.mouse_press_pos and (event.pos() - self.mouse_press_pos).manhattanLength() < 5:
                    self.reader_view._toggle_panels()
                return True

        elif event.type() == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                self.reader_view.reset_zoom()
                return True

        elif event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                angle = event.angleDelta().y()
                factor = 1.25 if angle > 0 else 0.8
                self._strip_zoom_factor *= factor
                self._resize_vertical_images()
                zoom_str = f"{self._strip_zoom_factor*100:.0f}%"
                self.reader_view.last_zoom_mode = zoom_str
                self.reader_view.zoom_changed.emit(zoom_str)
                return True # Consume
            self.reader_view._toggle_panels(False)

        elif event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._resize_vertical_images)
            
        return False

    def _scroll_to_page(self, page_index: int):
        if 0 <= page_index < len(self.page_labels):
            label = self.page_labels[page_index]
            self.reader_view.scroll_area.verticalScrollBar().setValue(label.y())
