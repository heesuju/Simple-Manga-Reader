import base64
import json
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage

from src.ui.viewer.base_viewer import BaseViewer
from src.utils.resource_utils import resource_path

_MIME = {'.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json'}


class ModelPage(QWebEnginePage):
    """QWebEnginePage subclass that intercepts MODEL_ANIMATIONS/MODEL_MESHES console messages."""
    animations_loaded = pyqtSignal(list)
    meshes_loaded     = pyqtSignal(list)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        if message.startswith('MODEL_ANIMATIONS:'):
            try:
                self.animations_loaded.emit(json.loads(message[len('MODEL_ANIMATIONS:'):]))
            except Exception:
                pass
        elif message.startswith('MODEL_MESHES:'):
            try:
                self.meshes_loaded.emit(json.loads(message[len('MODEL_MESHES:'):]))
            except Exception:
                pass


class ModelViewer(BaseViewer):
    animations_loaded = pyqtSignal(list)
    meshes_loaded     = pyqtSignal(list)

    def __init__(self, reader_view):
        super().__init__(reader_view)
        self._pending_url = None
        self._page_ready = False

        web_view = reader_view.model_web_view
        if web_view is not None:
            page = ModelPage(web_view)
            web_view.setPage(page)
            page.animations_loaded.connect(self.animations_loaded)
            page.meshes_loaded.connect(self.meshes_loaded)

    def set_active(self, active: bool):
        super().set_active(active)
        web_view = self.reader_view.model_web_view
        if web_view is None:
            return
        if active:
            self.reader_view.media_stack.hide()
            self.reader_view.scroll_area.hide()
            web_view.show()
        else:
            web_view.hide()
            self.reader_view.media_stack.show()

    def load(self, path: str):
        web_view = self.reader_view.model_web_view
        if web_view is None or not path:
            return

        ext = Path(path).suffix.lower()
        mime = _MIME.get(ext, 'model/gltf-binary')
        try:
            with open(path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('ascii')
            model_url = f'data:{mime};base64,{encoded}'
        except Exception as e:
            print(f'ModelViewer: cannot read {path}: {e}')
            return

        self._pending_url = model_url

        if self._page_ready:
            self._inject(web_view)
        else:
            try:
                web_view.loadFinished.disconnect(self._on_load_finished)
            except Exception:
                pass
            web_view.loadFinished.connect(self._on_load_finished)
            html_path = resource_path('src/ui/viewer/model_viewer.html')
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
        if web_view:
            web_view.page().runJavaScript(f'window.playAnimation({index})')
            self.reader_view.top_strip._anim_play_btn.setChecked(False)
            self.reader_view.top_strip._anim_play_btn.setText("⏸")

    def set_mesh_visible(self, name: str, visible: bool):
        web_view = self.reader_view.model_web_view
        if web_view:
            val = 'true' if visible else 'false'
            name_json = json.dumps(name)
            web_view.page().runJavaScript(f'window.setMeshVisible({name_json},{val})')

    def set_anim_paused(self, paused: bool):
        web_view = self.reader_view.model_web_view
        if web_view:
            val = 'true' if paused else 'false'
            web_view.page().runJavaScript(f'window.setAnimPaused({val})')

    def reset(self):
        web_view = self.reader_view.model_web_view
        if web_view:
            try:
                web_view.loadFinished.disconnect(self._on_load_finished)
            except Exception:
                pass
            web_view.setHtml('')
        self._page_ready = False
        self._pending_url = None

    def zoom(self, mode: str):
        pass

    def cleanup(self):
        self.reset()
