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
        self.reader = easyocr.Reader(['ko', 'en'])

    def read_text(self, image):
        '''
        Reads text from an image file or image data.

        Args:
            image (str or numpy.ndarray): The path to the image file or the image data as a numpy array.

        Returns:
            list: A list of tuples, where each tuple contains the bounding box, the text, and the confidence score.
        '''
        return self.reader.readtext(image)

OCR_SINGLETON = OCRSingleton.get_instance()
