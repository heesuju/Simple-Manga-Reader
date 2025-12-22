import os
import shutil
from huggingface_hub import hf_hub_download
from ultralytics import YOLO
import torch

class TextDetector:
    _model_cache = None

    def __init__(self, model_name="ogkalu/comic-text-segmenter-yolov8m"):
        self.model_name = model_name
        self.model_path = os.path.join("models", "comic-text-segmenter-yolov8m.pt")
        self._ensure_model()
        self._load_model()
        # Check device availability once
        self.device = 0 if torch.cuda.is_available() else 'cpu'
        print(f"TextDetector initialized on device: {self.device}")

    def _ensure_model(self):
        """Check if model exists, if not download from HF."""
        if not os.path.exists("models"):
            os.makedirs("models")
        
        if not os.path.exists(self.model_path):
            print(f"Model not found at {self.model_path}. Downloading from Hugging Face...")
            try:
                # The model filename in the repo might be 'best.pt' or similar.
                downloaded_path = hf_hub_download(repo_id=self.model_name, filename="comic-text-segmenter.pt")
                shutil.copy(downloaded_path, self.model_path)
                print("Model downloaded successfully.")
            except Exception as e:
                print(f"Error downloading model: {e}")
                pass

    def _load_model(self):
        if TextDetector._model_cache:
            self.model = TextDetector._model_cache
            return

        if os.path.exists(self.model_path):
            # User specifically asked for CPU support.
            print(f"Loading YOLO model from {self.model_path}...")
            self.model = YOLO(self.model_path)
            TextDetector._model_cache = self.model
        else:
            print("Model file missing. Detection will fail.")
            self.model = None

    def detect(self, image_path: str):
        """
        Run inference on the image.
        Returns a list of dicts: {'bbox': [x, y, w, h], 'text': '', 'class': 'text'}
        """
        if not self.model:
            return []

        results = self.model.predict(image_path, device=self.device, conf=0.25)
        
        detections = []
        for result in results:
            boxes = result.boxes.cpu().numpy()
            for box in boxes:
                r = box.xywh[0] # x_center, y_center, width, height
                cls = int(box.cls[0])
                
                # YOLO format is x_center, y_center, w, h. 
                # We often want top-left x, y for drawing.
                x_center, y_center, w, h = r
                x = x_center - w / 2
                y = y_center - h / 2
                
                detections.append({
                    'bbox': [float(x), float(y), float(w), float(h)],
                    'text': '', 
                    'class': 'text_bubble' 
                })
        return detections
