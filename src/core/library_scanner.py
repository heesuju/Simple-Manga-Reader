import os
from pathlib import Path
import re
from src.core.alt_manager import AltManager

# prefer treating images and video separately for cover-selection vs listing
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.jpe', '.webp', '.bmp', '.gif'}
VIDEO_EXTS = {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
ALL_MEDIA_EXTS = IMAGE_EXTS.union(VIDEO_EXTS)

def find_number(text:str)->float:
    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    return float(numbers[0]) if numbers else float('inf')

def get_chapter_number(path):
    """Extract the chapter number as integer or float from the folder or file name."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name

    match = re.search(r'Ch\.\s*(\d+(?:\.\d+)?)', name, re.IGNORECASE)
    if match:
        return float(match.group(1))
    else:
        return find_number(name)

class LibraryScanner:
    def is_archive(self, path: Path):
        return path.suffix.lower() in {'.zip', '.cbz', '.7z', '.rar', '.cbr', '.cb7'}

    def is_chapter_folder(self, path: Path):
        name = path.name.lower()
        return 'ch' in name or 'chapter' in name or any(char.isdigit() for char in name)

    def is_media_file(self, path: Path):
        """Return True for image or video files (used for scanning)."""
        return path.is_file() and path.suffix.lower() in ALL_MEDIA_EXTS

    def is_image_file(self, path: Path):
        """Return True only for actual image file extensions (used for cover selection)."""
        return path.is_file() and path.suffix.lower() in IMAGE_EXTS

    def has_valid_chapter_content(self, chapter_path: Path):
        """Check if chapter folder has media files other than cover.jpg/png."""
        for item in chapter_path.iterdir():
            if self.is_media_file(item):
                if item.name.lower() not in ['cover.jpg', 'cover.png']:
                    return True
        return False

    def scan_series(self, series_path):
        item = Path(series_path)
        
        # Case 1: Series is a single archive file (e.g. oneshot.zip)
        if item.is_file():
            if self.is_archive(item):
                series_name = item.stem
                
                chapters = self.scan_archive(item)
                
                if not chapters:
                    chapters = [{
                        "name": series_name,
                        "path": str(item)
                    }]
                
                return {
                    "name": series_name,
                    "path": str(item),
                    "cover_image": str(item),
                    "chapters": chapters,
                    "root_dir": str(item.parent)
                }
            return None

        # Case 2: Series is a folder
        if not item.is_dir():
            return None

        # Recursive scan for chapters
        chapters = self._scan_chapters_recursive(item, depth=0, max_depth=3)
        
        is_simple_series = False
        if len(chapters) == 1 and chapters[0]['path'] == str(item):
            is_simple_series = True
        
        if not chapters and not is_simple_series:
            return None

        series_name = item.name
        
        # Sort chapters
        sorted_chapters = sorted(chapters, key=lambda x: get_chapter_number(x['name']))
        
        cover_image = self.find_cover(item, sorted_chapters)

        return {
            "name": series_name,
            "path": str(item),
            "cover_image": str(cover_image) if cover_image else None,
            "chapters": sorted_chapters,
            "root_dir": str(item.parent)
        }
    
    def scan_archive(self, archive_path: Path) -> list:
        """
        Scan an archive for chapters (subfolders with images).
        Returns a list of dicts: {'name': ..., 'path': 'archive.zip|internal/path'}
        If the archive is 'flat' (images at root with no folder structure of interest), returns [].
        """
        import zipfile
        from src.utils.archive_utils import SevenZipHandler
        
        file_list = []
        is_seven_zip = False
        
        ext = archive_path.suffix.lower()
        if ext in {'.7z', '.rar', '.cbr', '.cb7'} and SevenZipHandler.is_available():
            file_list = SevenZipHandler.list_files(archive_path)
            is_seven_zip = True
        
        # Standard Zip
        if not file_list and not is_seven_zip:
            try:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    file_list = zf.namelist()
            except Exception:
                if SevenZipHandler.is_available() and not is_seven_zip:
                    file_list = SevenZipHandler.list_files(archive_path)
        
        if not file_list:
            return []

        try:
            # Build a simple tree
            # Node: {'files': bool, 'children': {name: Node}}
            root = {'has_images': False, 'children': {}}
            
            for name in file_list:
                if name.startswith('__MACOSX'): continue
                
                # Normalize path separators
                name = name.replace('\\', '/')
                
                parts = name.strip('/').split('/')
                if not parts or parts == ['']: continue
                
                # Check if file is image
                is_img = False
                if not name.endswith('/'):
                     path_obj = Path(name)
                     if path_obj.suffix.lower() in ALL_MEDIA_EXTS and path_obj.stem.lower() != 'cover':
                         is_img = True
                
                # Navigate/Build Tree
                current = root
                
                if len(parts) == 1 and not name.endswith('/'):
                    if is_img:
                        root['has_images'] = True
                    continue
                    
                # Directories
                dir_parts = parts[:-1] if not name.endswith('/') else parts
                
                for part in dir_parts:
                    if part not in current['children']:
                        current['children'][part] = {'has_images': False, 'children': {}}
                    current = current['children'][part]
                
                if is_img and not name.endswith('/'):
                    current['has_images'] = True
            
            chapters = []
            self._traverse_zip_tree(root, "", archive_path, chapters)
            
            if len(chapters) == 1 and chapters[0]['path'] == f"{archive_path}|":
                return []
                
            return chapters
            
        except Exception as e:
            print(f"Error scanning archive {archive_path}: {e}")
            return []

    def _traverse_zip_tree(self, node, current_path, archive_path, chapters):
        # If this node has direct images, it's a chapter.
        if node['has_images']:
            name = Path(current_path).name if current_path else archive_path.stem
            chapters.append({
                "name": name,
                "path": f"{archive_path}|{current_path}"
            })

        # Recurse
        for child_name, child_node in node['children'].items():
            if child_name.lower() in ('alts', 'translations'):
                continue
            new_path = f"{current_path}/{child_name}" if current_path else child_name
            self._traverse_zip_tree(child_node, new_path, archive_path, chapters)


    def _scan_chapters_recursive(self, folder: Path, depth: int, max_depth: int) -> list:
        if depth > max_depth:
            return []

        chapters = []

        # 1. Check if this folder ITSELF is a chapter (has images)
        has_content = False
        try:
            for f in folder.iterdir():
                if self.is_media_file(f):
                    if f.name.lower() not in ['cover.jpg', 'cover.png']: 
                        has_content = True
                        break
        except (PermissionError, OSError):
            pass

        if has_content:
            chapters.append({
                "name": folder.name,
                "path": str(folder)
            })

        # 2. Look for archives (chapters) and subfolders
        try:
            for item in folder.iterdir():
                if item.is_dir() and item.name.lower() in ('alts', 'translations'):
                    continue
                
                if self.is_archive(item):
                    # Check inside archive for structure
                    archive_chapters = self.scan_archive(item)
                    if archive_chapters:
                        chapters.extend(archive_chapters)
                    else:
                        # Fallback to whole archive as one chapter
                        chapters.append({
                            "name": item.stem,
                            "path": str(item)
                        })
                        
                elif item.is_dir():
                    # Recurse
                    sub_chapters = self._scan_chapters_recursive(item, depth + 1, max_depth)
                    chapters.extend(sub_chapters)
        except (PermissionError, OSError):
            pass
            
        return chapters

    def get_chapters(self, chapter_items):
        chapters = []
        for item in chapter_items:
            name = item.stem if item.is_file() else item.name
            chapters.append({
                "name": name,
                "path": str(item)
            })
        return sorted(chapters, key=lambda x: get_chapter_number(x['name']))

    def find_cover(self, series_path: Path, chapters):
        # Look for cover.jpg or cover.png (image only)
        for item in series_path.iterdir():
            if item.is_file() and item.name.lower() in ['cover.jpg', 'cover.png']:
                return item

        # If no explicit cover, prefer first image (not video) of first chapter
        if chapters:
            first_chapter = chapters[0]
            first_chapter_path = Path(first_chapter['path'])
            
            if first_chapter_path.is_dir():
                chapter_name = first_chapter.get('name', first_chapter_path.name)
                sort_mode = AltManager.get_chapter_sort(str(series_path), chapter_name)

                items = list(first_chapter_path.iterdir())
                if sort_mode == 'mtime':
                    items.sort(key=lambda p: os.path.getmtime(str(p)))
                elif sort_mode == 'ctime':
                    items.sort(key=lambda p: os.path.getctime(str(p)))
                else:
                    # Default: sort by chapter path natural
                    items.sort(key=lambda p: get_chapter_number(str(p).lower()))

                for item in items:
                    if self.is_image_file(item):
                        return item
                for item in items:
                    if self.is_media_file(item):
                        return item
            
            elif first_chapter_path.is_file():
                 return first_chapter_path

        # If no chapters, use first image in series folder (prefer images)
        for item in sorted(series_path.iterdir()):
            if self.is_image_file(item):
                return item

        # fallback: any media in series folder
        for item in sorted(series_path.iterdir()):
            if self.is_media_file(item):
                return item

        return None
