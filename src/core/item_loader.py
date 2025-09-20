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
            
            path_str = str(item_path)
            crop = None
            if path_str.endswith("_left"):
                path_str = path_str[:-5]
                crop = "left"
            elif path_str.endswith("_right"):
                path_str = path_str[:-6]
                crop = "right"

            if '|' in path_str:
                # Handle virtual paths
                item_type = 'image'
                pix = load_thumbnail_from_virtual_path(path_str, 150, 200, crop)
            elif Path(path_str).is_dir():
                if not ItemLoader._folder_is_valid(Path(path_str)):
                    self.signals.item_invalid.emit(idx, self.generation)
                    continue
                item_type = 'folder'
                try:
                    first_image = next(f for f in Path(path_str).iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'})
                    if first_image:
                        pix = load_thumbnail_from_path(str(first_image), 150, 200)
                except (StopIteration, PermissionError):
                    pass
            elif Path(path_str).is_file():
                if Path(path_str).suffix.lower() == '.zip':
                    item_type = 'zip'
                    pix = load_thumbnail_from_zip(path_str, 150, 200)
                else:
                    item_type = 'image'
                    pix = load_thumbnail_from_path(path_str, 150, 200, crop)

            if not pix:
                pix = QPixmap(150, 200)
                pix.fill(QColor("gray"))

            self.signals.item_loaded.emit(pix, item_path, idx, self.generation, item_type)
        
        self.signals.loading_finished.emit(self.generation)
