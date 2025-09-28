
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

    def find_series(self, root_dirs):
        series = []
        for root_dir in root_dirs:
            for item in Path(root_dir).iterdir():
                if not item.is_dir():
                    continue

                sub_items = list(item.iterdir())
                chapter_folders = [p for p in sub_items if p.is_dir() and self.is_chapter_folder(p)]
                image_files = [p for p in sub_items if self.is_image_file(p)]

                if chapter_folders:
                    series_path = os.path.relpath(item, root_dir)
                    series_name = item.name
                    chapters = self.get_chapters(chapter_folders, root_dir)
                    cover_image = self.find_cover(item, chapters, root_dir)
                    series.append({
                        "name": series_name,
                        "path": series_path,
                        "cover_image": cover_image,
                        "chapters": chapters,
                        "root_dir": root_dir
                    })
                elif image_files: # It's a series with no chapters
                    series_path = os.path.relpath(item, root_dir)
                    series_name = item.name
                    cover_image = self.find_cover(item, [], root_dir)
                    series.append({
                        "name": series_name,
                        "path": series_path,
                        "cover_image": cover_image,
                        "chapters": [],
                        "root_dir": root_dir
                    })
        return series

    def get_chapters(self, chapter_folders, root_dir):
        chapters = []
        for chapter_folder in chapter_folders:
            chapters.append({
                "name": chapter_folder.name,
                "path": os.path.relpath(chapter_folder, root_dir)
            })
        return sorted(chapters, key=lambda x: get_chapter_number(x['name']))

    def find_cover(self, series_path: Path, chapters, root_dir):
        # Look for cover.jpg or cover.png
        for item in series_path.iterdir():
            if item.is_file() and item.name.lower() in ['cover.jpg', 'cover.png']:
                return os.path.relpath(item, root_dir)

        # If no cover, use first image of first chapter
        if chapters:
            first_chapter_path = Path(os.path.join(root_dir, chapters[0]['path']))
            for item in sorted(first_chapter_path.iterdir()):
                if self.is_image_file(item):
                    return os.path.relpath(item, root_dir)
        
        # If no chapters, use first image in series folder
        for item in sorted(series_path.iterdir()):
            if self.is_image_file(item):
                return os.path.relpath(item, root_dir)

        return None
