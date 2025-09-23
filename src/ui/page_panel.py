from PyQt6.QtCore import QThreadPool
from src.ui.collapsible_panel import CollapsiblePanel
from src.ui.thumbnail_widget import ThumbnailWidget
from src.core.thumbnail_worker import ThumbnailWorker
from src.data.reader_model import ReaderModel
from src.enums import ViewMode
from src.utils.img_utils import empty_placeholder

class PagePanel(CollapsiblePanel):
    def __init__(self, parent=None, model:ReaderModel=None, on_page_changed=None):
        super().__init__(parent, "Page")
        self.thumbnails_layout.setSpacing(0)
        self.thread_pool = QThreadPool()
        self.model = model
        self.on_page_changed = on_page_changed
        self.page_thumbnail_widgets = []
        self.current_page_thumbnails = []
        self.input_label.enterPressed.connect(self.on_page_changed)
        
    def _update_page_thumbnails(self, model:ReaderModel):
        for i in reversed(range(self.thumbnails_layout.count() - 1)):
            self.thumbnails_layout.itemAt(i).widget().setParent(None)
        self.page_thumbnail_widgets.clear()

        images = model.images
        if model.view_mode == ViewMode.DOUBLE:
            images = model._get_double_view_images()

        for i, image_path in enumerate(images):
            widget = ThumbnailWidget(i, str(i+1))
            widget.clicked.connect(self._change_page_by_thumbnail)
            self.thumbnails_layout.insertWidget(i, widget)
            self.page_thumbnail_widgets.append(widget)

            if image_path == "placeholder":
                self._on_page_thumbnail_loaded(i, empty_placeholder())
            else:
                worker = ThumbnailWorker(i, image_path, self._load_thumbnail)
                worker.signals.finished.connect(self._on_page_thumbnail_loaded)
                self.thread_pool.start(worker)
        
        self._update_page_selection(model.current_index)

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
            self.content_area.snapToItem(index)

            # Select next page if it exists
            if index + 1 < len(self.page_thumbnail_widgets):
                next_thumb = self.page_thumbnail_widgets[index + 1]
                next_thumb.set_selected(True)
                self.current_page_thumbnails.append(next_thumb)
        else:  # Single or Strip mode
            current_thumb = self.page_thumbnail_widgets[index]
            current_thumb.set_selected(True)
            self.current_page_thumbnails.append(current_thumb)
            self.content_area.snapToItem(index)

        self.input_label.set_total(len(self.page_thumbnail_widgets))
        self.input_label.set_value(index + 1)

    def _change_page_by_thumbnail(self, index: int):
        self.on_page_changed(index + 1)