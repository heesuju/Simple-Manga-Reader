
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, 
                             QHBoxLayout, QFrame, QWidget, QMessageBox, QProgressBar, QFormLayout, QLineEdit, QCheckBox)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from src.core.llm_server import LLMServerManager

class DownloadWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def run(self):
        try:
            self.manager._ensure_model()
            self.finished.emit(True, "Download Complete")
        except Exception as e:
            self.finished.emit(False, str(e))

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedWidth(400)
        self.manager = LLMServerManager.instance()
        self.setup_ui()
        self.check_status()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("AI Configuration")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Server Status
        self.status_container = QFrame()
        self.status_container.setStyleSheet("background-color: #2b2b2b; border-radius: 5px; padding: 10px;")
        status_layout = QVBoxLayout(self.status_container)
        
        self.status_label = QLabel("Checking status...")
        self.status_label.setStyleSheet("font-size: 14px;")
        status_layout.addWidget(self.status_label)
        
        self.path_label = QLabel(f"Path: {self.manager.llama_cpp_dir}")
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.path_label.setWordWrap(True)
        status_layout.addWidget(self.path_label)

        # Action Buttons Layout
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 5, 0, 0)
        
        self.action_btn = QPushButton("Action")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0; 
                color: #000000; 
                border: none; 
                padding: 5px 10px; 
                border-radius: 3px; 
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffffff;
            }
        """)
        self.action_btn.clicked.connect(self.on_action_clicked)
        self.action_btn.hide()
        action_layout.addWidget(self.action_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff5252; 
                color: white; 
                border: none; 
                padding: 5px 10px; 
                border-radius: 3px; 
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff8a80;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_server)
        self.stop_btn.hide()
        action_layout.addWidget(self.stop_btn)
        
        status_layout.addLayout(action_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Infinite loading
        self.progress_bar.hide()
        status_layout.addWidget(self.progress_bar)

        layout.addWidget(self.status_container)
        
        # Config Section
        config_container = QFrame()
        config_container.setStyleSheet("background-color: #2b2b2b; border-radius: 5px; padding: 10px; margin-top: 10px;")
        config_layout = QFormLayout(config_container)
        
        self.repo_input = QLineEdit(self.manager.repo_id)
        self.repo_input.setPlaceholderText("Hugging Face Repo ID")
        self.repo_input.setStyleSheet("background-color: #3b3b3b; color: white; border: 1px solid #555; padding: 5px;")
        
        self.model_input = QLineEdit(self.manager.model_name)
        self.model_input.setPlaceholderText("GGUF Filename")
        self.model_input.setStyleSheet("background-color: #3b3b3b; color: white; border: 1px solid #555; padding: 5px;")
        
        self.port_input = QLineEdit(str(self.manager.port))
        self.port_input.setPlaceholderText("Port (e.g. 8080)")
        self.port_input.setStyleSheet("background-color: #3b3b3b; color: white; border: 1px solid #555; padding: 5px;")

        self.auto_start_check = QCheckBox("Automatically start server on startup")
        self.auto_start_check.setChecked(getattr(self.manager, 'auto_start', False))
        
        config_layout.addRow("Repo ID:", self.repo_input)
        config_layout.addRow("Filename:", self.model_input)
        config_layout.addRow("Port:", self.port_input)
        config_layout.addRow(self.auto_start_check)
        
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px; border-radius: 3px;")
        save_layout.addWidget(save_btn)
        config_layout.addRow(save_layout)
        
        layout.addWidget(config_container)

        layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def save_config(self):
        repo_id = self.repo_input.text().strip()
        model_name = self.model_input.text().strip()
        port = self.port_input.text().strip()
        auto_start = self.auto_start_check.isChecked()
        
        if not repo_id or not model_name or not port:
            QMessageBox.warning(self, "Invalid Config", "Please enter Repo ID, Model Name, and Port.")
            return

        if not port.isdigit():
             QMessageBox.warning(self, "Invalid Config", "Port must be a number.")
             return

        was_running = self.manager.is_running()
        self.manager.save_config(repo_id, model_name, port, auto_start)
        
        if was_running:
            if self.manager.is_model_present():
                # Restart to apply new port/model
                self.restart_server()
                QMessageBox.information(self, "Saved", "Configuration saved. Server triggering restart...")
            else:
                # Stop because new model is missing, can't restart yet
                self.manager.stop()
                QMessageBox.warning(self, "Server Stopped", "Configuration saved, but new model is missing.\nPlease download the model to restart.")
        else:
             QMessageBox.information(self, "Saved", "Configuration saved.")
             
        self.check_status()

    def check_status(self):
        self.action_btn.hide()
        self.stop_btn.hide()
        self.progress_bar.hide()
        
        if not self.manager.is_installed():
            self.status_label.setText("❌ llama.cpp not found")
            self.status_label.setStyleSheet("color: #ff6b6b; font-size: 14px; font-weight: bold;")
            self.path_label.setText(f"Missing executable at:\n{self.manager.server_exe}")
            return

        if not self.manager.is_model_present():
            self.status_label.setText("⚠️ Model missing")
            self.status_label.setStyleSheet("color: #ffd93d; font-size: 14px; font-weight: bold;")
            self.action_btn.setText("Download Model")
            self.action_btn.show()
            self.action_btn.clicked.disconnect()
            self.action_btn.clicked.connect(self.download_model)
            return

        if self.manager.is_running():
            self.status_label.setText("✅ Server is Running")
            self.status_label.setStyleSheet("color: #6bff6b; font-size: 14px; font-weight: bold;")
            self.action_btn.setText("Restart")
            self.action_btn.show()
            self.action_btn.clicked.disconnect()
            self.action_btn.clicked.connect(self.restart_server)
            
            self.stop_btn.show()
        else:
            self.status_label.setText("⭕ Server Stopped")
            self.status_label.setStyleSheet("color: #aaa; font-size: 14px; font-weight: bold;")
            self.action_btn.setText("Start Server")
            self.action_btn.show()
            self.action_btn.clicked.disconnect()
            self.action_btn.clicked.connect(self.start_server)

    def download_model(self):
        self.action_btn.hide()
        self.stop_btn.hide()
        self.progress_bar.show()
        self.status_label.setText("Downloading model...")
        
        self.worker = DownloadWorker(self.manager)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.start()

    def on_download_finished(self, success, msg):
        self.progress_bar.hide()
        if success:
            QMessageBox.information(self, "Success", "Model downloaded successfully.")
            self.check_status()
            # Auto start if possible
            self.start_server()
        else:
            QMessageBox.critical(self, "Error", f"Download failed: {msg}")
            self.check_status()

    def start_server(self):
        self.manager.start()
        # Give it a moment to start/fail
        QTimer.singleShot(500, self.check_status)

    def stop_server(self):
        self.manager.stop()
        QTimer.singleShot(500, self.check_status)

    def restart_server(self):
        self.manager.stop()
        QTimer.singleShot(1000, self.start_server)

    def on_action_clicked(self):
        pass
