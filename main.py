import qdarktheme
import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget
from PyQt6.QtGui import QKeySequence, QShortcut, QIcon
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from src.ui.folder_grid import FolderGrid
from src.ui.chapter_list import ChapterListView
from src.utils.img_utils import get_chapter_number
from src.utils.resource_utils import resource_path
from pathlib import Path

from src.ui.reader_view import ReaderView


def register_context_menu():
    """Register 'Open in SU.zip' right-click option for folders.
    Only writes to the registry if the entry is missing or points to a different path."""
    try:
        import winreg
        if getattr(sys, 'frozen', False):
            base_cmd = f'"{sys.executable}"'
        else:
            script_path = os.path.abspath(__file__)
            base_cmd = f'"{sys.executable}" "{script_path}"'

        def _register_entry(key_name, label, command):
            cmd_key_path = rf"Software\Classes\Directory\shell\{key_name}\command"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as key:
                    current, _ = winreg.QueryValueEx(key, "")
                    if current == command:
                        return  # Already up to date
            except OSError:
                pass
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\Directory\shell\{key_name}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, label)
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{sys.executable}"')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

        _register_entry("OpenInSUzip",        "Open in SU.zip",          f'{base_cmd} "%1"')
        _register_entry("AddToSUzip",  "Add to SU.zip",   f'{base_cmd} --add-series "%1"')
    except Exception as e:
        print(f"Failed to register context menu: {e}")

from src.core.library_manager import LibraryManager

_SERVER_NAME = "SUzip-instance"

class MainWindow(QMainWindow):
    def __init__(self, library_manager):
        super().__init__()
        self.setWindowTitle("SU.zip")
        self.library_manager = library_manager
        self.current_series_has_chapters = False
        self.reader_view = None # Initialize reader_view attribute

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.folder_grid = FolderGrid(self.library_manager, self)
        self.folder_grid.series_selected.connect(self.show_chapter_list)
        self.folder_grid.recent_series_selected.connect(self.show_reader_for_recent)
        self.stacked_widget.addWidget(self.folder_grid)

        self._privacy_overlay = QWidget(self)
        self._privacy_overlay.setStyleSheet("background: black;")
        self._privacy_overlay.hide()
        self._privacy_was_playing = False

        # Global Escape key shortcut
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self._handle_escape_key)

        QShortcut(QKeySequence(Qt.Key.Key_QuoteLeft), self, activated=self._toggle_privacy_overlay)

        # Global shortcuts for fullscreen toggle
        self.fullscreen_shortcut_alt = QShortcut(QKeySequence("Alt+Return"), self)
        self.fullscreen_shortcut_alt.activated.connect(self.toggle_fullscreen)
        
        self.fullscreen_shortcut_f11 = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut_f11.activated.connect(self.toggle_fullscreen)

        self._local_server = QLocalServer(self)
        QLocalServer.removeServer(_SERVER_NAME)
        self._local_server.listen(_SERVER_NAME)
        self._local_server.newConnection.connect(self._on_new_instance)

    def _on_new_instance(self):
        socket = self._local_server.nextPendingConnection()
        socket.waitForReadyRead(1000)
        data = socket.readAll().data()
        socket.deleteLater()
        try:
            args = json.loads(data)
            QTimer.singleShot(0, lambda: self._handle_args(args))
        except Exception:
            pass

    def _handle_args(self, args):
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.activateWindow()
        self.raise_()
        if len(args) >= 2 and args[0] == "--add-series" and os.path.isdir(args[1]):
            self.folder_grid.add_single(args[1])
        elif len(args) >= 1 and os.path.isdir(args[0]):
            self.open_folder_in_reader(args[0])

    def _handle_escape_key(self):
        current_widget = self.stacked_widget.currentWidget()
        
        if hasattr(self, 'reader_view') and current_widget == self.reader_view:
            self.reader_view.back_to_grid()
        elif hasattr(self, 'chapter_list') and current_widget == self.chapter_list:
            self.chapter_list.go_back()

    def show_chapter_list(self, series):
        self.current_series = series
        
        self.current_series_has_chapters = True
        self.chapter_list = ChapterListView(series, self.library_manager, self)
        self.chapter_list.back_to_library.connect(self.show_folder_grid)
        self.chapter_list.open_reader.connect(self.show_reader_view)
        self.chapter_list.tag_clicked.connect(self._on_tag_clicked)
        self.stacked_widget.addWidget(self.chapter_list)
        self.stacked_widget.setCurrentWidget(self.chapter_list)
        # else:
        #     self.current_series_has_chapters = False
        #     self.show_reader_view(series, None)

    def _on_tag_clicked(self, tag_type, tag_value):
        self.folder_grid.apply_tag_filter(tag_type, tag_value)
        self.show_folder_grid()

    def show_reader_for_recent(self, series):
        if series.get('_is_missing'):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Series Missing", f"The series '{series['name']}' is currently missing or inaccessible.\nPath: {series['path']}")
            return

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
            start_page = series.get('last_read_page', 0) or 0
            self.show_reader_view(series, target_chapter, start_page=start_page)
        else:
            # Fallback if chapter not found
            self.show_chapter_list(series)

    def show_folder_grid(self):
        self.folder_grid.load_recent_items()
        self.stacked_widget.setCurrentWidget(self.folder_grid)

    def show_reader_view(self, series, chapter, start_page=0):
        self.current_series = series
        if chapter:
            self.current_series_has_chapters = True
            # Save the last read chapter
            self.library_manager.update_last_read_chapter(series['id'], chapter['path'])
        else:
            self.current_series_has_chapters = False

        if chapter and chapter in series['chapters']:
            chapter_files = [ch['path'] for ch in series['chapters']]
            chapter_index = series['chapters'].index(chapter)
            start_file = None # Start from the beginning of the chapter

            # Get all images in the chapter
            full_chapter_path_str = chapter['path']
            is_virtual = '|' in full_chapter_path_str
            
            full_chapter_path = Path(full_chapter_path_str)
            
            if is_virtual or (full_chapter_path.is_file() and full_chapter_path.suffix.lower() in {'.zip', '.cbz'}):
                images = []
            else:
                try:
                    images = [str(p) for p in full_chapter_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.avif', '.mp4', '.webm', '.mkv', '.avi', '.mov'} and p.stem.lower() != 'cover']
                    images = sorted(images, key=get_chapter_number)
                except (NotADirectoryError, FileNotFoundError, OSError):
                    images = []
        else: # No chapters, it's a series of images
            chapter_files = []
            chapter_index = 0
            start_file = None
            full_series_path = Path(series['path'])
            if full_series_path.is_file() and full_series_path.suffix.lower() in {'.zip', '.cbz'}:
                images = []
            else:
                try:
                    images = [str(p) for p in full_series_path.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.avif', '.mp4', '.webm', '.mkv', '.avi', '.mov'} and p.stem.lower() != 'cover']
                    images = sorted(images, key=get_chapter_number)
                except (NotADirectoryError, FileNotFoundError):
                    images = []

        self.reader_view = ReaderView(series, chapter_files, chapter_index, start_file=start_file, images=images, start_page=start_page)
        self.reader_view.back_pressed.connect(self.handle_reader_back)
        self.reader_view.request_fullscreen_toggle.connect(self.toggle_fullscreen)
        self.reader_view.current_chapter_changed.connect(self.on_reader_chapter_changed)
        self.reader_view.hide_chapter_requested.connect(self.on_reader_hide_chapter)
        self.stacked_widget.addWidget(self.reader_view)
        self.stacked_widget.setCurrentWidget(self.reader_view)

    def on_reader_hide_chapter(self, series, chapter_dict):
        series_path = str(series['path'])
        self.library_manager.hide_chapter(series_path, chapter_dict)
        # Keep current_series chapters in sync so the chapter list stays correct
        if chapter_dict in self.current_series.get('chapters', []):
            self.current_series['chapters'].remove(chapter_dict)

    def on_reader_chapter_changed(self, series, chapter_path):
        if series and chapter_path:
            self.library_manager.update_last_read_chapter(series['id'], chapter_path, 0)

    def handle_reader_back(self):
        if hasattr(self, 'reader_view') and self.reader_view:
            model = self.reader_view.model
            chapter = model.manga_dir
            chapter_path = chapter.get('path') if isinstance(chapter, dict) else str(chapter) if chapter else None
            if chapter_path and self.current_series:
                page = getattr(model, 'current_index', 0)
                images = getattr(model, 'images', [])
                image_path = images[page].images[0] if images and page < len(images) else None
                self.library_manager.update_last_read_chapter(self.current_series['id'], chapter_path, page, image_path)

        if self.current_series_has_chapters:
            if not hasattr(self, 'chapter_list') or self.chapter_list.series != self.current_series:
                self.show_chapter_list(self.current_series)
            else:
                self.stacked_widget.setCurrentWidget(self.chapter_list)
        else:
            self.show_folder_grid()

    def open_folder_in_reader(self, folder_path):
        path = Path(folder_path)
        if not path.is_dir():
            return
        chapter = str(path)
        series = {
            'id': None,
            'name': path.name,
            'path': str(path),
            'chapters': [chapter],
            'cover_image': None,
            'last_read_chapter': None,
            'last_read_page': 0,
        }
        self.current_series = series
        self.current_series_has_chapters = False  # back goes to folder grid, not chapter list
        self.reader_view = ReaderView(series, [chapter], 0)
        self.reader_view.back_pressed.connect(self.handle_reader_back)
        self.reader_view.request_fullscreen_toggle.connect(self.toggle_fullscreen)
        self.reader_view.current_chapter_changed.connect(self.on_reader_chapter_changed)
        self.reader_view.hide_chapter_requested.connect(self.on_reader_hide_chapter)
        self.stacked_widget.addWidget(self.reader_view)
        self.stacked_widget.setCurrentWidget(self.reader_view)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._privacy_overlay.isVisible():
            self._privacy_overlay.setGeometry(self.rect())

    def _toggle_privacy_overlay(self):
        if self._privacy_overlay.isVisible():
            self._privacy_overlay.hide()
        else:
            player = self._get_media_player()
            from PyQt6.QtMultimedia import QMediaPlayer
            self._privacy_was_playing = (
                player is not None and
                player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            if self._privacy_was_playing:
                player.pause()
            self._privacy_overlay.setGeometry(self.rect())
            self._privacy_overlay.show()
            self._privacy_overlay.raise_()

    def _get_media_player(self):
        rv = getattr(self, 'reader_view', None)
        if rv and hasattr(rv, 'video_viewer'):
            return rv.video_viewer.media_player
        return None

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("assets/icons/app.png")))

    # Global exception handler for unexpected crashes
    def exception_hook(exctype, value, traceback):
        print(f"FATAL ERROR: {exctype.__name__}: {value}")
        import traceback as tb
        err_msg = "".join(tb.format_exception(exctype, value, traceback))
        print(err_msg)
        
        try:
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("The application has crashed.")
            msg.setInformativeText(str(value))
            msg.setDetailedText(err_msg)
            msg.setWindowTitle("Crash Report")
            msg.exec()
        except:
            pass
        sys.__excepthook__(exctype, value, traceback)
        sys.exit(1)

    sys.excepthook = exception_hook

    # Single-instance check — forward args to running instance and exit
    if len(sys.argv) > 1:
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if socket.waitForConnected(500):
            socket.write(json.dumps(sys.argv[1:]).encode())
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            sys.exit(0)

    try:
        qdarktheme.setup_theme("dark")
    except AttributeError:
        app.setStyleSheet(qdarktheme.load_stylesheet("dark"))
    
    # Start LLM Server
    from src.core.llm_server import LLMServerManager
    llm_manager = LLMServerManager.instance()
    if llm_manager.auto_start:
        llm_manager.start()

    register_context_menu()

    library_manager = LibraryManager()
    main_win = MainWindow(library_manager)
    main_win.showMaximized()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--add-series" and len(sys.argv) > 2:
            main_win.folder_grid.add_single(sys.argv[2])
        else:
            main_win.open_folder_in_reader(arg)

    exit_code = app.exec()
    
    llm_manager.stop()
    try:
        import shutil
        from src.utils.img_utils import ZIP_CACHE
        from src.utils.archive_utils import ARCHIVE_CACHE_DIR
        ZIP_CACHE.clear()
        if ARCHIVE_CACHE_DIR.exists():
            shutil.rmtree(ARCHIVE_CACHE_DIR, ignore_errors=True)
    except Exception:
        pass
    
    sys.exit(exit_code)