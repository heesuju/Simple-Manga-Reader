
import os
from pathlib import Path
import re

def find_number(text:str)->int:
    numbers = re.findall(r'\d+', text)
    return int(numbers[0]) if numbers else float('inf')

def get_chapter_number(path):
    """Extract the chapter number as integer from the folder or file name."""
    if isinstance(path, str) and '|' in path:
        name = Path(path.split('|')[1]).name
    else:
        name = Path(path).name
    
    match = re.search(r'Ch\.\s*(\d+)', name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    else:
        return find_number(name)

class LibraryScanner:
    def is_chapter_folder(self, path: Path):
        name = path.name.lower()
        return 'ch' in name or 'chapter' in name or any(char.isdigit() for char in name)

    def is_image_file(self, path: Path):
        return path.is_file() and path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif']

    def scan_series(self, series_path):
        item = Path(series_path)
        if not item.is_dir():
            return None

        sub_items = list(item.iterdir())
        chapter_folders = [p for p in sub_items if p.is_dir()]
        image_files = [p for p in sub_items if self.is_image_file(p)]

        if chapter_folders:
            series_name = item.name
            chapters = self.get_chapters(chapter_folders)
            cover_image = self.find_cover(item, chapters)
            return {
                "name": series_name,
                "path": str(item),
                "cover_image": str(cover_image) if cover_image else None,
                "chapters": chapters,
                "root_dir": str(item.parent)
            }
        elif image_files: # It's a series with no chapters
            series_name = item.name
            cover_image = self.find_cover(item, [])
            return {
                "name": series_name,
                "path": str(item),
                "cover_image": str(cover_image) if cover_image else None,
                "chapters": [],
                "root_dir": str(item.parent)
            }
        return None

    def get_chapters(self, chapter_folders):
        chapters = []
        for chapter_folder in chapter_folders:
            chapters.append({
                "name": chapter_folder.name,
                "path": str(chapter_folder)
            })
        return sorted(chapters, key=lambda x: get_chapter_number(x['name']))

    def find_cover(self, series_path: Path, chapters):
        # Look for cover.jpg or cover.png
        for item in series_path.iterdir():
            if item.is_file() and item.name.lower() in ['cover.jpg', 'cover.png']:
                return item

        # If no cover, use first image of first chapter
        if chapters:
            first_chapter_path = Path(chapters[0]['path'])
            for item in sorted(first_chapter_path.iterdir()):
                if self.is_image_file(item):
                    return item
        
        # If no chapters, use first image in series folder
        for item in sorted(series_path.iterdir()):
            if self.is_image_file(item):
                return item

        return None
