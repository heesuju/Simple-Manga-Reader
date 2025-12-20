
from manga_ocr import MangaOcr
from PIL import Image

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
            self.mocr = MangaOcr()
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
