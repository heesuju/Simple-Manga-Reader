from typing import List
from pathlib import Path
import zipfile
import math

from PyQt6.QtCore import QObject, pyqtSignal

from src.enums import ViewMode
from src.utils.img_utils import get_chapter_number, get_image_size
from src.core.thumbnail_worker import get_default_view_mode, get_common_size_ratio, get_image_ratio

def is_double_page(size, common_ratio):
    if size[0] == 0 or size[1] == 0:
        return False
    ratio = get_image_ratio(size[0]/2, size[1])

    if math.isclose(ratio, common_ratio):
        return True
    else:
        return False


class ReaderModel(QObject):
    refreshed = pyqtSignal()
    image_loaded = pyqtSignal(str)
    double_image_loaded = pyqtSignal(str, str)
    layout_updated = pyqtSignal(ViewMode)

    def __init__(self, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None, language: str = 'ko'):
        super().__init__()
        
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

    def refresh(self, start_from_end:bool=False, preserve_view_mode:bool=False):
        if not self.images:
            self.images = self._get_image_list()
            self.images = sorted(self.images, key=get_chapter_number)

            # Split wide images
            common_size, ratio, _, _ = get_common_size_ratio(self.images)
            if common_size[0] > 0:
                new_items = []
                for item in self.images:
                    size = get_image_size(item)
                    
                    if is_double_page(size, ratio):
                        new_items.append(str(item) + "_right")
                        new_items.append(str(item) + "_left")
                    else:
                        new_items.append(item)
                self.images = new_items
        
        if not preserve_view_mode:
            self.view_mode = get_default_view_mode(self.images)

        if hasattr(self, 'start_file') and self.start_file:
            try:
                self.current_index = self.images.index(self.start_file)
            except (ValueError, IndexError):
                self.current_index = 0
            self.start_file = None
        elif start_from_end:
            self.current_index = len(self.images) - 1
        else:
            self.current_index = 0

        self.refreshed.emit()

        if self.images:
            self.load_image()

    def _get_image_list(self):
        if isinstance(self.manga_dir, str) and self.manga_dir.endswith('.zip'):
            try:
                with zipfile.ZipFile(self.manga_dir, 'r') as zf:
                    image_files = sorted([f for f in zf.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')) and not f.startswith('__MACOSX')])
                    return [f"{self.manga_dir}|{name}" for name in image_files]
            except zipfile.BadZipFile:
                return []
        elif isinstance(self.manga_dir, Path) and self.manga_dir.is_dir():
            exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
            return [str(p) for p in sorted(self.manga_dir.iterdir()) if p.suffix.lower() in exts and p.is_file()]
        return []

    def _get_double_view_images(self, right_to_left:bool=True):
        new_images = list(self.images)
        i = 0
        last_pair_end = -1
        while i < len(new_images):
            img = new_images[i]
            if str(img).endswith("_right"):
                if i % 2 != 0:
                    if last_pair_end == -1:
                        new_images.insert(0, "placeholder")
                    else:
                        new_images.insert(last_pair_end + 1, "placeholder")
                    i += 1 # we inserted an element, so we need to increment i to continue from the same image in the next iteration
                    continue
                last_pair_end = i + 1
            i += 1
        
        if len(new_images) % 2 != 0:
            new_images.append("placeholder")

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

    def change_chapter(self, chapter:int):
        index = chapter - 1
        total_chapters = len(self.chapters)
        
        if index < 0:
            index = 0
        elif index > total_chapters - 1:
            index = total_chapters - 1
        
        self.chapter_index = index
        self.manga_dir = self.chapters[self.chapter_index]
        self.images = [] # force reload
        self.refresh(preserve_view_mode=True)

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
