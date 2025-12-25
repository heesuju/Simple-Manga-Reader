from typing import Set, List
from PyQt6.QtCore import QThreadPool, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QMenu, QApplication, QFileDialog
from PyQt6.QtGui import QAction, QCursor, QKeySequence

from src.ui.base.collapsible_panel import CollapsiblePanel
from src.ui.page_thumbnail import PageThumbnail
from src.workers.thumbnail_worker import ThumbnailWorker
from src.data.reader_model import ReaderModel
from src.enums import ViewMode
from src.utils.img_utils import empty_placeholder, load_thumbnail_from_path, load_thumbnail_from_virtual_path
from src.core.alt_manager import AltManager
from src.ui.components.drag_drop_alt_dialog import DragDropAltDialog
import src.ui.page_utils as page_utils

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
        self.click_map = [] # Map thumbnail index -> real page index
        
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
        self.content_area.installEventFilter(self)

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
        self.click_map.clear()

        if model.view_mode == ViewMode.DOUBLE:
            # Reconstruct visual list from layout pairs
            # Layout Pair: (Left, Right)
            # Visual Strip (assuming standard reading dir? Or just LTR strip?)
            # If RTL reading: Pair is [LeftPage, RightPage].
            # Previous logic showed [RightMap, LeftMap].
            # So we add Right, then Left.
            
            display_items = []
            
            # _layout_pairs is [(LeftItem, RightItem), ...]
            for pair in model._layout_pairs:
                left, right = pair
                
                # Add Right then Left (RTL visual order)
                # Filter out None (Spread empty slot)
                
                # Pairs to process in order
                items = [right, left]
                
                for item in items:
                    if item is None: continue
                    
                    display_items.append(item)
                    
                    # Calculate Target Index using O(1) lookup
                    target_idx = -1
                    if isinstance(item, str) and item == "placeholder":
                        # Map to partner
                        partner = left if item is right else right
                        if partner and hasattr(partner, 'path'): # Is Page
                             target_idx = model.get_page_index(partner.path)
                    elif hasattr(item, 'path'): # Is Page
                        target_idx = model.get_page_index(item.path)
                        
                    self.click_map.append(target_idx)
            
            self.image_paths_to_load = display_items

        else:
            self.image_paths_to_load = model.images
            # 1-to-1 map
            self.click_map = list(range(len(model.images)))


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
                # If we want label to match REAL page number?
                if i < len(self.click_map) and self.click_map[i] != -1:
                    thumb_label = str(self.click_map[i] + 1)
                elif page_obj == "placeholder":
                    thumb_label = ""
                
                alt_count = 0
                if hasattr(page_obj, 'images'):
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

        # Initial selection update - needs mapping from real current_index to thumbnail index
        # We can find thumbnail index that maps to current_index
        if self.model:
            self._update_page_selection(self.model.current_index, snap=True)


    def _on_page_thumbnail_loaded(self, index, pixmap):
        if index < len(self.page_thumbnail_widgets):
            self.page_thumbnail_widgets[index].set_pixmap(pixmap)

    def _update_page_selection(self, index, snap=True):
        for thumbnail in self.current_page_thumbnails:
            thumbnail.set_selected(False)
        self.current_page_thumbnails.clear()

        # Find all thumbnails that map to 'index' or 'index+1' (if double)??
        # The logic is: highlight the thumbnail(s) corresponding to currently visible pages.
        # In ReaderView Double, visible items are from _layout_pairs[current_layout].
        # We need to find which THUMBNAILS correspond to the visible pages.
        
        # Simpler: Find all i where click_map[i] == index?
        # Yes.
        
        indices_to_select = []
        
        # If double view, ReaderView might display index AND index+1 (if pair).
        # Actually ReaderView current_index is enough to define state.
        # But we need to know what pages are actually visible.
        # ReaderModel _get_current_layout_index -> Layout Pair.
        # Pair contains Pages.
        # We find thumbnails matching those Pages.
        
        visible_pages = []
        if self.model and self.model.images:
             if hasattr(self.model, 'view_mode') and self.model.view_mode == ViewMode.DOUBLE:
                  layout_idx = self.model._get_current_layout_index()
                  if layout_idx != -1 and layout_idx < len(self.model._layout_pairs):
                       l, r = self.model._layout_pairs[layout_idx]
                       if l and hasattr(l, 'path'): visible_pages.append(l)
                       if r and hasattr(r, 'path'): visible_pages.append(r)
                       # Also include placeholders if they map to visible pages?
                       # Or just select visible page thumbnails.
             else:
                  if 0 <= index < len(self.model.images):
                      visible_pages.append(self.model.images[index])
        
        # Find partial matches in image_paths_to_load
        for i, obj in enumerate(self.image_paths_to_load):
            if obj in visible_pages:
                indices_to_select.append(i)
            elif obj == "placeholder":
                # If placeholder logic: select it if its partner is visible?
                # or if it maps to visible page?
                if i < len(self.click_map):
                    mapped_idx = self.click_map[i]
                    # If mapped_idx corresponds to a visible page
                    # Mapping is index -> RealIdx.
                    # visible_pages contains Page objects.
                    # Convert to RealIndices
                    visible_indices = [self.model.images.index(p) for p in visible_pages]
                    if mapped_idx in visible_indices:
                        indices_to_select.append(i)

        for i in indices_to_select:
             if i < len(self.page_thumbnail_widgets):
                 w = self.page_thumbnail_widgets[i]
                 w.set_selected(True)
                 self.current_page_thumbnails.append(w)
                 if snap and i == indices_to_select[0]: # Snap to first
                     self.content_area.scrollToWidget(w)


    def _on_thumbnail_clicked(self, index: int):
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self._toggle_edit_selection(index)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            pass 
        else:
            if self.edit_selected_indices:
                self._clear_edit_selection()
            
            # Use Click Map
            if index < len(self.click_map):
                real_idx = self.click_map[index]
                if real_idx != -1:
                    self.on_page_changed(real_idx + 1)

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
        page_utils.save_page_as(self, self.model, index)

    def _link_selected_pages(self):
        page_utils.link_selected_pages(
            self.model, 
            self.edit_selected_indices, 
            lambda: self.reload_requested.emit(), 
            self.on_page_changed
        )

    def _unlink_page(self, index: int):
        page_utils.unlink_page(self.model, index)

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
        page_utils.open_in_explorer(self.model, index)

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

    def _add_alts_logic(self, file_paths: List[str], target_index: int = -1):
        target_idx = target_index
        if target_idx == -1:
            if not self.edit_selected_indices:
                if self.model:
                    target_idx = self.model.current_index
                if target_idx == -1: return
            else:
                 target_idx = list(self.edit_selected_indices)[0]

        page_utils.process_add_alts(
            self.model,
            file_paths,
            target_idx,
            lambda: self.reload_requested.emit(),
            lambda idx: self.model.update_page_variants(idx)
        )
    def eventFilter(self, source, event):
        if source == self.content_area and event.type() == event.Type.KeyPress and self.is_expanded:
            if event.key() == Qt.Key.Key_Up:
                self.navigate_flow_grid(-1, self.page_thumbnail_widgets, self.model.current_index, lambda idx: self.on_page_changed(idx + 1))
                return True
            elif event.key() == Qt.Key.Key_Down:
                self.navigate_flow_grid(1, self.page_thumbnail_widgets, self.model.current_index, lambda idx: self.on_page_changed(idx + 1))
                return True
        return super().eventFilter(source, event)
