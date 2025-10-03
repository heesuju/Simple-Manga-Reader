from typing import List
from pathlib import Path

from PyQt6.QtCore import QThreadPool, pyqtSignal, QRunnable, QObject
from PyQt6.QtWidgets import QPushButton
from src.ui.collapsible_panel import CollapsiblePanel
from src.ui.page_thumbnail import PageThumbnail
from src.core.thumbnail_worker import ThumbnailWorker
from src.utils.img_utils import _get_first_image_path, draw_text_on_image, load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.data.reader_model import ReaderModel
from src.utils.ocr_utils import OCR_SINGLETON
from src.utils.text_utils import group_text_by_proximity
from src.utils.translation_utils import translate_texts
import cv2


class BulkTranslationWorkerSignals(QObject):
    finished = pyqtSignal(list)


class BulkTranslationWorker(QRunnable):
    def __init__(self, texts):
        super().__init__()
        self.texts = texts
        self.signals = BulkTranslationWorkerSignals()

    def run(self):
        translated_texts = translate_texts(self.texts)
        self.signals.finished.emit(translated_texts)


class ChapterPanel(CollapsiblePanel):
    translation_ready = pyqtSignal(object)

    def __init__(self, parent=None, model:ReaderModel=None, on_chapter_changed=None):
        super().__init__(parent, "Chapter")
        self.model = model
        self.thread_pool = QThreadPool()
        self.on_chapter_changed = on_chapter_changed
        self.chapter_thumbnail_widgets = []
        self.current_chapter_thumbnail = None
        self.grouped_text_with_boxes = []
        self.modified_image = None
        self.input_label.enterPressed.connect(self.on_chapter_changed)

        self.translate_button = QPushButton("Translate")
        self.translate_button.clicked.connect(self._translate_current_page)
        self.add_control_widget(self.translate_button)

    def _load_thumbnail(self, path):
        if '|' in path:
            return load_thumbnail_from_virtual_path(path, 150, 200)
        else:
            return load_thumbnail_from_path(path, 150, 200)
    
    def _update_chapter_thumbnails(self, chapters:List[object]):
        for i in reversed(range(self.thumbnails_layout.count() - 1)):
            self.thumbnails_layout.itemAt(i).widget().setParent(None)
        self.chapter_thumbnail_widgets.clear()

        for i, chapter in enumerate(chapters):
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

    def _on_chapter_thumbnail_loaded(self, index, pixmap):
        if index < len(self.chapter_thumbnail_widgets):
            self.chapter_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_chapter_selection(self, index):
        if self.current_chapter_thumbnail:
            self.current_chapter_thumbnail.set_selected(False)
        
        if index < len(self.chapter_thumbnail_widgets):
            self.current_chapter_thumbnail = self.chapter_thumbnail_widgets[index]
            self.current_chapter_thumbnail.set_selected(True)
            self.content_area.snapToItem(index)

        self.input_label.set_total(len(self.chapter_thumbnail_widgets))
        self.input_label.set_value(index+1)

    def _change_chapter_by_thumbnail(self, index: int):
        self.on_chapter_changed(index + 1)

    def _translate_current_page(self):
        if not self.model or not self.model.images:
            return

        current_image_path = self.model.images[self.model.current_index]
        if '|' in current_image_path:
            print("OCR for images in zip files is not supported yet.")
            return

        print(f"Translating {current_image_path}...")
        
        # Load image with OpenCV
        image = cv2.imread(current_image_path)
        if image is None:
            print(f"Could not load image: {current_image_path}")
            return

        # Perform OCR
        ocr_result = OCR_SINGLETON.read_text(current_image_path)
        
        # Group text
        self.grouped_text_with_boxes = group_text_by_proximity(ocr_result)

        if not self.grouped_text_with_boxes:
            self.translation_ready.emit(image) # Emit original image if no text
            return

        self.modified_image = image.copy()

        texts_to_translate = [text for text, box in self.grouped_text_with_boxes]
        
        worker = BulkTranslationWorker(texts_to_translate)
        worker.signals.finished.connect(self._on_bulk_translation_finished)
        self.thread_pool.start(worker)

    def _on_bulk_translation_finished(self, translated_texts):
        if len(translated_texts) != len(self.grouped_text_with_boxes):
            print("Error: Number of translations does not match number of text boxes.")
            self.translation_ready.emit(self.modified_image)
            return

        for i, translated_text in enumerate(translated_texts):
            original_text, box = self.grouped_text_with_boxes[i]
            print(f"{original_text} -> {translated_text}")
            self.modified_image = draw_text_on_image(self.modified_image, translated_text, box)
        
        self.translation_ready.emit(self.modified_image)