from pathlib import Path
from typing import List

class Page:
    def __init__(self, images: List[str], translations: dict = None):
        """
        Initialize a Page with a list of image paths (variants).
        The first image in the list is considered the 'default' variant initially.
        translations: Dict[str, str] mapping language code -> file path.
        """
        self.images = images
        self.translations = translations if translations else {}
        self.current_variant_index = 0
        self.active_translation_lang = None # Language code if showing translation
        self.is_spread = False # If true, this page should be treated as a double-page spread
        self.is_spread_explicit = False # If true, is_spread was set from config (don't auto-detect)

    @property
    def path(self) -> str:
        """Return the path of the currently active image (variant or translation)."""
        # If showing translation, return translation path
        if self.active_translation_lang and self.active_translation_lang in self.translations:
            return self.translations[self.active_translation_lang]
            
        # Otherwise return current variant
        if 0 <= self.current_variant_index < len(self.images):
            return self.images[self.current_variant_index]
        return ""

    def set_variant(self, index: int):
        """Set the active variant index and disable translation view."""
        if 0 <= index < len(self.images):
            self.current_variant_index = index
            self.active_translation_lang = None

    def add_variant(self, path: str):
        """Add a new variant path."""
        if path not in self.images:
            self.images.append(path)

    def remove_variant(self, path: str):
        """Remove a variant path. Cannot remove the last image."""
        if path in self.images and len(self.images) > 1:
            if self.images[self.current_variant_index] == path:
                self.current_variant_index = 0 # Reset to 0 if current is removed
            self.images.remove(path)
            
    def set_translation(self, lang: str):
        """Switch to showing a translation."""
        if lang in self.translations:
            self.active_translation_lang = lang
            
    def clear_translation(self):
        """Revert to showing the active variant."""
        self.active_translation_lang = None
        
    def is_showing_translation(self) -> bool:
        return self.active_translation_lang is not None

    def get_categorized_variants(self) -> dict:
        """Groups variant paths by category (label)."""
        categories = {}
        for i, path in enumerate(self.images):
            p = Path(path)
            cat = None
            
            # The original page (index 0) is always the "Main" category, regardless of its filename text
            if i == 0:
                cat = "Main"
            else:
                # Check if it was saved in a category subdirectory: alts/main_page/category_name/file
                if 'alts' in p.parts:
                    try:
                        alts_idx = p.parts.index('alts')
                        # Expecting structure: .../alts/<main_file>/<category>/<file>
                        if len(p.parts) > alts_idx + 3:
                            cat = p.parts[alts_idx + 2].lower()
                        # Fallback for old structure: .../alts/<category>/<file>
                        elif len(p.parts) > alts_idx + 2:
                            cat = p.parts[alts_idx + 1].lower()
                    except ValueError:
                        pass
                
                # If no subdirectory category could be found, fallback to regex on filename
                if not cat:
                    name = p.stem
                    import re
                    # Match letters AND spaces as group 1, then optional trailing space/underscore/dash, then numbers
                    m = re.match(r'^([a-zA-Z\s]+?)[_\-\s]?\d*$', name)
                    if m and m.group(1).strip():
                        cat = m.group(1).strip().lower()
                    else:
                        cat = "Main"
                
                # Normalize "main" to "Main"
                if cat and cat.lower() == "main":
                    cat = "Main"
                
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(path)
            
        return categories
