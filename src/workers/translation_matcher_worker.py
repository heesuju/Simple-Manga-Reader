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
    def __init__(self, series_path: str, chapter_path: str, source_images: list[str], lang: Language):
        super().__init__()
        self.series_path = series_path
        self.chapter_path = Path(chapter_path)
        self.source_images = source_images
        self.lang = lang
        self.signals = TranslationWorkerSignals()

    def run(self):
        try:
            if not self.chapter_path.exists():
                self.signals.error.emit(f"Chapter path does not exist: {self.chapter_path}")
                return

            # 1. Identify Main Images in Chapter
            # We need to know which page number corresponds to which "Main" image file.
            # We reuse the logic from GroupPagesWorker to identify the MAIN image for each number.
            
            valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
            chapter_images = [
                p for p in self.chapter_path.iterdir() 
                if p.is_file() and p.suffix.lower() in valid_exts and 'cover' not in p.name.lower()
            ]

            # Group by number
            chapter_groups = {}
            for img in chapter_images:
                num = extract_page_number(img.name)
                if num == -1: continue
                if num not in chapter_groups: chapter_groups[num] = []
                chapter_groups[num].append(img)
            
            # Identify Main for each number
            main_images_by_num = {}
            for num, files in chapter_groups.items():
                # Shortest filename heuristic
                files.sort(key=lambda p: (len(p.stem), p.stem))
                main_images_by_num[num] = files[0] # The main file

            # 2. Process Source Images (Translations)
            # Create translations directory: chapter/translations/LANG/
            trans_dir = self.chapter_path / "translations" / self.lang.value
            trans_dir.mkdir(parents=True, exist_ok=True)

            matched_count = 0
            
            for src_path_str in self.source_images:
                src_path = Path(src_path_str)
                num = extract_page_number(src_path.name)
                
                if num == -1:
                    # Could not extract number, skip
                    continue
                
                if num in main_images_by_num:
                    main_image_path = main_images_by_num[num]
                    
                    # Move (or Copy) to translations dir
                    # Strategy: Copy to be safe? Or Move? 
                    # Drag Drop usually implies import. Let's Move? 
                    # Or maybe Copy if dragged from another drive?
                    # Let's Move for now as it's "Add Translations" implies putting them IN the library.
                    
                    target_name = src_path.name
                    target_path = trans_dir / target_name
                    
                    # Avoid overwrite if same name exists?
                    if target_path.exists():
                        # Simple overwrite
                        pass
                    
                    try:
                        shutil.move(str(src_path), str(target_path))
                    except shutil.Error:
                        # Fallback to copy+delete if move fails (e.g. cross-device)
                        shutil.copy2(str(src_path), str(target_path))
                        os.remove(str(src_path))
                    
                    # Link via AltManager
                    # link_translation takes: main_file (name? path?), translation_file (name in subfolder?)
                    # AltManager logic needs filename. 
                    
                    # AltManager.link_translation expects paths or names?
                    # Looking at code: main_name = Path(main_file).name
                    # trans_name = Path(translation_file).name
                    # entry["translations"][lang.value] = trans_name
                    
                    # So we just pass the filenames.
                    # Since we updated AltManager to look in 'translations/LANG/filename', 
                    # storing just the filename is correct.
                    
                    AltManager.link_translation(
                        self.series_path,
                        self.chapter_path.name,
                        main_image_path.name,
                        self.lang,
                        target_name
                    )
                    
                    matched_count += 1
            
            self.signals.finished.emit(f"Matched and linked {matched_count} translations.")

        except Exception as e:
            self.signals.error.emit(str(e))
            import traceback
            traceback.print_exc()
