from typing import List
from pathlib import Path

from PyQt6.QtCore import QThreadPool
from src.ui.collapsible_panel import CollapsiblePanel
from src.ui.thumbnail_widget import ThumbnailWidget
from src.core.thumbnail_worker import ThumbnailWorker
from src.utils.img_utils import _get_first_image_path

class ChapterPanel(CollapsiblePanel):
    def __init__(self, parent=None, on_chapter_changed=None):
        super().__init__(parent, "Chapter")
        self.thread_pool = QThreadPool()
        self.on_chapter_changed = on_chapter_changed
        self.chapter_thumbnail_widgets = []
        self.current_chapter_thumbnail = None
        self.input_label.enterPressed.connect(self.on_chapter_changed)
    
    def _update_chapter_thumbnails(self, chapters:List[object]):
        for i in reversed(range(self.thumbnails_layout.count() - 1)):
            self.thumbnails_layout.itemAt(i).widget().setParent(None)
        self.chapter_thumbnail_widgets.clear()

        for i, chapter in enumerate(chapters):
            chapter_name = Path(str(chapter)).name
            widget = ThumbnailWidget(i, chapter_name)
            widget.clicked.connect(self._change_chapter_by_thumbnail)
            self.thumbnails_layout.insertWidget(i, widget)
            self.chapter_thumbnail_widgets.append(widget)

            first_image_path = _get_first_image_path(chapter)
            if first_image_path:
                worker = ThumbnailWorker(i, first_image_path, self._load_thumbnail)
                worker.signals.finished.connect(self._on_chapter_thumbnail_loaded)
                self.thread_pool.start(worker)

    def _on_chapter_thumbnail_loaded(self, index, pixmap):
        if index < len(self.chapter_thumbnail_widgets):
            self.chapter_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_chapter_selection(self, index):
        if self.current_chapter_thumbnail:
            self.current_chapter_thumbnail.set_selected(False)
        
        if index < len(self.chapter_thumbnail_widgets):
            self.current_chapter_thumbnail = self.chapter_thumbnail_widgets[index]
            self.current_chapter_thumbnail.set_selected(True)
            self.content_area.ensureWidgetVisible(self.current_chapter_thumbnail)

        self.input_label.set_total(len(self.chapter_thumbnail_widgets))
        self.input_label.set_value(index+1)

    def _change_chapter_by_thumbnail(self, index: int):
        self.on_chapter_changed(index + 1)
