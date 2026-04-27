import json
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage

from src.ui.viewer.base_viewer import BaseViewer
from src.utils.resource_utils import resource_path


class L2DPage(QWebEnginePage):
    """QWebEnginePage subclass that intercepts MODEL_ANIMATIONS/MODEL_SLOTS console messages."""
    animations_loaded = pyqtSignal(list)
    slots_loaded = pyqtSignal(list)
    bones_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.featurePermissionRequested.connect(self.handle_feature_permission)

    def handle_feature_permission(self, url, feature):
        if feature == QWebEnginePage.Feature.MouseLock:
            self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        print(f"L2D_JS [{lineNumber}]: {message}")
        if message.startswith('MODEL_ANIMATIONS:'):
            try:
                self.animations_loaded.emit(json.loads(message[len('MODEL_ANIMATIONS:'):]))
            except Exception:
                pass
        elif message.startswith('MODEL_SLOTS:'):
            try:
                self.slots_loaded.emit(json.loads(message[len('MODEL_SLOTS:'):]))
            except Exception:
                pass
        elif message.startswith('BONES_TOGGLED:'):
            self.bones_toggled.emit(message.endswith('true'))


class L2DViewer(BaseViewer):
    animations_loaded = pyqtSignal(list)
    slots_loaded = pyqtSignal(list)
    bones_toggled = pyqtSignal(bool)

    def __init__(self, reader_view):
        super().__init__(reader_view)
        self._pending_url = None
        self._page_ready = False
        self._current_version = None

        web_view = reader_view.model_web_view
        if web_view is not None:
            self.page = L2DPage(web_view)

    def set_active(self, active: bool):
        super().set_active(active)
        web_view = self.reader_view.model_web_view
        if web_view is None:
            return
        if active:
            self.reader_view.media_stack.hide()
            self.reader_view.scroll_area.hide()
            
            if web_view.page() is not self.page:
                web_view.setPage(self.page)
                try:
                    self.page.animations_loaded.disconnect(self.animations_loaded)
                    self.page.slots_loaded.disconnect(self.slots_loaded)
                    self.page.bones_toggled.disconnect(self.bones_toggled)
                except Exception:
                    pass
                self.page.animations_loaded.connect(self.animations_loaded)
                self.page.slots_loaded.connect(self.slots_loaded)
                self.page.bones_toggled.connect(self.bones_toggled)
                self._page_ready = False
                
            web_view.show()
        else:
            web_view.hide()
            self.reader_view.media_stack.show()

    def _detect_spine_version(self, path: str) -> str:
        try:
            with open(path, 'rb') as f:
                data = f.read(100)
                if b'3.8.' in data:
                    return '3.8'
                if b'4.0.' in data:
                    return '4.0'
                if b'4.1.' in data or b'4.2.' in data:
                    return '4.1'
        except Exception:
            pass
        return '4.1'  # Default to newer

    def load(self, path: str):
        web_view = self.reader_view.model_web_view
        if web_view is None or not path:
            return

        try:
            model_url = QUrl.fromLocalFile(path).toString()
        except Exception as e:
            print(f'L2DViewer: cannot process path {path}: {e}')
            return

        self._pending_url = model_url
        version = self._detect_spine_version(path)
        print(version)

        if self._page_ready and web_view.page() is self.page and self._current_version == version:
            self._inject(web_view)
        else:
            self._current_version = version
            self._page_ready = False
            try:
                web_view.loadFinished.disconnect(self._on_load_finished)
            except Exception:
                pass
            web_view.loadFinished.connect(self._on_load_finished)
            if version == '3.8':
                html_file = 'src/ui/viewer/l2d/viewer_38.html'
            elif version == '4.0':
                html_file = 'src/ui/viewer/l2d/viewer_40.html'
            else:
                html_file = 'src/ui/viewer/l2d/viewer_41.html'
            html_path = resource_path(html_file)
            web_view.setUrl(QUrl.fromLocalFile(html_path))

    def _inject(self, web_view):
        if self._pending_url is None:
            return
        url_json = json.dumps(self._pending_url)
        js = (
            '(function poll(){'
            '  if(typeof window.loadModel==="function"){'
            f'    window.loadModel({url_json});'
            '  }else{'
            '    setTimeout(poll,50);'
            '  }'
            '})();'
        )
        web_view.page().runJavaScript(js)
        self._pending_url = None

    def _on_load_finished(self, ok: bool):
        web_view = self.reader_view.model_web_view
        try:
            web_view.loadFinished.disconnect(self._on_load_finished)
        except Exception:
            pass
        if ok:
            self._page_ready = True
            self._inject(web_view)

    def play_animation(self, index: int):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            web_view.page().runJavaScript(f'window.playAnimation({index})')
            self.reader_view.top_strip._anim_play_btn.setChecked(False)
            self.reader_view.top_strip._anim_play_btn.setText("⏸")

    def set_anim_paused(self, paused: bool):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            val = 'true' if paused else 'false'
            web_view.page().runJavaScript(f'window.setAnimPaused({val})')

    def set_slot_visible(self, slot_name: str, visible: bool):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            val = 'true' if visible else 'false'
            web_view.page().runJavaScript(f'window.setSlotVisible({json.dumps(slot_name)},{val})')

    def set_show_bones(self, visible: bool):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            val = 'true' if visible else 'false'
            web_view.page().runJavaScript(f'window.setShowBones({val})')

    def set_neighbor_count(self, n: int):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            web_view.page().runJavaScript(f'window.setNeighborCount({n})')

    def set_bounce_force(self, n: int):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            web_view.page().runJavaScript(f'window.setBounceForce({n})')

    def set_premultiplied_alpha(self, enabled: bool):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            val = 'true' if enabled else 'false'
            web_view.page().runJavaScript(f'window.setPremultipliedAlpha({val})')

    def highlight_slot(self, slot_name: str):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            web_view.page().runJavaScript(f'window.highlightSlot({json.dumps(slot_name)})')

    def clear_highlight(self):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            web_view.page().runJavaScript('window.clearHighlight()')

    def reset(self):
        web_view = self.reader_view.model_web_view
        if web_view and web_view.page() is self.page:
            try:
                web_view.loadFinished.disconnect(self._on_load_finished)
            except Exception:
                pass
            web_view.setHtml('')
        self._page_ready = False
        self._pending_url = None
        self._current_version = None

    def zoom(self, mode: str):
        pass

    def cleanup(self):
        self.reset()
