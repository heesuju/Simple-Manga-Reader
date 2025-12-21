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
