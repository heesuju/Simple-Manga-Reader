
import os
import subprocess
import signal
import time
import requests
from pathlib import Path
from huggingface_hub import hf_hub_download
import json

from PyQt6.QtCore import QObject, pyqtSignal

class LLMServerManager(QObject):
    _instance = None
    status_changed = pyqtSignal(str)

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.llama_cpp_dir = self.project_root / "llama.cpp"
        self.models_dir = self.llama_cpp_dir / "models"
        
        self.config_path = self.project_root / "llm_config.json"
        self.repo_id = "Menlo/Jan-nano-gguf"
        self.model_name = "jan-nano-4b-Q4_K_M.gguf"
        
        self.load_config()

        self.port = 8080
        self.process = None

        # Executable name depends on OS
        if os.name == 'nt':
            self.server_exe = self.llama_cpp_dir / "llama-server.exe"
        else:
            self.server_exe = self.llama_cpp_dir / "llama-server"

        self.is_downloading = False

    @property
    def model_path(self):
        return self.models_dir / self.model_name

    def load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    self.repo_id = config.get('repo_id', self.repo_id)
                    self.model_name = config.get('model_name', self.model_name)
                    self.port = config.get('port', self.port)
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save_config(self, repo_id, model_name, port):
        self.repo_id = repo_id
        self.model_name = model_name
        self.port = int(port)
        config = {
            'repo_id': self.repo_id,
            'model_name': self.model_name,
            'port': self.port
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
            # Re-emit status since model path might have changed
            self.emit_status()
        except Exception as e:
            print(f"Failed to save config: {e}")

    def emit_status(self):
        """Emits the current status."""
        if self.is_downloading:
            self.status_changed.emit("downloading")
            return

        if not self.is_installed():
            self.status_changed.emit("error_install")
            return

        if not self.is_model_present():
            self.status_changed.emit("error_model")
            return

        if self.is_running():
            self.status_changed.emit("running")
        else:
            self.status_changed.emit("stopped")

    def _ensure_model(self):
        """Check if model exists, download if not. BLOCKING."""
        if not self.models_dir.exists():
            self.models_dir.mkdir(parents=True, exist_ok=True)

        if not self.model_path.exists():
            print(f"Model not found at {self.model_path}. Downloading...")
            try:
                self.is_downloading = True
                self.emit_status()
                
                print(f"Downloading {self.model_name} from {self.repo_id}...")
                download_path = hf_hub_download(repo_id=self.repo_id, filename=self.model_name, local_dir=str(self.models_dir))
                print(f"Model downloaded to {download_path}")
            except Exception as e:
                print(f"Failed to download model: {e}")
            finally:
                self.is_downloading = False
                self.emit_status()

    def start(self):
        """Start the llama-server subprocess."""
        if self.is_running():
            print("LLM Server is already running.")
            self.emit_status()
            return

        if not self.server_exe.exists():
            print(f"Error: llama-server executable not found at {self.server_exe}")
            self.emit_status()
            return

        if not self.model_path.exists():
            print(f"Error: Model file not found at {self.model_path}")
            self.emit_status()
            return

        cmd = [
            str(self.server_exe),
            "-m", str(self.model_path),
            "--port", str(self.port),
            "--ctx-size", "2048", # Default context size, adjust as needed
            "--n-gpu-layers", "99" # Try to offload everything to GPU if possible
        ]

        print(f"Starting LLM Server: {' '.join(cmd)}")
        try:
            # Start process, redirect output to avoid cluttering main console or capture it
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            
            self.process = subprocess.Popen(
                cmd, 
                creationflags=creationflags,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            print(f"LLM Server started with PID {self.process.pid}")
            self.emit_status()
        except Exception as e:
            print(f"Failed to start LLM Server: {e}")

    def stop(self):
        """Stop the llama-server subprocess."""
        if self.process:
            print(f"Stopping LLM Server (PID {self.process.pid})...")
            if os.name == 'nt':
                # On Windows, terminate the process group
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
            else:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            
            self.process.wait()
            self.process = None
            print("LLM Server stopped.")
        self.emit_status()

    def is_installed(self):
        """Check if llama-server executable exists."""
        return self.server_exe.exists()
    
    def is_model_present(self):
        """Check if GGUF model exists."""
        return self.model_path.exists()

    def is_running(self):
        """Check if the server process is still running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def check_health(self):
        """Check if server is responding to HTTP requests."""
        try:
            response = requests.get(f"http://localhost:{self.port}/health", timeout=1)
            return response.status_code == 200
        except requests.RequestException:
            return False
