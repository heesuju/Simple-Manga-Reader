
from manga_ocr import MangaOcr
from PIL import Image

import torch

class OCR:
    _model_cache = None

    def __init__(self):
        self._load_model()

    def _load_model(self):
        if OCR._model_cache:
            self.mocr = OCR._model_cache
            return
        
        # Initialize MangaOCR
        # This will download models if not present
        print("Initializing MangaOCR...")
        try:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"MangaOCR initializing on device: {device}")
            self.mocr = MangaOcr(device=device)
            OCR._model_cache = self.mocr
            print("MangaOCR initialized.")
        except Exception as e:
            print(f"Failed to initialize MangaOCR: {e}")
            raise e

    def process(self, image: Image.Image) -> str:
        """
        Run OCR on a PIL Image crop.
        """
        return self.mocr(image)
