from PyQt6.QtCore import QRunnable, pyqtSignal, QObject
from pathlib import Path
import shutil
import os
from src.utils.img_utils import extract_page_number
from src.core.alt_manager import AltManager
from src.enums import Language

class TranslationWorkerSignals(QObject):
    finished = pyqtSignal(str) # Message
    error = pyqtSignal(str)

class TranslationMatcherWorker(QRunnable):
    def __init__(self, series_path: str, chapter_path: str, mapping: list[tuple[str, str]], lang: Language):
        super().__init__()
        self.series_path = series_path
        self.chapter_path = Path(chapter_path)
        self.mapping = mapping # List of (main_filename, source_path)
        self.lang = lang
        self.signals = TranslationWorkerSignals()

    def run(self):
        print(f"DEBUG: Worker started for {self.chapter_path}")
        print(f"DEBUG: Mapping size: {len(self.mapping)}")
        try:
            if not self.chapter_path.exists():
                self.signals.error.emit(f"Chapter path does not exist: {self.chapter_path}")
                return

            # Create translations directory: chapter/translations/LANG/
            trans_dir = self.chapter_path / "translations" / self.lang.value
            trans_dir.mkdir(parents=True, exist_ok=True)

            matched_count = 0
            
            for main_filename, src_path_str in self.mapping:
                
                # Case: Removal (src_path_str is None)
                if src_path_str is None:
                    AltManager.link_translation(
                        self.series_path,
                        self.chapter_path.name,
                        main_filename,
                        self.lang,
                        None
                    )
                    matched_count += 1
                    continue
                    
                src_path = Path(src_path_str)
                
                # Move (or Copy) to translations dir
                target_name = src_path.name
                target_path = trans_dir / target_name
                
                # Copy/Move Logic
                if src_path.resolve() != target_path.resolve():
                    if target_path.exists():
                         # If target exists, maybe just link it? 
                         # User asked to check for dupes.
                         # If we are dragging a file that is already there (same name), we assume user meant to use THAT file.
                         # So we skip copy/move.
                         pass
                    else:
                        try:
                             shutil.move(str(src_path), str(target_path))
                        except shutil.Error:
                             shutil.copy2(str(src_path), str(target_path))
                             os.remove(str(src_path))
                
                AltManager.link_translation(
                    self.series_path,
                    self.chapter_path.name,
                    main_filename,
                    self.lang,
                    target_name
                )
                
                matched_count += 1
            
            self.signals.finished.emit(f"Linked {matched_count} translations.")

        except Exception as e:
            self.signals.error.emit(str(e))
            import traceback
            traceback.print_exc()
