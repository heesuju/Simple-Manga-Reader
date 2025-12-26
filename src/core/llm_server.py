
import os
import subprocess
import signal
import time
import requests
from pathlib import Path
from huggingface_hub import hf_hub_download

class LLMServerManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LLMServerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return
        self.initialized = True
        
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.llama_cpp_dir = self.project_root / "llama.cpp"
        self.models_dir = self.llama_cpp_dir / "models"
        self.model_name = "jan-nano-4b-Q4_K_M.gguf"
        self.model_path = self.models_dir / self.model_name
        self.port = 8080
        self.process = None

        # Executable name depends on OS
        if os.name == 'nt':
            self.server_exe = self.llama_cpp_dir / "llama-server.exe"
        else:
            self.server_exe = self.llama_cpp_dir / "llama-server"

    def _ensure_model(self):
        """Check if model exists, download if not."""
        if not self.models_dir.exists():
            self.models_dir.mkdir(parents=True, exist_ok=True)

        if not self.model_path.exists():
            print(f"Model not found at {self.model_path}. Downloading...")
            try:
                repo_id = "Menlo/Jan-nano-gguf"
                download_path = hf_hub_download(repo_id=repo_id, filename=self.model_name, local_dir=str(self.models_dir))
                print(f"Model downloaded to {download_path}")
            except Exception as e:
                print(f"Failed to download model: {e}")

    def start(self):
        """Start the llama-server subprocess."""
        if self.is_running():
            print("LLM Server is already running.")
            return

        self._ensure_model()

        if not self.server_exe.exists():
            print(f"Error: llama-server executable not found at {self.server_exe}")
            return

        if not self.model_path.exists():
            print(f"Error: Model file not found at {self.model_path}")
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
