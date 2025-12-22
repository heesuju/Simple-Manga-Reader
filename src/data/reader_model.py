from typing import List, Union
from pathlib import Path
import os


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
    page_updated = pyqtSignal(int)

    def __init__(self, series: object, manga_dirs: List[object], index:int, start_file: str = None, images: List[str] = None, language: str = 'ko'):
        super().__init__()
        
        self.series = series
        self.language = language
        self.start_file = start_file
        self.view_mode = ViewMode.SINGLE
        self.images: List[Page] = [] 
        self._image_map = {} # Maps image path -> page_index
        self.current_index = 0
        self.chapters = manga_dirs if manga_dirs else []
        self.chapter_index = index if manga_dirs else 0
        self.manga_dir = self.chapters[self.chapter_index] if manga_dirs else None
        self.preferred_language = None # Stores global language preference (e.g. "ENG")

        if self.chapters:
            self.chapters = sorted(self.chapters, key=lambda x: get_chapter_number(str(x)))

        if images:
            self.set_images(images)

    def set_images(self, images: List[Union[str, Page]]):
        """
        Set images. Accepts either raw paths (strings) or already grouped Page objects.
        """
        if not images:
            self.images = []
            return

        # Check if first item is Page object
        if isinstance(images[0], Page):
            self.images = images
            return

        # Legacy/Fallback: Group raw image paths into Page objects
        if not self.series or not self.manga_dir:
            self.images = [Page([path]) for path in images]
            return

        chapter_name = Path(self.manga_dir).name
        alt_config = AltManager.load_alts(str(self.series['path']))
        chapter_alts = alt_config.get(chapter_name, {})
        self.images = AltManager.group_images(images, chapter_alts)
        
        # Build Map
        self._rebuild_map()

    def _rebuild_map(self):
        """Rebuild the hash map for O(1) lookup."""
        self._image_map.clear()
        for i, page in enumerate(self.images):
            # Map variants using normalized path
            for img_path in page.images:
                 norm = os.path.normpath(img_path)
                 self._image_map[norm] = i

    def get_page_index(self, path: str) -> int:
        """O(1) lookup for page index given a path."""
        norm_path = os.path.normpath(path)
        return self._image_map.get(norm_path, -1)

    def refresh(self):
        """Should be called after model data is updated to refresh the view."""
        self.refreshed.emit()

    def set_preferred_language(self, lang: Union[str, None]):
        """Set the preferred language for display. None means 'Original'."""
        self.preferred_language = lang
        self.load_image() # Reload to apply preference

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
            
            # Apply preference
            if self.preferred_language and self.preferred_language in page.translations:
                 page.set_translation(self.preferred_language)
            elif self.preferred_language is None:
                 page.clear_translation()
            # If preference is set but translation missing, we keep it cleared (Original)
            # effectively logic: if desired TL exists, show it. Else show original.
            if self.preferred_language and self.preferred_language not in page.translations:
                 page.clear_translation()
            
            self.image_loaded.emit(page.path)
        elif self.view_mode == ViewMode.DOUBLE:
            page1 = images[self.current_index]
            page2 = images[self.current_index + 1] if self.current_index + 1 < len(images) else None
            
            p1_path = page1.path if page1 else None
            p2_path = page2.path if page2 else None
            
            # Apply preference for Double View as well
            for p in [page1, page2]:
                if p:
                    if self.preferred_language and self.preferred_language in p.translations:
                        p.set_translation(self.preferred_language)
                    elif self.preferred_language is None:
                        p.clear_translation()
                    elif self.preferred_language and self.preferred_language not in p.translations:
                        p.clear_translation()
            
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

    def cycle_variant(self, page_index: int):
        if 0 <= page_index < len(self.images):
            page = self.images[page_index]
            if len(page.images) > 1:
                next_variant = (page.current_variant_index + 1) % len(page.images)
                self.change_variant(page_index, next_variant)

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

        # If switching TO Double mode, ensure snapping to the start of a pair
        if self.view_mode == ViewMode.DOUBLE:
             if self.current_index % 2 != 0:
                 self.current_index -= 1

        self.update_layout()

    def update_layout(self):
        self.load_image()
        self.layout_updated.emit(self.view_mode)

    def update_page_variants(self, page_index: int):
        """
        Refreshes the variants for the page at page_index from the disk/config.
        This is used when alts are added/removed externally or unlinked.
        """
        if not (0 <= page_index < len(self.images)):
            return

        page = self.images[page_index]
        if not page.images:
            return

        # The main file (key) for this page group
        main_file = page.images[0]
        chapter_name = Path(self.manga_dir).name
        alt_config = AltManager.load_alts(str(self.series['path']))
        
        # 1. Re-build the variants list for just this page
        # Logic similar to group_images but focused on one main file
        new_variants = [main_file]
        main_name = Path(main_file).name
        
        # Save current path to restore selection
        current_variant_path = page.path

        chapter_alts = alt_config.get(chapter_name, {})
        
        if main_name in chapter_alts:
            # We need to resolve paths. We don't have the full list of all files to map from name -> path easily 
            # unless we scan or just assume they are in the same dir or alts dir.
            # However, usually alts are in 'alts/' folder or same folder.
            # Existing Page object has paths. 
            # But we might have ADDED a new file which is not in Page object yet.
            
            # We can construct paths.
            # If the alt config has names, we check if they exist in alts dir or main dir.
            
            entry = chapter_alts[main_name]
            alt_names = []
            translations = {}
            
            # Handle List (Legacy) vs Dict (New)
            if isinstance(entry, list):
                alt_names = entry
            elif isinstance(entry, dict):
                # Add alts
                if "alts" in entry and isinstance(entry["alts"], list):
                    alt_names.extend(entry["alts"])
                    
                # Add translations
                if "translations" in entry and isinstance(entry["translations"], dict):
                    # We need to resolve paths for translations too
                    trans_dict = entry["translations"]
                    # We will resolve them in the loop below or separately
                    # Let's verify existence separately to keep logic clean or reuse loop
                    # Actually, reuse loop logic is tricky because we need key->path mapping for translations
                    pass

            found_alts = []
            
            # Strategy: Check 'alts' and 'translations' subdirectories (if we want to be robust), 
            # as well as the chapter folder itself.
            chapter_dir = Path(self.manga_dir)
            possible_dirs = [chapter_dir / "alts", chapter_dir / "translations", chapter_dir]
            
            # Resolve Alts
            for alt_name in alt_names:
                for d in possible_dirs:
                    candidate = d / alt_name
                    if candidate.exists():
                        found_alts.append(str(candidate))
                        break
            
             # Resolve Translations (if any)
            if isinstance(entry, dict) and "translations" in entry and isinstance(entry["translations"], dict):
                 for lang_key, trans_file in entry["translations"].items():
                     # Check direct match in possible_dirs
                     found = False
                     for d in possible_dirs:
                         candidate = d / trans_file
                         if candidate.exists():
                             translations[lang_key] = str(candidate)
                             found = True
                             break
                     
                     if not found:
                         # Check internal structure: translations/LANG/file
                         candidate = chapter_dir / "translations" / lang_key / trans_file
                         if candidate.exists():
                             translations[lang_key] = str(candidate)

            # Sort alts (re-use sort logic if possible, or duplicate for now as it's small)
            ANIM_EXTS = {'.gif'}
            VIDEO_EXTS = {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
            def get_priority(path_str):
                suffix = Path(path_str).suffix.lower()
                if suffix in VIDEO_EXTS: return 2
                if suffix in ANIM_EXTS: return 1
                return 0 # Image
            
            found_alts.sort(key=lambda p: (get_priority(p), Path(p).suffix.lower(), Path(p).name.lower()))
            new_variants.extend(found_alts)

        # 2. Update the Page object
        page.images = new_variants
        page.translations = translations
        
        # Restore selection
        # Normalize paths for comparison just in case
        try:
            # Find index of current_variant_path in new_variants
            # We use simple string match as they should be same absolute paths
            new_index = new_variants.index(current_variant_path)
            page.current_variant_index = new_index
        except ValueError:
            # If path lost (e.g. unlinked), default to 0
            page.current_variant_index = 0
        
        # 3. Update Map for this page
        # Remove old entries for this page? 
        # Easier to just rebuild map logic or update partially
        # Since variants changed, we should ideally remove old variants pointing to this index 
        # and add new ones.
        # For simplicity, we can just re-add new ones. 
        # (Assuming distinct pages don't share files, which they shouldn't).
        for var in new_variants:
            self._image_map[os.path.normpath(var)] = page_index
        
        # 4. Emit signal
        self.page_updated.emit(page_index)
