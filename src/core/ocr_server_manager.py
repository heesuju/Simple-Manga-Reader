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


class OCRServerManager(QObject):
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
        self.server_script = self.project_root / "ocr_server.py"
        self.config_path = self.project_root / "ocr_config.json"
        self.port = 8082
        self.process = None
        self._load_config()

    # ── Config ──────────────────────────────────────────────────────────────

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    self.port = config.get('port', self.port)
            except Exception as e:
                print(f"Failed to load OCR config: {e}")

    def save_config(self, port: int):
        self.port = int(port)
        try:
            with open(self.config_path, 'w') as f:
                json.dump({'port': self.port}, f, indent=4)
            self.emit_status()
        except Exception as e:
            print(f"Failed to save OCR config: {e}")

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
            print(f"OCR server script not found: {self.server_script}")
            self.status_changed.emit("error")
            return

        cmd = [sys.executable, str(self.server_script), str(self.port)]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        try:
            self.process = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self.project_root),
            )
            print(f"OCR server started (PID {self.process.pid}) on port {self.port}")
            self.status_changed.emit("running")
        except Exception as e:
            print(f"Failed to start OCR server: {e}")
            self.status_changed.emit("error")

    def stop(self):
        if self.process:
            print(f"Stopping OCR server (PID {self.process.pid})...")
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:
                import signal
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait()
            self.process = None
            print("OCR server stopped.")
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

    # ── OCR API ──────────────────────────────────────────────────────────────

    def detect(self, pil_image, auto_start: bool = True) -> list:
        """
        Send a PIL image to the OCR server.
        Returns list of dicts: [{'bbox': [x,y,w,h], 'text': str, 'class': str}]
        Sorted top-to-bottom, right-to-left (reading order for manga).
        """
        if not self.is_running():
            if auto_start:
                self.start()
                # Wait for server to be ready (up to 30 s — model load takes time)
                for _ in range(60):
                    time.sleep(0.5)
                    if self.check_health():
                        break
                else:
                    print("OCR server did not become ready in time.")
                    return []
            else:
                return []

        buf = BytesIO()
        pil_image.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()

        try:
            resp = requests.post(
                f"http://localhost:{self.port}/ocr",
                json={"image": b64},
                timeout=120,
            )
            results = resp.json().get('results', [])
            # Sort: top-to-bottom then right-to-left
            results.sort(key=lambda d: (d['bbox'][1], -d['bbox'][0]))
            return results
        except Exception as e:
            print(f"OCR server request failed: {e}")
            return []
