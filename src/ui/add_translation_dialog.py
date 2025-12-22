import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QDialogButtonBox, 
    QPushButton, QHBoxLayout, QWidget, QComboBox, QAbstractItemView,
    QListWidgetItem, QScrollArea, QFrame, QMenu
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap, QDrag
from src.utils.img_utils import load_thumbnail_from_path, extract_page_number
from src.enums import Language
from src.core.alt_manager import AltManager

class TranslationSlot(QFrame):
    """
    A single slot for a translation image.
    Supports Drag & Drop of a single file.
    """
    file_dropped = pyqtSignal(str) # Emits path
    removed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 170)
        self.setStyleSheet("""
            TranslationSlot {
                background-color: rgba(0, 0, 0, 50);
                border: 2px dashed #555;
                border-radius: 5px;
            }
            TranslationSlot:hover {
                border-color: #777;
            }
        """)
        self.setAcceptDrops(True)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("border: none; background: transparent;")
        
        self.name_label = QLabel("Drop Here")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("color: #aaa; font-size: 10px; border: none; background: transparent;")
        self.name_label.setWordWrap(True)
        self.name_label.setFixedHeight(40)
        
        self.layout.addWidget(self.preview, 1)
        self.layout.addWidget(self.name_label)
        
        self.current_path = None

    def set_image(self, path: str):
        self.current_path = path
        if path:
            pix = load_thumbnail_from_path(path, 110, 120)
            if pix:
                self.preview.setPixmap(pix)
            else:
                self.preview.setText("No Preview")
            self.preview.setStyleSheet("border: none; background: transparent;")
            
            self.setStyleSheet("""
                TranslationSlot {
                    background-color: rgba(0, 0, 0, 50);
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                }
            """)
            self.name_label.setText(Path(path).name)
            self.name_label.setToolTip(Path(path).name)
        else:
            self.clear()

    def clear(self):
        self.current_path = None
        self.preview.clear()
        self.name_label.setText("Drop Here")
        self.setStyleSheet("""
            TranslationSlot {
                background-color: rgba(0, 0, 0, 50);
                border: 2px dashed #555;
                border-radius: 5px;
            }
        """)
        self.removed.emit()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Check if it's a file, not a folder (folders handled by parent)
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile() and os.path.isfile(urls[0].toLocalFile()):
                event.acceptProposedAction()
                self.setStyleSheet("""
                    TranslationSlot {
                        background-color: rgba(3, 169, 244, 0.2);
                        border: 2px dashed #03A9F4;
                        border-radius: 5px;
                    }
                """)
            else:
                event.ignore()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        # Restore style based on state
        if self.current_path:
            self.set_image(self.current_path) # Re-applies solid border
        else:
            self.clear() # Re-applies dashed border
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                path = urls[0].toLocalFile()
                if os.path.isfile(path):
                    valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
                    if Path(path).suffix.lower() in valid_exts:
                         self.set_image(path)
                         self.file_dropped.emit(path)
                         event.acceptProposedAction() 

class MappingRow(QWidget):
    def __init__(self, main_page_path, page_num, parent=None):
        super().__init__(parent)
        self.main_path = main_page_path
        self.page_num = page_num
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        # Left: Main Page
        self.main_frame = QFrame()
        self.main_frame.setFixedSize(120, 170)
        self.main_frame.setStyleSheet("background-color: rgba(0,0,0,30); border-radius: 5px;")
        main_layout = QVBoxLayout(self.main_frame)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self.main_thumb = QLabel()
        self.main_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = load_thumbnail_from_path(main_page_path, 110, 120)
        if pix:
            self.main_thumb.setPixmap(pix)
        else:
            self.main_thumb.setText("No Image")
            
        # Prioritize showing the actual filename
        self.main_lbl = QLabel(Path(main_page_path).name)
        self.main_lbl.setStyleSheet("color: white; font-size: 10px;")
        self.main_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_lbl.setWordWrap(True)
        self.main_lbl.setFixedHeight(40)
        self.main_lbl.setToolTip(Path(main_page_path).name)
        
        main_layout.addWidget(self.main_thumb, 1)
        main_layout.addWidget(self.main_lbl)
        
        # Arrow
        arrow = QLabel("→")
        arrow.setStyleSheet("color: #aaa; font-size: 20px; font-weight: bold;")
        
        # Right: Translation Slot
        self.slot = TranslationSlot()
        
        # Remove Button
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setToolTip("Remove Translation")
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 0, 0, 50);
                color: white;
                border: 1px solid #555;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 100);
            }
        """)
        self.remove_btn.clicked.connect(self.slot.clear)
        self.remove_btn.hide() # Hidden by default
        
        # Connect slot changed/cleared signals to button visibility
        self.slot.file_dropped.connect(self._on_slot_changed)
        self.slot.removed.connect(self._on_slot_changed) 
        # TranslationSlot needs to emit signal when cleared via set_image(None) too?
        # Actually TranslationSlot.clear() is called by remove_btn.
        # But set_translation calls set_image.
        
        layout.addWidget(self.main_frame)
        layout.addWidget(arrow)
        layout.addWidget(self.slot)
        layout.addWidget(self.remove_btn)
        layout.addStretch()

    def _on_slot_changed(self):
        self.remove_btn.setVisible(bool(self.slot.current_path))

    def get_main_filename(self):
        return Path(self.main_path).name

    def get_translation_path(self):
        return self.slot.current_path

    def set_translation(self, path):
        self.slot.set_image(path)
        self._on_slot_changed()


class AddTranslationDialog(QDialog):
    def __init__(self, series_path: str, chapter_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Translations (Drag & Drop)")
        self.resize(500, 700)
        self.setAcceptDrops(True) # Global drop for folders
        
        self.series_path = series_path
        self.chapter_path = Path(chapter_path)
        
        self.layout = QVBoxLayout(self)
        
        # 1. Language Selection
        lang_layout = QHBoxLayout()
        lang_label = QLabel("Translation Language:")
        lang_label.setStyleSheet("color: white; font-weight: bold;")
        
        self.lang_combo = QComboBox()
        for lang in Language:
            self.lang_combo.addItem(lang.value, lang)
            
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        self.layout.addLayout(lang_layout)
        
        # 2. Instructions
        self.instructions = QLabel(
            "1. Drag a FOLDER here to auto-match translations by number.\n"
            "2. Drag individual files to slots to manually assign.\n"
            "3. Click the X button to remove a translation."
        )
        self.instructions.setStyleSheet("color: #aaa; font-size: 12px; margin-bottom: 10px;")
        self.layout.addWidget(self.instructions)
        
        # 3. Scroll Area for Rows
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.rows_layout = QVBoxLayout(self.container)
        self.rows_layout.setSpacing(10)
        self.rows_layout.addStretch() # Push items up
        
        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)
        
        # 4. Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True) 
        self.layout.addWidget(self.button_box)
        
        self.rows: list[MappingRow] = []
        self.pages: list = [] # Store Page objects
        self._load_chapter_pages()
        
        # Connect signal after loading pages
        self.lang_combo.currentTextChanged.connect(self._on_language_changed)
        
        # Initial load for default language
        self._on_language_changed(self.lang_combo.currentText())

    def _load_chapter_pages(self):
        # Use AltManager to Group Pages
        if not self.chapter_path.exists():
            return
            
        alt_config = AltManager.load_alts(self.series_path)
        chapter_alts = alt_config.get(self.chapter_path.name, {})
        
        valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
        images = [str(p) for p in self.chapter_path.iterdir() 
                  if p.is_file() and p.suffix.lower() in valid_exts and p.stem.lower() != 'cover']
        
        grouped_pages = AltManager.group_images(images, chapter_alts)
        self.pages = grouped_pages
        
        # remove stretch
        item = self.rows_layout.takeAt(self.rows_layout.count() - 1)
        
        for page in grouped_pages:
             # Identify main image (first in list)
             if not page.images: continue
             main_img = page.images[0]
             
             # Extract number using img_utils
             num = extract_page_number(main_img)
             
             row = MappingRow(main_img, num)
             self.rows_layout.addWidget(row)
             self.rows.append(row)
        
        # restore stretch
        self.rows_layout.addStretch()

    def _on_language_changed(self, lang_text):
        try:
             target_lang = Language(lang_text).value
             self._update_slots_for_language(target_lang)
        except ValueError:
             pass

    def _update_slots_for_language(self, lang_code: str):
        # Clear/Update slots based on existing translation data
        for i, row in enumerate(self.rows):
            if i < len(self.pages):
                page = self.pages[i]
                
                # Check if this page has a translation for lang_code
                if page.translations and lang_code in page.translations:
                    trans_path = page.translations[lang_code]
                    row.set_translation(trans_path)
                else:
                    row.set_translation(None) # Clear slot if no translation

    def get_selected_language(self) -> Language:
        return self.lang_combo.currentData()

    def get_mapping(self) -> list[tuple[str, str]]:
        """Returns list of (main_filename, translation_abspath). None path means remove."""
        mapping = []
        for row in self.rows:
            trans_path = row.get_translation_path()
            # Send ALL rows. Processing worker will handle None as delete/unlink.
            mapping.append((row.get_main_filename(), trans_path))
        return mapping

    # Global Drag Events (For Folders)
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Accept if at least one folder
            for url in event.mimeData().urls():
                if os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            # Process Folders
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self._process_folder_drop(path)
            event.acceptProposedAction()

    def _process_folder_drop(self, folder_path):
        """Auto-match files in folder to rows"""
        valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
        try:
            for f in os.listdir(folder_path):
                full_path = os.path.join(folder_path, f)
                if os.path.isfile(full_path) and os.path.splitext(f)[1].lower() in valid_exts:
                    num = extract_page_number(f)
                    if num != -1:
                        # Find matching row
                        for row in self.rows:
                            if row.page_num == num:
                                row.set_translation(full_path)
                                break
        except OSError:
            pass
