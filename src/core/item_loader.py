import os
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
    def __init__(self, items, generation, item_type='file', thumb_width=150, thumb_height=200, root_dir=None):
        super().__init__()
        self.items = items
        self.generation = generation
        self.signals = ItemLoaderSignals()
        self.item_type = item_type
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.root_dir = root_dir

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
        for idx, item in enumerate(self.items):
            item_type = ''
            pix = None
            item_path = item

            if self.item_type == 'series':
                item_type = 'series'
                cover_image = item.get('cover_image')
                if cover_image:
                    pix = load_thumbnail_from_path(cover_image, self.thumb_width, self.thumb_height)
            elif self.item_type == 'chapter':
                item_type = 'chapter'
                chapter_path = item['path']
                thumbnail_path = None
                
                cover_path = Path(chapter_path) / 'cover.png' 
                if not cover_path.exists(): 
                    cover_path = Path(chapter_path) / 'cover.jpg'
                
                if cover_path.exists():
                    thumbnail_path = str(cover_path)
                else:
                    try:
                        first_image = next(f for f in Path(chapter_path).iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'})
                        if first_image:
                            thumbnail_path = str(first_image)
                    except (StopIteration, PermissionError):
                        pass
                
                if thumbnail_path:
                    pix = load_thumbnail_from_path(thumbnail_path, self.thumb_width, self.thumb_height)
            else:
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
                    pix = load_thumbnail_from_virtual_path(path_str, self.thumb_width, self.thumb_height, crop)
                elif Path(path_str).is_dir():
                    if not ItemLoader._folder_is_valid(Path(path_str)):
                        self.signals.item_invalid.emit(idx, self.generation)
                        continue
                    item_type = 'folder'
                    try:
                        first_image = next(f for f in Path(path_str).iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'})
                        if first_image:
                            pix = load_thumbnail_from_path(str(first_image), self.thumb_width, self.thumb_height)
                    except (StopIteration, PermissionError):
                        pass
                elif Path(path_str).is_file():
                    if Path(path_str).suffix.lower() == '.zip':
                        item_type = 'zip'
                        pix = load_thumbnail_from_zip(path_str, self.thumb_width, self.thumb_height)
                    else:
                        item_type = 'image'
                        pix = load_thumbnail_from_path(path_str, self.thumb_width, self.thumb_height, crop)

            if not pix:
                pix = QPixmap(self.thumb_width, self.thumb_height)
                pix.fill(QColor("gray"))

            self.signals.item_loaded.emit(pix, item, idx, self.generation, item_type)
        
        self.signals.loading_finished.emit(self.generation)
