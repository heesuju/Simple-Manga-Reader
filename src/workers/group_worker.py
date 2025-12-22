from PyQt6.QtCore import QRunnable, pyqtSignal, QObject
from pathlib import Path
from src.utils.img_utils import extract_page_number
from src.core.alt_manager import AltManager
import shutil

class GroupWorkerSignals(QObject):
    finished = pyqtSignal(str) # Message
    error = pyqtSignal(str)

class GroupPagesWorker(QRunnable):
    def __init__(self, series_path: str, chapter_path: str):
        super().__init__()
        self.series_path = series_path
        self.chapter_path = Path(chapter_path)
        self.signals = GroupWorkerSignals()

    def run(self):
        try:
            if not self.chapter_path.exists():
                self.signals.error.emit(f"Chapter path does not exist: {self.chapter_path}")
                return

            # 1. Scan images
            valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
            images = [
                p for p in self.chapter_path.iterdir() 
                if p.is_file() and p.suffix.lower() in valid_exts and p.stem.lower() != 'cover'
            ]

            if not images:
                self.signals.finished.emit("No images found to group.")
                return

            # 2. Group by number
            groups = {}
            for img in images:
                num = extract_page_number(img.name)
                if num == -1:
                    continue
                
                if num not in groups:
                    groups[num] = []
                groups[num].append(img)

            # 3. Process Groups
            alts_dir = self.chapter_path / "alts"
            processed_count = 0
            
            for num, files in groups.items():
                if len(files) <= 1:
                    continue

                # Sort by filename length as heuristic for "Main" (shortest is main)
                files.sort(key=lambda p: (len(p.stem), p.stem))
                
                main_image = files[0]
                alts = files[1:]

                # Create alts dir if needed
                if alts:
                    alts_dir.mkdir(exist_ok=True)

                alt_paths_relative = []

                for alt_img in alts:
                    target_path = alts_dir / alt_img.name
                    
                    # Move file if it's not already there
                    if alt_img.parent != alts_dir:
                        if target_path.exists():
                            pass 
                        else:
                            shutil.move(str(alt_img), str(target_path))
                    
                    # Store relative path for AltManager
                    alt_paths_relative.append(alt_img.name)
                
                # Link via AltManager
                
                AltManager.link_pages(
                    self.series_path,
                    self.chapter_path.name,
                    main_image.name,
                    alt_paths_relative
                )
                
                processed_count += 1

            self.signals.finished.emit(f"Grouped {processed_count} sets of pages.")

        except Exception as e:
            self.signals.error.emit(str(e))
