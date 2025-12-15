from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon
from src.enums import ViewMode

class AltSelector(QWidget):
    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        self.model = model
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            AltSelector {
                background-color: rgba(0, 0, 0, 170);
                color: white;
                border-radius: 5px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 3px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 60);
            }
            QPushButton:checked {
                background-color: rgba(50, 200, 255, 180);
                border: 1px solid rgba(50, 200, 255, 200);
            }
        """)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        self.play_icon = QIcon("assets/icons/play.png")
        self.pause_icon = QIcon("assets/icons/pause.png") # Keep pause icon for potential future use or if it's used elsewhere
        # Store state as {page_index: {'speed_idx': 0, 'timer': QTimer}}
        self.slideshow_states = {} 
        self.speeds = [2000, 1000, 500, 250] # ms intervals
        self.speed_labels = ["x1", "x2", "x4", "x8"]

        self.hide()

        if self.model:
            self.model.image_loaded.connect(self._on_image_loaded)
            self.model.double_image_loaded.connect(self._on_double_image_loaded)

    def _clear_buttons(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _on_image_loaded(self, path):
        # Single view
        self._update_selector(self.model.current_index)

    def _on_double_image_loaded(self, path1, path2):
        # Double view: Show selector for current page(s) if they have alts.
        # This is a bit complex. Where do we put the selector? 
        # For simplicity, maybe just show selector for the first page that has alts?
        # Or two selectors?
        # Let's start with supporting the "current_index" page logic. 
        # In double view, current_index points to left/right page depending on logic.
        # But we might see two pages.
        
        # Current simplified logic: Only show selector for the primary current index.
        # (Enhancement: Support multiple selectors or a combined one later)
        self._update_selector(self.model.current_index)

    def _update_selector(self, primary_index):
        self._clear_buttons()
        
        if not self.model or not self.model.images:
            self.hide()
            # Stop all timers if no images
            for state in self.slideshow_states.values(): state['timer'].stop()
            self.slideshow_states.clear()
            return

        indices_to_check = [primary_index]
        if self.model.view_mode == ViewMode.DOUBLE:
            # Check next page too
            if primary_index + 1 < len(self.model.images):
                indices_to_check.append(primary_index + 1)
        
        # Stop timers for pages that are no longer visible
        active_indices = set(self.slideshow_states.keys())
        visible_indices = set(indices_to_check)
        for idx in active_indices - visible_indices:
            self.slideshow_states[idx]['timer'].stop()
            del self.slideshow_states[idx]

        has_variants = False
        
        # We might need a vertical layout if we have multiple pages with variants
        # But AltSelector inherits QWidget and uses QHBoxLayout self.layout.
        # Let's switch to QVBoxLayout if we want rows, or just pack them horizontally with separators.
        # Pack horizontally: "P1: [1][2] | P2: [1][2]"
        
        for idx in indices_to_check:
            if not (0 <= idx < len(self.model.images)):
                continue
            
            page = self.model.images[idx]
            if len(page.images) > 1:
                has_variants = True
                
                # Separator if needed
                if self.layout.count() > 0:
                     sep = QLabel("|")
                     sep.setStyleSheet("color: rgba(255,255,255,100); margin: 0 5px;")
                     self.layout.addWidget(sep)
                
                # Determine state
                is_playing = idx in self.slideshow_states
                
                # Play Button
                play_btn = QPushButton()
                play_btn.setFixedSize(50, 24) # Wider for text
                play_btn.setCheckable(True)
                play_btn.setChecked(is_playing)
                
                if is_playing:
                    state = self.slideshow_states[idx]
                    speed_idx = state['speed_idx']
                    play_btn.setText(self.speed_labels[speed_idx])
                    # No icon when playing, just text to show speed? Or both?
                    # User said "changes icon to x1.5 x2". Since QIcon text is hard, let's use text on button.
                else:
                    play_btn.setIcon(self.play_icon)
                
                play_btn.clicked.connect(lambda checked, p_idx=idx: self._on_play_clicked(p_idx))
                self.layout.addWidget(play_btn)

                for i, variant_path in enumerate(page.images):
                    btn = QPushButton(str(i + 1))
                    btn.setFixedSize(24, 24)
                    btn.setCheckable(True)
                    
                    # Determine type for styling
                    import os
                    ext = os.path.splitext(variant_path)[1].lower()
                    is_gif = ext == '.gif'
                    is_video = ext in {'.mp4', '.webm', '.mkv', '.avi', '.mov'}
                    
                    style = ""
                    if is_video:
                        style = "border-color: #03A9F4; color: #03A9F4;" # Light Blue
                        btn.setToolTip("Video")
                    elif is_gif:
                        style = "border-color: #E040FB; color: #E040FB;" # Purple
                        btn.setToolTip("Animated GIF")
                    else:
                        btn.setToolTip("Image")

                    if style:
                        # Append to existing stylesheet logic or set directly
                        # Since we have a global sheet, we need to be careful.
                        # Setting specific style on widget overrides generic sheet for those properties.
                        btn.setStyleSheet(style)

                    # If playing, variants are NOT checked (Play is the "selected" mode)
                    if not is_playing and i == page.current_variant_index:
                        btn.setChecked(True)
                    
                    # Use closure to capture index
                    btn.clicked.connect(lambda checked, p_idx=idx, v_idx=i: self._on_variant_clicked(p_idx, v_idx))
                    self.layout.addWidget(btn)

        if has_variants:
            # Only show if parent says panels are visible
            if hasattr(self.parent(), "panels_visible"):
                if self.parent().panels_visible:
                    self.show()
                else:
                    self.hide() # Ensure hidden if panels are hidden (though usually already hidden)
            else:
                self.show()
        else:
            self.hide()

    def _on_play_clicked(self, page_index):
        if page_index not in self.slideshow_states:
            # Start slideshow
            timer = QTimer(self)
            timer.timeout.connect(lambda: self._advance_variant(page_index))
            timer.start(self.speeds[0])
            self.slideshow_states[page_index] = {'speed_idx': 0, 'timer': timer}
        else:
            # Cycle speed
            state = self.slideshow_states[page_index]
            new_speed_idx = (state['speed_idx'] + 1) % len(self.speeds)
            state['speed_idx'] = new_speed_idx
            state['timer'].setInterval(self.speeds[new_speed_idx])
            
        self._update_selector(self.model.current_index)

    def _advance_variant(self, page_index):
        if not self.model or not (0 <= page_index < len(self.model.images)):
            return

        page = self.model.images[page_index]
        new_variant_index = (page.current_variant_index + 1) % len(page.images)
        self.model.change_variant(page_index, new_variant_index)

    def _on_variant_clicked(self, page_index, variant_index):
        if self.model:
            # Stop slideshow if checking a variant
            if page_index in self.slideshow_states:
                self.slideshow_states[page_index]['timer'].stop()
                del self.slideshow_states[page_index]
            
            self.model.change_variant(page_index, variant_index)
            # _update_selector is called automatically via model.image_loaded signal.
            # No need to call it explicitly here.

