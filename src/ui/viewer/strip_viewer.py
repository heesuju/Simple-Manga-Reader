from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget, QAbstractSlider
from PyQt6.QtGui import QPixmap, QMouseEvent, QWheelEvent
from PyQt6.QtCore import Qt, QTimer, QCoreApplication, QEvent

from src.ui.viewer.base_viewer import BaseViewer
from src.workers.view_workers import PixmapLoader

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
        self._strip_zoom_factor = 1.0

        # Clear existing
        while self.reader_view.vbox.count():
            item = self.reader_view.vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.page_labels.clear()
        self.page_pixmaps.clear()

        # Load new
        images = self.reader_view.model.images
        for i in range(len(images)):
            lbl = QLabel("Loading...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(300)
            lbl.setContentsMargins(0,0,0,0)
            lbl.setStyleSheet("border: 0px; padding: 0px; margin: 0px;")
            self.reader_view.vbox.addWidget(lbl)
            self.page_labels.append(lbl)

            # Updated to pass load_func instead of reader_view
            # images[i] is a Page object, we need the path string
            worker = PixmapLoader(images[i].path, i, self.reader_view.image_viewer._load_pixmap)
            worker.signals.finished.connect(self._on_image_loaded)
            self.reader_view.thread_pool.start(worker)

        QTimer.singleShot(0, self._update_visible_images)
        
        # Reset scroll position
        if self.reader_view.model.current_index == 0:
            self.reader_view.scroll_area.verticalScrollBar().setValue(0)
        else:
            QTimer.singleShot(0, lambda: self._scroll_to_page(self.reader_view.model.current_index))

    def _on_image_loaded(self, index: int, pixmap: QPixmap):
        if index < len(self.page_labels):
            self.page_pixmaps[index] = pixmap
            # Only resize if the label is visible
            lbl = self.page_labels[index]
            viewport_rect = self.reader_view.scroll_area.viewport().rect()
            viewport_top = self.reader_view.scroll_area.verticalScrollBar().value()
            viewport_bottom = viewport_top + viewport_rect.height()
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()
            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                self._resize_single_label(lbl, pixmap)

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

        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()

            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                if i in self.page_pixmaps:
                    self._resize_single_label(lbl, self.page_pixmaps[i])
            else:
                lbl.clear()

    def _resize_single_label(self, label: QLabel, orig_pix: QPixmap):
        w = self.reader_view.scroll_area.viewport().width() * self._strip_zoom_factor - (self.reader_view.vbox.contentsMargins().left() + self.reader_view.vbox.contentsMargins().right())
        if w <= 0 or orig_pix.isNull():
            return
        scaled = orig_pix.scaledToWidth(int(w), Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(scaled)
        label.setFixedHeight(scaled.height())

    def _resize_vertical_images(self):
        if not self.reader_view.scroll_area.isVisible():
            return
            
        viewport_rect = self.reader_view.scroll_area.viewport().rect()
        viewport_top = self.reader_view.scroll_area.verticalScrollBar().value()
        viewport_bottom = viewport_top + viewport_rect.height()

        for i, lbl in enumerate(self.page_labels):
            lbl_top = lbl.y()
            lbl_bottom = lbl.y() + lbl.height()
            if lbl_bottom >= viewport_top - 500 and lbl_top <= viewport_bottom + 500:
                if i in self.page_pixmaps:
                    self._resize_single_label(lbl, self.page_pixmaps[i])

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
