from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from PyQt6.QtGui import QPixmap
from src.utils.img_utils import is_image_folder, load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path, get_chapter_number

class ItemLoaderSignals(QObject):
    item_loaded = pyqtSignal(QPixmap, object, int, int, str)  # pix, path, idx, gen, item_type
    item_invalid = pyqtSignal(int, int)  # idx, gen
    loading_finished = pyqtSignal(int) # gen


class ItemLoader(QRunnable):
    """Load thumbnails for folders and images in a separate thread."""
    def __init__(self, items, generation):
        super().__init__()
        self.items = items
        self.generation = generation
        self.signals = ItemLoaderSignals()

    @staticmethod
    def _folder_is_valid(folder_path: Path) -> bool:
        """Checks if a folder contains images or subfolders with images (1 level deep)."""
        try:
            # Check for images in the folder itself
            if any(f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} for f in folder_path.iterdir()):
                return True

            # Check subfolders for images
            for subfolder in folder_path.iterdir():
                if subfolder.is_dir():
                    try:
                        if any(f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} for f in subfolder.iterdir()):
                            return True
                    except PermissionError:
                        continue
        except PermissionError:
            return False
        return False

    def run(self):
        from PyQt6.QtGui import QPixmap, QColor
        for idx, item_path in enumerate(self.items):
            item_type = ''
            pix = None
            
            if isinstance(item_path, str) and '|' in item_path:
                # Handle virtual paths
                item_type = 'image'
                # This function will be created in utils.py later
                pix = load_thumbnail_from_virtual_path(item_path, 150, 200)
            elif item_path.is_dir():
                if not ItemLoader._folder_is_valid(item_path):
                    self.signals.item_invalid.emit(idx, self.generation)
                    continue
                item_type = 'folder'
                try:
                    first_image = next(f for f in item_path.iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'})
                    if first_image:
                        pix = load_thumbnail_from_path(str(first_image), 150, 200)
                except (StopIteration, PermissionError):
                    pass
            elif item_path.is_file():
                if item_path.suffix.lower() == '.zip':
                    item_type = 'zip'
                    pix = load_thumbnail_from_zip(str(item_path), 150, 200)
                else:
                    item_type = 'image'
                    pix = load_thumbnail_from_path(str(item_path), 150, 200)

            if not pix:
                pix = QPixmap(150, 200)
                pix.fill(QColor("gray"))

            self.signals.item_loaded.emit(pix, item_path, idx, self.generation, item_type)
        
        self.signals.loading_finished.emit(self.generation)
