import shutil
import os
from pathlib import Path
from typing import Set

from PyQt6.QtCore import QThreadPool, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QMenu, QApplication, QFileDialog
from PyQt6.QtGui import QAction, QCursor

from src.ui.base.collapsible_panel import CollapsiblePanel
from src.ui.page_thumbnail import PageThumbnail
from src.workers.thumbnail_worker import ThumbnailWorker
from src.data.reader_model import ReaderModel
from src.enums import ViewMode
from src.utils.img_utils import empty_placeholder, load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.core.alt_manager import AltManager

class PagePanel(CollapsiblePanel):
    reload_requested = pyqtSignal()

    def __init__(self, parent=None, model:ReaderModel=None, on_page_changed=None):
        super().__init__(parent, "Page")
        self.thumbnails_layout.setSpacing(0)
        self.thread_pool = QThreadPool()
        self.model = model
        self.on_page_changed = on_page_changed
        self.page_thumbnail_widgets = []
        self.current_page_thumbnails = []
        self.edit_selected_indices: Set[int] = set()

        self.BATCH_SIZE = 20
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
        if event.matches(QAction.StandardKey.Paste) or (event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V):
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
        
    def _update_page_thumbnails(self, model:ReaderModel):
        self.batch_timer.stop()
        
        for i in reversed(range(self.thumbnails_layout.count() - 1)):
            widget = self.thumbnails_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.page_thumbnail_widgets.clear()
        self.edit_selected_indices.clear()

        images = model.images
        if model.view_mode == ViewMode.DOUBLE:
            images = model._get_double_view_images()

        self.image_paths_to_load = images
        self.current_batch_index = 0
        
        if self.image_paths_to_load:
            self.batch_timer.start(10) # Start loading the first batch

    def _add_next_thumbnail_batch(self):
        start_index = self.current_batch_index
        end_index = min(start_index + self.BATCH_SIZE, len(self.image_paths_to_load))

        for i in range(start_index, end_index):
            page_obj = self.image_paths_to_load[i]
            
            thumb_label = str(i + 1)
            
            widget = PageThumbnail(i, thumb_label)
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

        self.current_batch_index = end_index
        if self.current_batch_index < len(self.image_paths_to_load):
            self.batch_timer.start(10) # Schedule the next batch

        self._update_page_selection(self.model.current_index)

    def _on_page_thumbnail_loaded(self, index, pixmap):
        if index < len(self.page_thumbnail_widgets):
            self.page_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_page_selection(self, index):
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
            self.content_area.snapToItemIfOutOfView(index)

            if index + 1 < len(self.page_thumbnail_widgets):
                next_thumb = self.page_thumbnail_widgets[index + 1]
                next_thumb.set_selected(True)
                self.current_page_thumbnails.append(next_thumb)
        else:
            current_thumb = self.page_thumbnail_widgets[index]
            current_thumb.set_selected(True)
            self.current_page_thumbnails.append(current_thumb)
            self.content_area.snapToItemIfOutOfView(index, current_thumb.width())

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

        menu.exec(QCursor.pos())

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
        chapter_name = Path(self.model.manga_dir).name
        
        main_file = unique_paths[0]
        alt_files = unique_paths[1:]
        
        AltManager.link_pages(series_path, chapter_name, main_file, alt_files)
        
        self.reload_requested.emit()
        self.on_page_changed(main_page_idx + 1)

    def _unlink_page(self, index: int):
        page = self.model.images[index]
        if not page: return
        
        series_path = self.model.series['path']
        chapter_name = Path(self.model.manga_dir).name
        
        current_file = page.path
        AltManager.unlink_page(series_path, chapter_name, current_file)
        
        self.reload_requested.emit()

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

    def _add_alts_logic(self, file_paths: list[str]):
        if not self.edit_selected_indices:
            target_idx = -1
            if self.edit_selected_indices:
                target_idx = list(self.edit_selected_indices)[0]
            elif self.model:
                target_idx = self.model.current_index
            
            if target_idx == -1: return
        else:
             target_idx = list(self.edit_selected_indices)[0]

        target_page = self.model.images[target_idx]
        if not target_page: return
        
        target_main_file = target_page.images[0] # Always link to the main file of the group
        
        chapter_dir = Path(self.model.manga_dir)
        series_path = self.model.series['path']
        chapter_name = chapter_dir.name
        
        files_to_link = []
        
        for file_path in file_paths:
            src_path = Path(file_path)
            if not src_path.exists(): continue
            
            # Check if inside chapter folder
            if chapter_dir in src_path.parents:
                files_to_link.append(str(src_path))
            else:
                # Copy
                dst_path = chapter_dir / src_path.name
                try:
                    shutil.copy2(src_path, dst_path)
                    files_to_link.append(str(dst_path))
                except Exception as e:
                    print(f"Error copying file {src_path}: {e}")

        if files_to_link:
            AltManager.link_pages(series_path, chapter_name, target_main_file, files_to_link)
            self.reload_requested.emit()