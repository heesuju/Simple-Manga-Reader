import shutil
import os
from pathlib import Path
from typing import Set

from PyQt6.QtCore import QThreadPool, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QMenu, QApplication, QFileDialog
from PyQt6.QtGui import QAction, QCursor, QKeySequence
import uuid
import subprocess

from src.ui.base.collapsible_panel import CollapsiblePanel
from src.ui.page_thumbnail import PageThumbnail
from src.workers.thumbnail_worker import ThumbnailWorker
from src.data.reader_model import ReaderModel
from src.enums import ViewMode
from src.utils.img_utils import empty_placeholder, load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.core.alt_manager import AltManager
from src.ui.components.drag_drop_alt_dialog import DragDropAltDialog

class PagePanel(CollapsiblePanel):
    reload_requested = pyqtSignal()

    def __init__(self, parent=None, model:ReaderModel=None, on_page_changed=None):
        super().__init__(parent, "Page")
        self.thumbnails_layout.setSpacing(0)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(2)
        self.model = model
        self.on_page_changed = on_page_changed
        self.page_thumbnail_widgets = []
        self.current_page_thumbnails = []
        self.edit_selected_indices: Set[int] = set()

        self.edit_selected_indices: Set[int] = set()
        
        self.BATCH_SIZE = 10
        self.image_paths_to_load = []
        self.current_batch_index = 0
        self.batch_timer = QTimer(self)
        self.batch_timer.setSingleShot(True)
        self.batch_timer.timeout.connect(self._add_next_thumbnail_batch)
        
        self.navigate_first.connect(self._go_first)
        self.navigate_prev.connect(self._go_prev)
        self.navigate_next.connect(self._go_next)
        self.navigate_last.connect(self._go_last)
        
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste) or (event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V):
            self._paste_as_alternate()
            event.accept()
            return
        super().keyPressEvent(event)

    def _go_first(self):
        if self.model:
            self.on_page_changed(1)

    def _go_prev(self):
        if self.model:
            current = self.model.current_index + 1
            if current > 1:
                self.on_page_changed(current - 1)

    def _go_next(self):
        if self.model:
            current = self.model.current_index + 1
            if current < len(self.model.images):
                self.on_page_changed(current + 1)

    def _go_last(self):
        if self.model:
            self.on_page_changed(len(self.model.images))

    def showEvent(self, event):
        super().showEvent(event)
        if self.model:
             # Defer the snap slightly to ensure layout is ready
            QTimer.singleShot(50, lambda: self._update_page_selection(self.model.current_index))

    def _load_thumbnail(self, path: str):
        if '|' in path:
            return load_thumbnail_from_virtual_path(path, 150, 200)
        else:
            return load_thumbnail_from_path(path, 150, 200)

    def stop_loading_thumbnails(self):
        self.batch_timer.stop()
        self.thread_pool.clear()
        self.image_paths_to_load = []
        
    def _update_page_thumbnails(self, model:ReaderModel):
        self.batch_timer.stop()
        
        while self.thumbnails_layout.count():
            item = self.thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.page_thumbnail_widgets.clear()
        self.edit_selected_indices.clear()

        images = model.images
        if model.view_mode == ViewMode.DOUBLE:
            images = model._get_double_view_images()

        self.image_paths_to_load = images
        self.current_batch_index = 0
        
        if self.image_paths_to_load:
            self.batch_timer.start(50) # Start loading the first batch

    def _add_next_thumbnail_batch(self):
        start_index = self.current_batch_index
        end_index = min(start_index + self.BATCH_SIZE, len(self.image_paths_to_load))

        # Disable updates to prevent flicker and unnecessary layout calcs during batch
        self.content_area.setUpdatesEnabled(False)
        try:
            for i in range(start_index, end_index):
                page_obj = self.image_paths_to_load[i]
                
                thumb_label = str(i + 1)
                alt_count = 0
                if page_obj and page_obj != "placeholder":
                    alt_count = len(page_obj.images)
                
                widget = PageThumbnail(i, thumb_label, alt_count=alt_count)
                widget.clicked.connect(self._on_thumbnail_clicked)
                widget.right_clicked.connect(self._on_thumbnail_right_clicked)
                
                self.thumbnails_layout.insertWidget(i, widget)
                self.page_thumbnail_widgets.append(widget)

                if page_obj is None or page_obj == "placeholder":
                     self._on_page_thumbnail_loaded(i, empty_placeholder())
                else:
                    worker = ThumbnailWorker(i, page_obj.path, self._load_thumbnail)
                    worker.signals.finished.connect(self._on_page_thumbnail_loaded)
                    self.thread_pool.start(worker)
        except Exception as e:
            print(f"Error adding batch: {e}")
        finally:
            self.content_area.setUpdatesEnabled(True)

        self.current_batch_index = end_index
        if self.current_batch_index < len(self.image_paths_to_load):
            self.batch_timer.start(50) # Schedule the next batch

        should_snap = (start_index <= self.model.current_index < end_index)
        self._update_page_selection(self.model.current_index, snap=should_snap)

    def _on_page_thumbnail_loaded(self, index, pixmap):
        if index < len(self.page_thumbnail_widgets):
            self.page_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_page_selection(self, index, snap=True):
        for thumbnail in self.current_page_thumbnails:
            thumbnail.set_selected(False)
        self.current_page_thumbnails.clear()

        if index >= len(self.page_thumbnail_widgets):
            return

        # Select new thumbnail(s)
        if self.model.view_mode == ViewMode.DOUBLE:
            current_thumb = self.page_thumbnail_widgets[index]
            current_thumb.set_selected(True)
            self.current_page_thumbnails.append(current_thumb)
            if snap:
                self.content_area.scrollToWidget(current_thumb)

            if index + 1 < len(self.page_thumbnail_widgets):
                next_thumb = self.page_thumbnail_widgets[index + 1]
                next_thumb.set_selected(True)
                self.current_page_thumbnails.append(next_thumb)
        else:
            current_thumb = self.page_thumbnail_widgets[index]
            current_thumb.set_selected(True)
            self.current_page_thumbnails.append(current_thumb)
            if snap:
                self.content_area.scrollToWidget(current_thumb)

    def _on_thumbnail_clicked(self, index: int):
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self._toggle_edit_selection(index)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            pass 
        else:
            if self.edit_selected_indices:
                self._clear_edit_selection()
            self.on_page_changed(index + 1)

    def _on_thumbnail_right_clicked(self, index: int):
        if index not in self.edit_selected_indices:
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.ControlModifier):
                self._clear_edit_selection()
            self._toggle_edit_selection(index, force_select=True)
        
        self._show_context_menu(index)

    def _toggle_edit_selection(self, index: int, force_select: bool = False):
        if index in self.edit_selected_indices and not force_select:
            self.edit_selected_indices.remove(index)
            self.page_thumbnail_widgets[index].set_edit_selected(False)
        else:
            self.edit_selected_indices.add(index)
            self.page_thumbnail_widgets[index].set_edit_selected(True)

    def _clear_edit_selection(self):
        for idx in self.edit_selected_indices:
            if idx < len(self.page_thumbnail_widgets):
                self.page_thumbnail_widgets[idx].set_edit_selected(False)
        self.edit_selected_indices.clear()

    def _show_context_menu(self, index: int):
        menu = QMenu(self)
        
        if len(self.edit_selected_indices) > 1:
            link_action = QAction("Link selected pages as Alternates", self)
            link_action.triggered.connect(self._link_selected_pages)
            menu.addAction(link_action)

        unlink_action = QAction("Unlink Page (Ungroup)", self)
        unlink_action.triggered.connect(lambda: self._unlink_page(index))
        menu.addAction(unlink_action)
        
        menu.addSeparator()
        
        paste_action = QAction("Paste as Alternate", self)
        paste_action.triggered.connect(self._paste_as_alternate)
        if not QApplication.clipboard().mimeData().hasUrls():
            paste_action.setEnabled(False)
        menu.addAction(paste_action)

        add_file_action = QAction("Add Alternate from File...", self)
        add_file_action.triggered.connect(self._add_alt_from_file)
        menu.addAction(add_file_action)

        add_dd_action = QAction("Add Alternates (Drag & Drop)...", self)
        add_dd_action.triggered.connect(lambda: self._open_drag_drop_dialog(index))
        menu.addAction(add_dd_action)

        
        menu.addSeparator()

        save_as_action = QAction("Save As...", self)
        save_as_action.triggered.connect(lambda: self._save_page_as(index))
        menu.addAction(save_as_action)
        
        open_explorer_action = QAction("Reveal in File Explorer", self)
        open_explorer_action.triggered.connect(lambda: self._open_in_explorer(index))
        menu.addAction(open_explorer_action)

        menu.exec(QCursor.pos())

    def _save_page_as(self, index: int):
        page = self.model.images[index]
        if not page:
            return
            
        # Get the path of the main image (first variant)
        # Avoid saving virtual paths (zips) directly unless we extract? 
        # For now, assume path is extractable or handle standard files.
        src_path = page.images[0]
        if '|' in src_path:
             # Virtual path (e.g. zip). We might not support saving directly from zip without extraction.
             # But ReaderView extracts it. Here we have just path.
             # For simplicity, if it's zip, we skip or show error (or maybe just block it).
             # Wait, copying a file out of zip requires extraction.
             # Let's assume standard file for now as 'Save As' implies file copy.
             # If it's inside zip, src_path is like /path/to/archive.zip|internal/path.jpg
             pass
        
        path_to_save = src_path
        if '|' in path_to_save:
             # Logic to extract from zip if needed?
             # For now, let's just support local filesystem files to match behavior.
             return

        if not os.path.exists(path_to_save):
            return

        base_name = os.path.basename(path_to_save)
        ext = os.path.splitext(base_name)[1]
        
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        initial_path = os.path.join(downloads_dir, base_name)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image As",
            initial_path,
            f"Image (*{ext});;All Files (*)"
        )
        
        if file_path:
            try:
                shutil.copy2(path_to_save, file_path)
            except Exception as e:
                print(f"Error copying image: {e}")

    def _link_selected_pages(self):
        if len(self.edit_selected_indices) < 2:
            return
        
        sorted_indices = sorted(list(self.edit_selected_indices))
        main_page_idx = sorted_indices[0]
        
        main_page = self.model.images[main_page_idx]
        if not main_page: return

        all_paths = []
        for idx in sorted_indices:
            page = self.model.images[idx]
            if page:
                all_paths.extend(page.images)

        unique_paths = []
        seen = set()
        for p in all_paths:
            if p not in seen:
                unique_paths.append(p)
                seen.add(p)
        
        series_path = self.model.series['path']
        chapter_dir = Path(self.model.manga_dir) # Ensure we have chapter dir
        chapter_name = chapter_dir.name
        
        main_file = unique_paths[0]
        original_alt_files = unique_paths[1:]
        
        main_stem = Path(main_file).stem
        
        # Move alts to alts/ folder
        alts_dir = chapter_dir / "alts"
        if not alts_dir.exists():
            alts_dir.mkdir(parents=True, exist_ok=True)
            
        final_alt_files = []
        for i, alt_path in enumerate(original_alt_files):
            p = Path(alt_path)
            new_name = f"{main_stem}_{i+1}{p.suffix}"
            dst = alts_dir / new_name

            counter = i + 1
            while dst.exists() and dst.resolve() != p.resolve():
                new_name = f"{main_stem}_{counter}_{uuid.uuid4().hex[:4]}{p.suffix}"
                dst = alts_dir / new_name
            
            if alts_dir in p.parents and p.name == new_name:
                final_alt_files.append(str(p))
            else:
                try:
                    shutil.move(p, dst)
                    final_alt_files.append(str(dst))
                except Exception as e:
                    print(f"Error moving alt {p}: {e}")
                    final_alt_files.append(str(p))
        
        AltManager.link_pages(series_path, chapter_name, main_file, final_alt_files)
        
        self.reload_requested.emit()
        self.on_page_changed(main_page_idx + 1)

    def _unlink_page(self, index: int):
        page = self.model.images[index]
        if not page: return
        
        series_path = self.model.series['path']
        chapter_dir = Path(self.model.manga_dir)
        if isinstance(chapter_dir, str): chapter_dir = Path(chapter_dir)
        chapter_name = chapter_dir.name
        
        current_file_path = Path(page.path)
        
        # Check if we are unlinking the main page (images[0]) or an alt
        main_file_path = Path(page.images[0])
        is_main_file = (current_file_path.resolve() == main_file_path.resolve())
        
        # 1. Update JSON Configuration
        # If main file: remove the entire key (dissolve group)
        # If alt file: remove just that alt from the list
        AltManager.unlink_page(series_path, chapter_name, str(current_file_path))
        
        # 2. Rename files to _detached
        files_to_rename = []
        
        if is_main_file:
            # If main was selected, we dissolved the group. 
            # We should rename ALL alts (images[1:]) to _detached.
            # Convert paths to Path objects
            files_to_rename = [Path(p) for p in page.images if Path(p).resolve() != main_file_path.resolve()]
        else:
            # Only rename the current alt we just detached
            files_to_rename = [current_file_path]
            
        for p in files_to_rename:
            # Only rename if it's in the 'alts/' directory (standard behavior)
            if "alts" in str(p.parent.name):
                new_stem = f"{p.stem}_detached_{uuid.uuid4().hex[:8]}"
                new_name = f"{new_stem}{p.suffix}"
                # Rename in place
                dst_path = p.parent / new_name
                
                try:
                    shutil.move(p, dst_path)
                except Exception as e:
                    print(f"Error moving detached file: {e}")
        
        # Unlinking (detaching) a page means it is removed from the group but stays in alts folder (hidden from pages).
        # So no new page is added to the main list.
        # Thus, we can just update the variants.
        self.model.update_page_variants(index)

    def _paste_as_alternate(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        
        if not mime_data.hasUrls():
            return
            
        file_paths = [url.toLocalFile() for url in mime_data.urls()]
        self._add_alts_logic(file_paths)

    def _add_alt_from_file(self):
        default_dir = self.model.manga_dir if self.model else ""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Images/Videos", 
            str(default_dir), 
            "Media Files (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.webm *.mkv)"
        )
        if file_paths:
            self._add_alts_logic(file_paths)

    def _open_in_explorer(self, index: int):
        page = self.model.images[index]
        if not page:
             return
             
        # Resolve path if it's a virtual path (zip) or just a file
        # We want to highlight the file itself.
        path = page.images[0] # Use the first image (main)
        if '|' in path:
            path = path.split('|')[0] # Get the zip file path
            
        path = os.path.normpath(path)
        
        if os.name == 'nt':
            subprocess.Popen(['explorer', '/select,', str(path)])
        # elif os.name == 'posix': # Mac/Linux support if needed
        #     subprocess.Popen(['open', '-R', str(path)]) # Mac
        #     # Linux usually varies (xdg-open doesn't support select usually)

    def refresh_thumbnail(self, index: int):
        if 0 <= index < len(self.page_thumbnail_widgets):
            widget = self.page_thumbnail_widgets[index]
            page_obj = self.model.images[index]
            alt_count = len(page_obj.images) if page_obj else 0
            widget.set_alt_count(alt_count)

    def _open_drag_drop_dialog(self, index: int):
        dialog = DragDropAltDialog(self)
        if dialog.exec():
            files = dialog.get_files()
            if files:
                self._add_alts_logic(files, target_index=index)

    def _add_alts_logic(self, file_paths: list[str], target_index: int = -1):
        target_idx = target_index
        if target_idx == -1:
            if not self.edit_selected_indices:
                if self.model:
                    target_idx = self.model.current_index
                if target_idx == -1: return
            else:
                 target_idx = list(self.edit_selected_indices)[0]

        target_page = self.model.images[target_idx]
        if not target_page: return
        
        target_main_file = target_page.images[0] # Always link to the main file of the group
        
        chapter_dir = Path(self.model.manga_dir)
        alts_dir = chapter_dir / "alts"
        if not alts_dir.exists():
            try:
                alts_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                print(f"Error creating alts directory: {e}")
                return

        series_path = self.model.series['path']
        chapter_name = chapter_dir.name
        
        files_to_link = []
        main_stem = Path(target_main_file).stem
        start_index = len(target_page.images)
        if start_index < 1: start_index = 1

        for i, file_path in enumerate(file_paths):
            src_path = Path(file_path)
            if not src_path.exists(): continue
            
            new_name = f"{main_stem}_{start_index + i}{src_path.suffix}"
            dst_path = alts_dir / new_name
            
            # Verify no collision
            while dst_path.exists() and dst_path.resolve() != src_path.resolve():
                 new_name = f"{main_stem}_{start_index + i}_{uuid.uuid4().hex[:4]}{src_path.suffix}"
                 dst_path = alts_dir / new_name
            
            if src_path.resolve() == dst_path.resolve():
                files_to_link.append(str(dst_path))
                continue

            try:
                # Check if source is in the same directory as the target main file
                # If so, MOVE instead of COPY
                target_parent = Path(target_main_file).parent.resolve()
                src_parent = src_path.parent.resolve()
                
                # If src is in the same folder as main file (chapter folder), we MOVE it to alts.
                # If src is internal (same folder), we trigger granular update because we are effectively just organizing it?
                # Wait, if src is existing page in chapter, it's already in the page list. 
                # If we link it, it disappears from page list and becomes alt. That requires RELOAD.
                
                # BUT, this function (`_add_alts_logic`) handles "Add Alternate from File..." which implies external file or file selection dialog.
                # If user selects a file that is ALREADY a page in the reader (internal file), 
                # then `ReaderModel` needs to know to REMOVE it from pages list.
                
                # The prompt said: "when it is added from existing chapter... this case should be fully reloaded."
                # "but if it is an external directory... no new page is added... just an update to the image... not requiring a full reload."
                
                # So we need to detect if src_path is "internal" (already part of pages list implicitly or explicitly).
                # Simple check: Is src_path inside chapter_dir but NOT in alts dir? 
                # And is it one of the pages? (Ideally yes).
                
                is_internal = False
                if chapter_dir in src_path.parents:
                     # It is inside chapter dir.
                     if "alts" not in src_path.parts: # Not in alts folder
                         is_internal = True
                
                if src_parent == target_parent:
                     shutil.move(src_path, dst_path)
                else:
                     shutil.copy2(src_path, dst_path)
                     
                files_to_link.append(str(dst_path))
                
                if is_internal:
                    # If any file was internal, we must do full reload because a page (probably) disappeared from main list.
                    # We can't easily patch the pages list without full logic.
                    # So we set a flag.
                    pass 

            except Exception as e:
                print(f"Error processing file {src_path}: {e}")

        if files_to_link:
            AltManager.link_pages(series_path, chapter_name, target_main_file, files_to_link)
            
            # Check if we need full reload
            needs_full_reload = False
            for fp in file_paths:
                p = Path(fp)
                # If path was inside chapter dir and not in alts, it was likely a page.
                if chapter_dir.resolve() in p.resolve().parents:
                    # Check if it was in alts?
                    # If it was in alts, it wasn't a main page (usually). 
                    # But verifying 'internal' usually means it was a visible page.
                    if p.parent.name != "alts":
                        needs_full_reload = True
                        break
            
            if needs_full_reload:
                 self.reload_requested.emit()
            else:
                 self.model.update_page_variants(target_idx)
                 # self.refresh_thumbnail(target_idx) # Handled by signal connection in ReaderView?
                 # ReaderView connects model.page_updated to on_page_updated.
