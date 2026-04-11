import os
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from PyQt6.QtGui import QPixmap, QImage
from src.utils.img_utils import is_image_folder, load_thumbnail_from_path, load_thumbnail_from_zip, load_thumbnail_from_virtual_path, get_chapter_number, is_image_monotone
from src.utils.archive_utils import ARCHIVE_EXTS

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
        
        # Drive status cache for this run to avoid repeated 30s hangs on Windows
        drive_status = {}

        def is_drive_ready(path_str):
            if not path_str or not isinstance(path_str, str):
                return False
            drive = os.path.splitdrive(path_str)[0]
            if not drive: # Relative path or something else, assume ready
                return True
            if drive in drive_status:
                return drive_status[drive]
            
            # Fast check for drive readiness
            try:
                ready = os.path.exists(drive + '\\')
                drive_status[drive] = ready
                return ready
            except Exception:
                drive_status[drive] = False
                return False

        for idx, item in enumerate(self.items):
            if self._is_aborted:
                return
            item_type = ''
            qimg = None

            try:
                if self.item_type == 'series':
                    item_type = 'series'
                    path_str = item.get('path')
                    
                    if not path_str or not is_drive_ready(path_str):
                        item['_is_missing'] = True
                    else:
                        series_path = Path(path_str)
                        if not series_path.exists():
                            item['_is_missing'] = True
                        elif series_path.is_file() and not series_path.suffix.lower() in {'.zip', '.cbz', '.7z', '.rar', '.cbr', '.cb7'}:
                            item['_is_missing'] = True

                    if not item.get('_is_missing'):
                        cover_image = item.get('cover_image')
                        if cover_image:
                            if '|' in cover_image:
                                qimg = load_thumbnail_from_virtual_path(cover_image, self.thumb_width, self.thumb_height)
                            elif is_drive_ready(cover_image):
                                qimg = load_thumbnail_from_path(cover_image, self.thumb_width, self.thumb_height)
                
                elif self.item_type == 'page':
                    item_type = 'page'
                    thumbnail_path = item.get('image_path')
                    series = item.get('_series', {})
                    series_path_str = series.get('path') if series else None
                    
                    # 1. Check if series path exists (if available)
                    if series_path_str:
                        if not is_drive_ready(series_path_str) or not os.path.exists(series_path_str):
                            item['_is_missing'] = True
                    
                    # 2. Check thumbnail existence
                    if not item.get('_is_missing') and thumbnail_path:
                        if '|' in thumbnail_path:
                            qimg = load_thumbnail_from_virtual_path(thumbnail_path, self.thumb_width, self.thumb_height)
                        elif is_drive_ready(thumbnail_path) and os.path.exists(thumbnail_path):
                            qimg = load_thumbnail_from_path(thumbnail_path, self.thumb_width, self.thumb_height)
                        else:
                             item['_is_missing'] = True

                elif self.item_type == 'chapter':
                    item_type = 'chapter'
                    thumbnail_path = item.get('cover_path')
                    
                    if not thumbnail_path:
                        # discovery might be slow, so check drive
                        if is_drive_ready(item.get('path')):
                             thumbnail_path = _get_first_media_path(item)
                    
                    if thumbnail_path:
                        if '|' in thumbnail_path:
                            qimg = load_thumbnail_from_virtual_path(thumbnail_path, self.thumb_width, self.thumb_height)
                        elif is_drive_ready(thumbnail_path) and os.path.exists(thumbnail_path):
                            qimg = load_thumbnail_from_path(thumbnail_path, self.thumb_width, self.thumb_height)
                        else:
                            item['_is_missing'] = True
                        
                        if qimg and not qimg.isNull():
                            if self.library_manager and 'id' in item:
                                self.library_manager.set_chapter_cover_path(item['id'], thumbnail_path)
                            item['cover_path'] = thumbnail_path
                    else:
                        item['_is_missing'] = True

                else: # Generic file/folder loader
                    path_str = str(item)
                    if not is_drive_ready(path_str):
                        self.signals.item_invalid.emit(idx, self.generation)
                        continue

                    crop = None
                    if path_str.endswith("_left"):
                        path_str = path_str[:-5]
                        crop = "left"
                    elif path_str.endswith("_right"):
                        path_str = path_str[:-6]
                        crop = "right"

                    media_path = _get_first_media_path(path_str)
                    if media_path:
                        if '|' in media_path:
                            item_type = 'archive' if Path(media_path.split('|')[0]).suffix.lower() in ARCHIVE_EXTS else 'image'
                            qimg = load_thumbnail_from_virtual_path(media_path, self.thumb_width, self.thumb_height, crop)
                        elif Path(media_path).is_dir():
                            item_type = 'folder'
                            qimg = None 
                        else:
                            item_type = 'image'
                            qimg = load_thumbnail_from_path(media_path, self.thumb_width, self.thumb_height, crop)
                    else:
                        self.signals.item_invalid.emit(idx, self.generation)
                        continue

                # Fallback to placeholder if missing or failed
                if item.get('_is_missing') or not qimg or qimg.isNull():
                    from src.utils.img_utils import empty_placeholder_qimage
                    qimg = empty_placeholder_qimage(self.thumb_width, self.thumb_height)

                self.signals.item_loaded.emit(qimg, item, idx, self.generation, item_type)
            
            except Exception as e:
                print(f"Error in ItemLoader at index {idx}: {e}")
                import traceback
                traceback.print_exc()
                self.signals.item_invalid.emit(idx, self.generation)
        
        self.signals.loading_finished.emit(self.generation)
        
        self.signals.loading_finished.emit(self.generation)
