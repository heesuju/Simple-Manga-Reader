import os
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from PyQt6.QtGui import QPixmap, QImage
from src.utils.img_utils import is_image_folder, load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path, get_chapter_number, is_image_monotone

class ItemLoaderSignals(QObject):
    item_loaded = pyqtSignal(QImage, object, int, int, str)  # qimg, path, idx, gen, item_type
    item_invalid = pyqtSignal(int, int)  # idx, gen
    loading_finished = pyqtSignal(int) # gen


class ItemLoader(QRunnable):
    """Load thumbnails for folders and images in a separate thread."""
    def __init__(self, items, generation, item_type='file', thumb_width=150, thumb_height=200, root_dir=None, library_manager=None):
        super().__init__()
        self.items = items
        self.generation = generation
        self.signals = ItemLoaderSignals()
        self.item_type = item_type
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.root_dir = root_dir
        self.library_manager = library_manager
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    @staticmethod
    def _folder_is_valid(folder_path: Path) -> bool:
        """Checks if a folder contains any media files."""
        from src.utils.img_utils import _get_first_media_path
        return _get_first_media_path(str(folder_path)) is not None

    def run(self):
        from PyQt6.QtGui import QImage, QColor
        from src.utils.img_utils import load_thumbnail_from_path, load_thumbnail_from_virtual_path, _get_first_media_path
        
        for idx, item in enumerate(self.items):
            if self._is_aborted:
                return
            item_type = ''
            qimg = None
            item_path = item

            if self.item_type == 'series':
                item_type = 'series'
                cover_image = item.get('cover_image')
                if cover_image:
                    if '|' in cover_image:
                        qimg = load_thumbnail_from_virtual_path(cover_image, self.thumb_width, self.thumb_height)
                    else:
                        qimg = load_thumbnail_from_path(cover_image, self.thumb_width, self.thumb_height)
            elif self.item_type == 'chapter':
                item_type = 'chapter'
                # 1. Try existing cover_path
                thumbnail_path = item.get('cover_path')
                
                # 2. If no cover_path, discover it robustly (Video, ZIP, Dir)
                if not thumbnail_path:
                    thumbnail_path = _get_first_media_path(item)
                
                if thumbnail_path:
                    if '|' in thumbnail_path:
                        qimg = load_thumbnail_from_virtual_path(thumbnail_path, self.thumb_width, self.thumb_height)
                    else:
                        qimg = load_thumbnail_from_path(thumbnail_path, self.thumb_width, self.thumb_height)
                    
                    if qimg and not qimg.isNull():
                        if self.library_manager and 'id' in item:
                            self.library_manager.set_chapter_cover_path(item['id'], thumbnail_path)
                        item['cover_path'] = thumbnail_path
            else:
                path_str = str(item_path)
                crop = None
                if path_str.endswith("_left"):
                    path_str = path_str[:-5]
                    crop = "left"
                elif path_str.endswith("_right"):
                    path_str = path_str[:-6]
                    crop = "right"

                # Discover media recursively/robustly for files/folders
                media_path = _get_first_media_path(path_str)
                if media_path:
                    if '|' in media_path:
                        item_type = 'archive' if media_path.split('|')[0].lower().endswith(('.zip', '.cbz', '.7z', '.rar')) else 'image'
                        qimg = load_thumbnail_from_virtual_path(media_path, self.thumb_width, self.thumb_height, crop)
                    elif Path(media_path).is_dir():
                        item_type = 'folder'
                        qimg = None # Should not happen with _get_first_media_path returning a file
                    else:
                        item_type = 'image'
                        qimg = load_thumbnail_from_path(media_path, self.thumb_width, self.thumb_height, crop)
                else:
                    self.signals.item_invalid.emit(idx, self.generation)
                    continue

            if not qimg or qimg.isNull():
                from src.utils.img_utils import empty_placeholder_qimage
                qimg = empty_placeholder_qimage(self.thumb_width, self.thumb_height)

            self.signals.item_loaded.emit(qimg, item, idx, self.generation, item_type)
        
        self.signals.loading_finished.emit(self.generation)
