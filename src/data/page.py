from pathlib import Path
from typing import List

class Page:
    def __init__(self, images: List[str]):
        """
        Initialize a Page with a list of image paths (variants).
        The first image in the list is considered the 'default' variant initially.
        """
        self.images = images
        self.current_variant_index = 0

    @property
    def path(self) -> str:
        """Return the path of the currently active variant."""
        if 0 <= self.current_variant_index < len(self.images):
            return self.images[self.current_variant_index]
        return ""

    def set_variant(self, index: int):
        """Set the active variant index."""
        if 0 <= index < len(self.images):
            self.current_variant_index = index

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
