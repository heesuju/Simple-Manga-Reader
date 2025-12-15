from typing import List
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from src.enums import ViewMode
from src.utils.img_utils import get_chapter_number
from src.core.thumbnail_worker import get_default_view_mode
from src.data.page import Page
from src.core.alt_manager import AltManager

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
        self.images: List[Page] = [] 
        self.current_index = 0
        self.chapters = manga_dirs if manga_dirs else []
        self.chapter_index = index if manga_dirs else 0
        self.manga_dir = self.chapters[self.chapter_index] if manga_dirs else None

        if self.chapters:
            self.chapters = sorted(self.chapters, key=lambda x: get_chapter_number(str(x)))

        if images:
            self.set_images(images)

    def set_images(self, image_paths: List[str]):
        """
        Group raw image paths into Page objects based on info.json configurations.
        """
        if not self.series or not self.manga_dir:
            self.images = [Page([path]) for path in image_paths]
            return

        chapter_name = Path(self.manga_dir).name
        alt_config = AltManager.load_alts(str(self.series['path']))
        chapter_alts = alt_config.get(chapter_name, {})

        grouped_pages = []
        processed_files = set()
        
        # Map filenames to full paths for easy lookup
        path_map = {Path(p).name: p for p in image_paths}

        # Collect all subsidiary files (alts) to know what to skip
        subsidiary_files = set()
        for alts_list in chapter_alts.values():
            for alt_name in alts_list:
                subsidiary_files.add(alt_name)

        for path in image_paths:
            name = Path(path).name
            
            # If this file is a known alternate of another file, skip it.
            # It will be picked up when we find its 'Main' file.
            # Exception: If the Main file is missing from path_map, we might want to show this one?
            # Current logic: If name is in subsidiary_files, it means it is listed as an alt.
            
            if name in subsidiary_files:
                continue
                
            if name in processed_files:
                continue

            variants = [path]
            processed_files.add(name)

            # Check if this image has alts configured
            if name in chapter_alts:
                for alt_name in chapter_alts[name]:
                    if alt_name in path_map:
                        variants.append(path_map[alt_name])
                        processed_files.add(alt_name)
            
            grouped_pages.append(Page(variants))
        
        self.images = grouped_pages

    def refresh(self):
        """Should be called after model data is updated to refresh the view."""
        self.refreshed.emit()

    def _get_double_view_images(self, right_to_left:bool=True) -> List[Page]:
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
            page = images[self.current_index]
            self.image_loaded.emit(page.path)
        elif self.view_mode == ViewMode.DOUBLE:
            page1 = images[self.current_index]
            page2 = images[self.current_index + 1] if self.current_index + 1 < len(images) else None
            
            p1_path = page1.path if page1 else None
            p2_path = page2.path if page2 else None
            self.double_image_loaded.emit(p1_path, p2_path)

    def change_variant(self, page_index: int, variant_index: int):
        if 0 <= page_index < len(self.images):
            self.images[page_index].set_variant(variant_index)
            # If the changed page is the current one, reload
            if page_index == self.current_index or \
               (self.view_mode == ViewMode.DOUBLE and abs(page_index - self.current_index) <= 1):
                self.load_image()

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
