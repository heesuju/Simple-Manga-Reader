import qdarktheme
import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from src.folder_grid import FolderGrid
from src.ui.chapter_list import ChapterListView
from src.utils.img_utils import get_chapter_number
from pathlib import Path
from dotenv import load_dotenv
from pathlib import Path
from src.utils.img_utils import get_chapter_number

load_dotenv()

from src.ui.reader_view import ReaderView

from src.core.library_manager import LibraryManager

class MainWindow(QMainWindow):
    def __init__(self, library_manager):
        super().__init__()
        self.setWindowTitle("Manga Reader")
        self.library_manager = library_manager
        self.current_series_has_chapters = False

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.folder_grid = FolderGrid(self.library_manager, self)
        self.folder_grid.series_selected.connect(self.show_chapter_list)
        self.folder_grid.recent_series_selected.connect(self.show_reader_for_recent)
        self.stacked_widget.addWidget(self.folder_grid)

    def show_chapter_list(self, series):
        self.current_series = series
        if series.get('chapters'):
            self.current_series_has_chapters = True
            self.chapter_list = ChapterListView(series, self.library_manager, self)
            self.chapter_list.back_to_library.connect(self.show_folder_grid)
            self.chapter_list.open_reader.connect(self.show_reader_view)
            self.stacked_widget.addWidget(self.chapter_list)
            self.stacked_widget.setCurrentWidget(self.chapter_list)
        else:
            self.current_series_has_chapters = False
            self.show_reader_view(series, None)

    def show_reader_for_recent(self, series):
        last_read_path = series.get('last_read_chapter')
        if not last_read_path:
            # If for some reason there is no last read chapter, fall back to chapter list
            self.show_chapter_list(series)
            return

        target_chapter = None
        for chapter in series.get('chapters', []):
            if chapter['path'] == last_read_path:
                target_chapter = chapter
                break
        
        if target_chapter:
            self.show_reader_view(series, target_chapter)
        else:
            # Fallback if chapter not found
            self.show_chapter_list(series)

    def show_folder_grid(self):
        self.folder_grid.load_recent_items()
        self.stacked_widget.setCurrentWidget(self.folder_grid)

    def show_reader_view(self, series, chapter):
        self.current_series = series
        if chapter:
            self.current_series_has_chapters = True
            # Save the last read chapter
            self.library_manager.update_last_read_chapter(series['id'], chapter['path'])
        else:
            self.current_series_has_chapters = False

        if chapter:
            chapter_files = [ch['path'] for ch in series['chapters']]
            chapter_index = series['chapters'].index(chapter)
            start_file = None # Start from the beginning of the chapter

            # Get all images in the chapter
            full_chapter_path = Path(chapter['path'])
            images = [str(p) for p in full_chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} and 'cover' not in p.name.lower()]
            images = sorted(images, key=get_chapter_number)
        else: # No chapters, it's a series of images
            chapter_files = []
            chapter_index = 0
            start_file = None
            full_series_path = Path(series['path'])
            images = [str(p) for p in full_series_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'} and 'cover' not in p.name.lower()]
            images = sorted(images, key=get_chapter_number)

        self.reader_view = ReaderView(series, chapter_files, chapter_index, start_file=start_file, images=images)
        self.reader_view.back_pressed.connect(self.handle_reader_back)
        self.stacked_widget.addWidget(self.reader_view)
        self.stacked_widget.setCurrentWidget(self.reader_view)

    def handle_reader_back(self):
        if self.current_series_has_chapters:
            if not hasattr(self, 'chapter_list') or self.chapter_list.series != self.current_series:
                self.show_chapter_list(self.current_series)
            else:
                self.stacked_widget.setCurrentWidget(self.chapter_list)
        else:
            self.stacked_widget.setCurrentWidget(self.folder_grid)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("dark")
    library_manager = LibraryManager()
    main_win = MainWindow(library_manager)
    main_win.show()
    sys.exit(app.exec())