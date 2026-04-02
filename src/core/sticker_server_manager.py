import os
import sys
import subprocess
import json
import base64
import time
from io import BytesIO
from pathlib import Path

import requests
from PyQt6.QtCore import QObject, pyqtSignal


class StickerServerManager(QObject):
    _instance = None
    status_changed = pyqtSignal(str)  # "running", "stopped", "error"

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.server_script = self.project_root / "sticker_server.py"
        self.config_path = self.project_root / "sticker_config.json"
        self.port = 8083
        self.process = None
        self._load_config()

    # ── Config ───────────────────────────────────────────────────────────────

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    self.port = config.get("port", self.port)
            except Exception as e:
                print(f"Failed to load sticker config: {e}")

    def save_config(self, port: int):
        self.port = int(port)
        try:
            with open(self.config_path, "w") as f:
                json.dump({"port": self.port}, f, indent=4)
            self.emit_status()
        except Exception as e:
            print(f"Failed to save sticker config: {e}")

    # ── Status ───────────────────────────────────────────────────────────────

    def emit_status(self):
        if not self.server_script.exists():
            self.status_changed.emit("error")
            return
        if self.is_running():
            self.status_changed.emit("running")
        else:
            self.status_changed.emit("stopped")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        if self.is_running():
            self.emit_status()
            return

        if not self.server_script.exists():
            print(f"Sticker server script not found: {self.server_script}")
            self.status_changed.emit("error")
            return

        cmd = [sys.executable, str(self.server_script), str(self.port)]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self.project_root),
            )
            print(f"Sticker server started (PID {self.process.pid}) on port {self.port}")
            self.status_changed.emit("running")
        except Exception as e:
            print(f"Failed to start sticker server: {e}")
            self.status_changed.emit("error")

    def stop(self):
        if self.process:
            print(f"Stopping sticker server (PID {self.process.pid})...")
            if os.name == "nt":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(self.process.pid)])
            else:
                import signal
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait()
            self.process = None
            print("Sticker server stopped.")
        self.status_changed.emit("stopped")

    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def check_health(self) -> bool:
        try:
            r = requests.get(f"http://localhost:{self.port}/health", timeout=1)
            return r.status_code == 200
        except requests.RequestException:
            return False

    # ── Sticker API ──────────────────────────────────────────────────────────

    def make_sticker(self, pil_image, border: int = 8, auto_start: bool = True):
        """
        Send a PIL image to the sticker server.
        Returns a PIL RGBA image (transparent background, white border), or None on failure.
        """
        from PIL import Image

        if not self.is_running():
            if auto_start:
                self.start()
                for _ in range(60):
                    time.sleep(0.5)
                    if self.check_health():
                        break
                else:
                    print("Sticker server did not become ready in time.")
                    return None
            else:
                return None

        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        try:
            resp = requests.post(
                f"http://localhost:{self.port}/sticker",
                json={"image": b64, "border": border},
                timeout=60,
            )
            result_b64 = resp.json().get("image")
            if not result_b64:
                print(f"Sticker server error: {resp.json().get('error')}")
                return None
            img_bytes = base64.b64decode(result_b64)
            return Image.open(BytesIO(img_bytes)).convert("RGBA")
        except Exception as e:
            print(f"Sticker server request failed: {e}")
            return None
