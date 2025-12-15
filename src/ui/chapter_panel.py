from typing import List
from pathlib import Path

from PyQt6.QtCore import QThreadPool, QTimer
from src.ui.base.collapsible_panel import CollapsiblePanel
from src.ui.page_thumbnail import PageThumbnail
from src.workers.thumbnail_worker import ThumbnailWorker
from src.utils.img_utils import _get_first_image_path, draw_text_on_image, load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.data.reader_model import ReaderModel

class ChapterPanel(CollapsiblePanel):
    def __init__(self, parent=None, model:ReaderModel=None, on_chapter_changed=None):
        super().__init__(parent, "Chapter")
        self.model = model
        self.thread_pool = QThreadPool()
        self.on_chapter_changed = on_chapter_changed
        self.chapter_thumbnail_widgets = []
        self.current_chapter_thumbnail = None
        self.BATCH_SIZE = 10
        self.chapters_to_load = []
        self.current_batch_index = 0
        self.batch_timer = QTimer(self)
        self.batch_timer.setSingleShot(True)
        self.batch_timer.timeout.connect(self._add_next_batch)

        self.navigate_first.connect(self._go_first)
        self.navigate_prev.connect(self._go_prev)
        self.navigate_next.connect(self._go_next)
        self.navigate_last.connect(self._go_last)

    def _go_first(self):
        if self.model and self.model.chapters:
            self.on_chapter_changed(1)

    def _go_prev(self):
        if self.model and self.model.chapters:
            # current_index is 0-based. If index is 5 (chapter 6), we want chapter 5 (index 4).
            # on_chapter_changed takes 1-based index (chapter number)
            # Chapter 6 is #6. Previous is #5.
            current = self.model.chapter_index + 1
            if current > 1:
                self.on_chapter_changed(current - 1)

    def _go_next(self):
        if self.model and self.model.chapters:
            current = self.model.chapter_index + 1
            if current < len(self.model.chapters):
                self.on_chapter_changed(current + 1)

    def _go_last(self):
        if self.model and self.model.chapters:
            self.on_chapter_changed(len(self.model.chapters))

    def showEvent(self, event):
        super().showEvent(event)
        if self.model and self.current_chapter_thumbnail:
             # Defer the snap slightly to ensure layout is ready
            QTimer.singleShot(50, lambda: self.content_area.snapToItemIfOutOfView(self.model.chapter_index, self.current_chapter_thumbnail.width()))

    def _load_thumbnail(self, path):
        if '|' in path:
            return load_thumbnail_from_virtual_path(path, 150, 200)
        else:
            return load_thumbnail_from_path(path, 150, 200)
    
    def _update_chapter_thumbnails(self, chapters:List[object]):
        for i in reversed(range(self.thumbnails_layout.count() - 1)):
            self.thumbnails_layout.itemAt(i).widget().setParent(None)
        self.chapter_thumbnail_widgets.clear()

        self.chapters_to_load = chapters
        self.current_batch_index = 0
        self.batch_timer.start(50)

    def _add_next_batch(self):
        start = self.current_batch_index
        end = min(start + self.BATCH_SIZE, len(self.chapters_to_load))

        self.content_area.setUpdatesEnabled(False)
        try:
            for i in range(start, end):
                chapter = self.chapters_to_load[i]
                # Use index 'i' correctly
                chapter_name = Path(str(chapter)).name
                widget = PageThumbnail(i, chapter_name)
                widget.clicked.connect(self._change_chapter_by_thumbnail)
                self.thumbnails_layout.insertWidget(i, widget)
                self.chapter_thumbnail_widgets.append(widget)

                first_image_path = _get_first_image_path(chapter)
                if first_image_path:
                    worker = ThumbnailWorker(i, first_image_path, self._load_thumbnail)
                    worker.signals.finished.connect(self._on_chapter_thumbnail_loaded)
                    self.thread_pool.start(worker)
        finally:
             self.content_area.setUpdatesEnabled(True)

        self.current_batch_index = end
        if self.current_batch_index < len(self.chapters_to_load):
            self.batch_timer.start(50)
        else:
             # Re-apply selection if needed
             if self.model and self.model.chapter_index < len(self.chapter_thumbnail_widgets):
                 self._update_chapter_selection(self.model.chapter_index)

    def _on_chapter_thumbnail_loaded(self, index, pixmap):
        if index < len(self.chapter_thumbnail_widgets):
            self.chapter_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_chapter_selection(self, index):
        if self.current_chapter_thumbnail:
            self.current_chapter_thumbnail.set_selected(False)
        
        if index < len(self.chapter_thumbnail_widgets):
            self.current_chapter_thumbnail = self.chapter_thumbnail_widgets[index]
            self.current_chapter_thumbnail.set_selected(True)
            self.content_area.snapToItemIfOutOfView(index, self.current_chapter_thumbnail.width())

    def _change_chapter_by_thumbnail(self, index: int):
        self.on_chapter_changed(index + 1)