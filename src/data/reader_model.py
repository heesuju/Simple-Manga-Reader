from typing import List, Union
from pathlib import Path
import os
import random
from PyQt6.QtGui import QImageReader

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
        
        # Double Mode Virtual Layout Logic
        self._layout_pairs = [] 
        self._page_to_layout_index = {} # Maps Real Page Index -> Layout Index

        self.current_index = 0
        self.chapters = manga_dirs if manga_dirs else []
        self.chapter_index = index if manga_dirs else 0
        self.manga_dir = self.chapters[self.chapter_index] if manga_dirs else None
        self.preferred_language = None 

        if self.chapters:
            self.chapters = sorted(self.chapters, key=lambda x: get_chapter_number(str(x)))

        if images:
            self.set_images(images)

    def set_images(self, images: List[Union[str, Page]]):
        """
        Set images. 
        Accepts either raw paths (strings) or already grouped Page objects.
        """
        if not images:
            self.images = []
            self._layout_pairs = []
            return

        # Check if first item is Page object
        if isinstance(images[0], Page):
            self.images = images
        else:
            # Legacy/Fallback
            if not self.series or not self.manga_dir:
                self.images = [Page([path]) for path in images]
            else:
                chapter_name = Path(self.manga_dir).name
                alt_config = AltManager.load_alts(str(self.series['path']))
                chapter_alts = alt_config.get(chapter_name, {})
                self.images = AltManager.group_images(images, chapter_alts)
        
        # Build Map
        self._rebuild_map()

        # Auto-detect spreads
        self.auto_detect_spreads()
        
        # Build Layout (Initial)
        self._build_double_layout()

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
        self._build_double_layout()
        self.refreshed.emit()

    def set_preferred_language(self, lang: Union[str, None]):
        """Set the preferred language for display and apply to all pages."""
        self.preferred_language = lang
        
        # Apply to ALL pages immediately
        for page in self.images:
            if self.preferred_language and self.preferred_language in page.translations:
                 page.set_translation(self.preferred_language)
            elif self.preferred_language is None:
                 page.clear_translation()
            elif self.preferred_language and self.preferred_language not in page.translations:
                 # Preference set but translation missing -> revert to original
                 page.clear_translation()

        self.refresh() # Trigger full reload

    def _build_double_layout(self):
        """
        Builds the virtual layout for double page view.
        Spreads take a full slot. Non-spreads are paired (Right, Left) for RTL.
        Orphans are paired with "placeholder".
        """
        self._layout_pairs = []
        self._page_to_layout_index = {}
        
        if not self.images:
            return

        buffer = [] # Holds single pages ((index, page)) waiting for a pair
        
        for i, page in enumerate(self.images):
            if page.is_spread:
                if buffer:
                    # Flush orphan (Preceding) -> Right side (First slot)
                    # Pair with Placeholder on Left
                    # Pair: ("placeholder", OrphanPage) [Left, Right] logic? 
                    # Existing ReaderView: item2 (Right) is loaded from pair[1]?
                    # Let's check ReaderModel._load_double_images usage later. 
                    # Usually RTL: [Left=Next, Right=Curr]. 
                    # If orphan is 'Right' (First), then Left is 'Placeholder'.
                    orphan_idx, orphan_page = buffer.pop(0)
                    pair = ("placeholder", orphan_page)
                    self._layout_pairs.append(pair)
                    self._page_to_layout_index[orphan_idx] = len(self._layout_pairs) - 1
                
                # Add Spread (Spread, None)
                pair = (page, None)
                self._layout_pairs.append(pair)
                self._page_to_layout_index[i] = len(self._layout_pairs) - 1
                
            else:
                if buffer:
                    # We have a partner.
                    # Current (i) is logically AFTER Preceding.
                    # RTL: [Left=Current, Right=Preceding]
                    pre_idx, pre_page = buffer.pop(0)
                    pair = (page, pre_page)
                    self._layout_pairs.append(pair)
                    self._page_to_layout_index[i] = len(self._layout_pairs) - 1
                    self._page_to_layout_index[pre_idx] = len(self._layout_pairs) - 1
                else:
                    buffer.append((i, page))
                    
        if buffer:
            # Trailing orphan -> Right side?
            # If [P1, P2, P3]. P3 is alone. P3 is Right. Left is Ph.
            orphan_idx, orphan_page = buffer.pop(0)
            pair = ("placeholder", orphan_page)
            self._layout_pairs.append(pair)
            self._page_to_layout_index[orphan_idx] = len(self._layout_pairs) - 1

    def _get_current_layout_index(self) -> int:
        if not self._layout_pairs: return -1
        return self._page_to_layout_index.get(self.current_index, 0)

    def load_image(self):
        if not self.images:
            return

        # Ensure index range
        if not (0 <= self.current_index < len(self.images)):
             self.current_index = max(0, min(self.current_index, len(self.images) - 1))

        if self.view_mode == ViewMode.SINGLE:
            page = self.images[self.current_index]
            self.image_loaded.emit(page.path)
            
        elif self.view_mode == ViewMode.DOUBLE:
            layout_idx = self._get_current_layout_index()
            if layout_idx == -1 or layout_idx >= len(self._layout_pairs): 
                # Fallback
                self.view_mode = ViewMode.SINGLE
                self.load_image()
                return
                
            left_item, right_item = self._layout_pairs[layout_idx]
            
            # Handling Spreads (Spread, None)
            if isinstance(left_item, Page) and left_item.is_spread: 
                # Reuse Single View logic for Spreads to center them
                self.image_loaded.emit(left_item.path)
                return

            # Normal Pair or Placeholder
            l_path = "placeholder"
            if isinstance(left_item, Page):
                l_path = left_item.path
            
            r_path = "placeholder"
            if isinstance(right_item, Page):
                r_path = right_item.path
                
            self.double_image_loaded.emit(l_path, r_path)

    def auto_detect_spreads(self):
        """
        Detects double-page spreads based on aspect ratio.
        """
        if not self.series or not self.manga_dir or not self.images:
            return

        # 1. Detect if "Manga" (consistent aspect ratio)
        # Sample random 5 pages from middle 50%
        valid_indices = range(len(self.images))
        if len(self.images) > 10:
             start = len(self.images) // 4
             end = len(self.images) * 3 // 4
             valid_indices = range(start, end)
        
        # Taking up to 5 samples
        sample_indices = random.sample(valid_indices, min(5, len(valid_indices)))
        ratios = []
        
        for i in sample_indices:
             path = self.images[i].path
             reader = QImageReader(path)
             size = reader.size()
             if size.isValid() and size.height() > 0:
                 ratios.append(size.width() / size.height())
        
        if not ratios:
            return

        median_ratio = sorted(ratios)[len(ratios) // 2]
        
        # Check consistency (all within 10% of median)
        if median_ratio == 0: return

        is_consistent = all(abs(r - median_ratio) / median_ratio < 0.1 for r in ratios)
        
        if not is_consistent:
            return
            
        # 2. Detect spreads
        common_ratio = median_ratio
        # Spread is roughly double the width, so ratio should be ~2x common_ratio
        # We use a threshold, e.g., > 1.5x
        spread_threshold = common_ratio * 1.5 
        
        updates = {}
        chapter_name = Path(self.manga_dir).name
        
        for page in self.images:
            # Skip if user explicitly set it (loaded from config as explicit) or manually handled
            if page.is_spread_explicit:
                continue
                
            path = page.path
            reader = QImageReader(path)
            size = reader.size()
            
            if size.isValid() and size.height() > 0:
                 ratio = size.width() / size.height()
                 
                 is_spread = ratio > spread_threshold
                 
                 if page.is_spread != is_spread:
                     page.is_spread = is_spread
                     updates[path] = is_spread
        
        # 3. Save updates
        if updates:
             AltManager.save_spread_states(str(self.series['path']), chapter_name, updates)
             self.refresh()

    def navigate(self, direction: int) -> bool:
        """
        Smart navigation respecting view modes and layouts.
        Returns True if navigation succeeded within chapter, False if boundary reached.
        """
        if self.view_mode == ViewMode.SINGLE or self.view_mode == ViewMode.STRIP:
             new_index = self.current_index + direction
             if 0 <= new_index < len(self.images):
                 self.current_index = new_index
                 self.load_image()
                 return True
             else:
                 return False # Boundary
        
        elif self.view_mode == ViewMode.DOUBLE:
             current_layout = self._get_current_layout_index()
             new_layout = current_layout + direction
             
             if 0 <= new_layout < len(self._layout_pairs):
                 left, right = self._layout_pairs[new_layout]
                 
                 candidate = None
                 # Prefer Right (First logical) page.
                 if right and isinstance(right, Page):
                      candidate = right
                 elif left and isinstance(left, Page):
                      candidate = left
                      
                 if candidate:
                      try:
                          idx = self.images.index(candidate)
                          self.current_index = idx
                          self.load_image()
                          return True
                      except ValueError:
                          pass 
                          
             return False # Boundary
 
    def change_variant(self, page_index: int, variant_index: int):
        if 0 <= page_index < len(self.images):
            self.images[page_index].set_variant(variant_index)
            self.page_updated.emit(page_index) # Notify valid update
            
            # If the changed page is the current one, reload
            # In double mode, we check logic.
            # Ideally we check if page_index is in current layout pair.
            # Checking abs diff is 'okay' approximation but let's be safe.
            should_reload = False
            if page_index == self.current_index:
                should_reload = True
            elif self.view_mode == ViewMode.DOUBLE:
                # Check if visible
                layout_idx = self._get_current_layout_index()
                if 0 <= layout_idx < len(self._layout_pairs):
                    pair = self._layout_pairs[layout_idx]
                    # Check if page is in pair
                    # pair is (Item, Item). Item is Page or None or "placeholder"
                    # We need to compare PAGE INSTANCES or indices.
                    # We only have Page Instance reference in pair.
                    target_page = self.images[page_index]
                    if pair[0] == target_page or pair[1] == target_page:
                         should_reload = True
            
            if should_reload:
                self.load_image()

    def cycle_variant(self, page_index: int):
        if 0 <= page_index < len(self.images):
            page = self.images[page_index]
            if len(page.images) > 1:
                next_variant = (page.current_variant_index + 1) % len(page.images)
                self.change_variant(page_index, next_variant)

    def change_page(self, page:int):
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
