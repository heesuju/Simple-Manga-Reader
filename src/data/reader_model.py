from typing import List
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from src.enums import ViewMode
from src.utils.img_utils import get_chapter_number
from src.core.thumbnail_worker import get_default_view_mode

class ReaderModel(QObject):
    refreshed = pyqtSignal()
    image_loaded = pyqtSignal(str)
    double_image_loaded = pyqtSignal(str, str)
    layout_updated = pyqtSignal(ViewMode)

    def __init__(self, series: object, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None, language: str = 'ko'):
        super().__init__()
        
        self.series = series
        self.language = language
        self.start_file = start_file
        self.view_mode = ViewMode.SINGLE
        self.images: List[str] = images if images else []
        self.current_index = 0
        self.chapters = manga_dirs if manga_dirs else []
        self.chapter_index = index if manga_dirs else 0
        self.manga_dir = self.chapters[self.chapter_index] if manga_dirs else None

        if self.chapters:
            self.chapters = sorted(self.chapters, key=lambda x: get_chapter_number(str(x)))

    def refresh(self):
        """Should be called after model data is updated to refresh the view."""
        self.refreshed.emit()

    def _get_double_view_images(self, right_to_left:bool=True):
        new_images = list(self.images)
        i = 0

        result = [None] * len(new_images)
        
        if right_to_left:
            for i, val in enumerate(new_images):
                if i % 2 == 0:  # even
                    new_index = i + 1
                else:             # odd
                    new_index = i - 1
                
                if 0 <= new_index < len(new_images):  # avoid out-of-range
                    result[new_index] = val
                else:
                    result[i] = val

        return result

    def load_image(self):
        if not self.images or not (0 <= self.current_index < len(self.images)):
            return

        images = self.images
        if self.view_mode == ViewMode.DOUBLE:
            images = self._get_double_view_images()

        if self.view_mode == ViewMode.SINGLE:
            self.image_loaded.emit(images[self.current_index])
        elif self.view_mode == ViewMode.DOUBLE:
            pix1 = images[self.current_index]
            pix2 = images[self.current_index + 1] if self.current_index + 1 < len(images) else None
            self.double_image_loaded.emit(pix1, pix2)

    def change_page(self, page:int):
        if self.view_mode == ViewMode.DOUBLE and page % 2 == 0:
            page -=1

        index = page - 1            
        self.current_index = index
        self.load_image()

    def set_chapter(self, chapter:int) -> bool:
        index = chapter - 1
        total_chapters = len(self.chapters)
        
        if index < 0:
            index = 0
        elif index > total_chapters - 1:
            index = total_chapters - 1
        
        if self.chapter_index == index:
            return False

        self.chapter_index = index
        self.manga_dir = self.chapters[self.chapter_index]
        self.images = [] # force reload
        return True

    def change_chapter(self, direction: int) -> bool:
        new_index = self.chapter_index + direction
        total_chapters = len(self.chapters)

        if 0 <= new_index < total_chapters:
            if self.chapter_index == new_index:
                return False
            self.chapter_index = new_index
            self.manga_dir = self.chapters[self.chapter_index]
            self.images = []
            return True
        return False

    def toggle_layout(self, mode:ViewMode=None):
        if isinstance(mode, ViewMode):
            self.view_mode = mode
        elif self.view_mode.value + 1 < len(list(ViewMode)):
            self.view_mode = ViewMode(self.view_mode.value + 1)
        else:
            self.view_mode = ViewMode(0)

        self.update_layout()

    def update_layout(self):
        self.load_image()
        self.layout_updated.emit(self.view_mode)
