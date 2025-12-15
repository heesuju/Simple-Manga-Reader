from PyQt6.QtCore import QThreadPool, QTimer
from src.ui.base.collapsible_panel import CollapsiblePanel
from src.ui.page_thumbnail import PageThumbnail
from src.workers.thumbnail_worker import ThumbnailWorker
from src.data.reader_model import ReaderModel
from src.enums import ViewMode
from src.utils.img_utils import empty_placeholder, load_thumbnail_from_path, load_thumbnail_from_virtual_path

class PagePanel(CollapsiblePanel):
    def __init__(self, parent=None, model:ReaderModel=None, on_page_changed=None):
        super().__init__(parent, "Page")
        self.thumbnails_layout.setSpacing(0)
        self.thread_pool = QThreadPool()
        self.model = model
        self.on_page_changed = on_page_changed
        self.page_thumbnail_widgets = []
        self.current_page_thumbnails = []

        self.BATCH_SIZE = 20
        self.image_paths_to_load = []
        self.current_batch_index = 0
        self.batch_timer = QTimer(self)
        self.batch_timer.setSingleShot(True)
        self.batch_timer.timeout.connect(self._add_next_thumbnail_batch)
        
        self.navigate_first.connect(self._go_first)
        self.navigate_prev.connect(self._go_prev)
        self.navigate_next.connect(self._go_next)
        self.navigate_last.connect(self._go_last)

    def _go_first(self):
        if self.model:
            self.on_page_changed(1)

    def _go_prev(self):
        if self.model:
            current = self.model.current_index + 1
            # Check model mode for step usage? For now single step.
            if current > 1:
                self.on_page_changed(current - 1)

    def _go_next(self):
        if self.model:
            current = self.model.current_index + 1
            if current < len(self.model.images):
                self.on_page_changed(current + 1)

    def _go_last(self):
        if self.model:
            self.on_page_changed(len(self.model.images))

    def showEvent(self, event):
        super().showEvent(event)
        if self.model:
             # Defer the snap slightly to ensure layout is ready
            QTimer.singleShot(50, lambda: self._update_page_selection(self.model.current_index))

    def _load_thumbnail(self, path: str):
        if '|' in path:
            return load_thumbnail_from_virtual_path(path, 150, 200)
        else:
            return load_thumbnail_from_path(path, 150, 200)
        
    def _update_page_thumbnails(self, model:ReaderModel):
        self.batch_timer.stop()
        
        for i in reversed(range(self.thumbnails_layout.count() - 1)):
            widget = self.thumbnails_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.page_thumbnail_widgets.clear()

        images = model.images
        if model.view_mode == ViewMode.DOUBLE:
            images = model._get_double_view_images()

        self.image_paths_to_load = images
        self.current_batch_index = 0
        
        if self.image_paths_to_load:
            self.batch_timer.start(10) # Start loading the first batch

    def _add_next_thumbnail_batch(self):
        start_index = self.current_batch_index
        end_index = min(start_index + self.BATCH_SIZE, len(self.image_paths_to_load))

        for i in range(start_index, end_index):
            image_path = self.image_paths_to_load[i]
            widget = PageThumbnail(i, str(i + 1))
            widget.clicked.connect(self._change_page_by_thumbnail)
            self.thumbnails_layout.insertWidget(i, widget)
            self.page_thumbnail_widgets.append(widget)

            if image_path == "placeholder":
                self._on_page_thumbnail_loaded(i, empty_placeholder())
            else:
                worker = ThumbnailWorker(i, image_path, self._load_thumbnail)
                worker.signals.finished.connect(self._on_page_thumbnail_loaded)
                self.thread_pool.start(worker)

        self.current_batch_index = end_index
        if self.current_batch_index < len(self.image_paths_to_load):
            self.batch_timer.start(10) # Schedule the next batch

        self._update_page_selection(self.model.current_index)

    def _on_page_thumbnail_loaded(self, index, pixmap):
        if index < len(self.page_thumbnail_widgets):
            self.page_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_page_selection(self, index):
        for thumbnail in self.current_page_thumbnails:
            thumbnail.set_selected(False)
        self.current_page_thumbnails.clear()

        if index >= len(self.page_thumbnail_widgets):
            return

        # Select new thumbnail(s)
        if self.model.view_mode == ViewMode.DOUBLE:
            # Select current page
            current_thumb = self.page_thumbnail_widgets[index]
            current_thumb.set_selected(True)
            self.current_page_thumbnails.append(current_thumb)
            self.content_area.snapToItemIfOutOfView(index)

            # Select next page if it exists
            if index + 1 < len(self.page_thumbnail_widgets):
                next_thumb = self.page_thumbnail_widgets[index + 1]
                next_thumb.set_selected(True)
                self.current_page_thumbnails.append(next_thumb)
        else:  # Single or Strip mode
            current_thumb = self.page_thumbnail_widgets[index]
            current_thumb.set_selected(True)
            self.current_page_thumbnails.append(current_thumb)
            self.content_area.snapToItemIfOutOfView(index, current_thumb.width())

    def _change_page_by_thumbnail(self, index: int):
        self.on_page_changed(index + 1)