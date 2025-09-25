'''
This module provides a singleton class for EasyOCR reader.
'''
import easyocr

class OCRSingleton:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.reader = easyocr.Reader(['en', 'es'])

    def read_text(self, image_path):
        '''
        Reads text from an image file.

        Args:
            image_path (str): The path to the image file.

        Returns:
            list: A list of tuples, where each tuple contains the bounding box, the text, and the confidence score.
        '''
        return self.reader.readtext(image_path)

OCR_SINGLETON = OCRSingleton.get_instance()
