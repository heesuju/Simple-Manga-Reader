import os
import zipfile
from pathlib import Path
import io

from PyQt6.QtCore import Qt, QRunnable, pyqtSlot, QObject, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QFont, QColor, QTextOption, QTextDocument, QTextCursor

from src.core.translator import Translator
from src.core.ocr_server_manager import OCRServerManager
from PIL import Image, ImageQt
from src.enums import Language
from src.core.alt_manager import AltManager

class TranslateSignals(QObject):
    finished = pyqtSignal(str, str, list, str, list) # original_path, saved_path, overlays, lang_code, history
    started = pyqtSignal(str) # lang_code

class TranslateWorker(QRunnable):
    def __init__(self, image_path: str, series_path: str, chapter_name: str, target_lang: Language = Language.ENG, history: list = None, page_context: str = ""):
        super().__init__()
        self.image_path = image_path
        self.series_path = series_path
        self.chapter_name = chapter_name
        self.target_lang = target_lang
        self.history = history if history is not None else []
        self.page_context = page_context
        self.signals = TranslateSignals()

    @pyqtSlot()
    def run(self):
        saved_path_str = None
        overlays = []
        try:
            self.signals.started.emit(self.target_lang.value)
            print("Starting translation worker...")
            translator = Translator()
            
            target_path = self.image_path
            
            # Handle modifiers and pre-processing
            crop_mode = None
            if isinstance(target_path, str):
                if target_path.endswith("_left"):
                    target_path = target_path[:-5]
                    crop_mode = "left"
                elif target_path.endswith("_right"):
                    target_path = target_path[:-6]
                    crop_mode = "right"
            
            # Load full image for cropping later
            full_pil_img = None
            
            if isinstance(target_path, str) and ('|' in target_path or crop_mode):
                 from src.utils.img_utils import get_image_data_from_zip
                 
                 img_data = None
                 if '|' in target_path:
                     img_data = get_image_data_from_zip(target_path)
                 else:
                     with open(target_path, 'rb') as f:
                         img_data = f.read()
                 
                 if img_data:
                     try:
                         full_pil_img = Image.open(io.BytesIO(img_data)).convert('RGB')
                         
                         if crop_mode == 'left':
                             w, h = full_pil_img.size
                             full_pil_img = full_pil_img.crop((0, 0, w//2, h))
                         elif crop_mode == 'right':
                             w, h = full_pil_img.size
                             full_pil_img = full_pil_img.crop((w//2, 0, w, h))
                     except Exception as e:
                         print(f"Failed to load image from data: {e}")
            elif isinstance(target_path, str) and os.path.exists(target_path):
                 full_pil_img = Image.open(target_path).convert('RGB')
            else:
                 # Should fail gracefully or handle object
                 pass

            # Run detection + OCR via OCR server (returns sorted results)
            if full_pil_img:
                detections = OCRServerManager.instance().detect(full_pil_img)
            else:
                detections = []

            for det in detections:
                bbox = det['bbox']  # [x, y, w, h]
                detected_text = det.get('text', '')
                
                translated_text = ""
                if detected_text:
                    print(f"[OCR] Detected: {repr(detected_text)}")
                    try:
                        translated_text = translator.translate_contextual(detected_text, self.history, target_lang=self.target_lang, page_context=self.page_context)
                        print(f"[TL] Translated: {repr(translated_text)}")
                        # Append to history ONLY if translation succeeded
                        if translated_text:
                             self.history.append((detected_text, translated_text))
                        
                        # Limit history size if needed (handled in translator implicitly by slicing, but good to keep memory low)
                        if len(self.history) > 20:
                             self.history.pop(0)
                             
                    except Exception as e:
                        print(f"Translation failed: {e}")
                        # Abort the entire task on translation failure as per user request
                        raise e
                else:
                    translated_text = "[No Text Detected]"
                
                overlays.append({
                    'bbox': bbox,
                    'text': translated_text
                })
            
            # Painting must run on the main thread (QTextDocument is not thread-safe on Windows).
            # Emit overlays to the caller; the caller is responsible for compositing.
            self.signals.finished.emit(self.image_path, None, overlays, self.target_lang.value, self.history)
            
        except Exception as e:
            print(f"Error in translation worker: {e}")
            import traceback
            traceback.print_exc()
            self.signals.finished.emit(self.image_path, None, [], self.target_lang.value, self.history)


def paint_and_save_overlays(image_path: str, overlays: list, series_path: str, chapter_name: str, target_lang: Language) -> str | None:
    """
    Composite translated text overlays onto the source image and save.
    Must be called from the main thread — uses QTextDocument for text layout.
    Returns the saved file path, or None on failure.
    """
    has_translations = any(o['text'] and o['text'] != "[No Text Detected]" for o in overlays)
    if not has_translations or '|' in image_path:
        return None

    try:
        pil_img = Image.open(image_path).convert('RGB')
        im_data = io.BytesIO()
        pil_img.save(im_data, format='PNG')
        q_img = QImage.fromData(im_data.getvalue())

        if q_img.isNull():
            return None

        painter = QPainter(q_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        for overlay in overlays:
            if not overlay['text'] or overlay['text'] == "[No Text Detected]":
                continue

            x, y, w, h = overlay['bbox']
            text = overlay['text']

            # White background
            painter.setBrush(QColor(255, 255, 255, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(x, y, w, h))

            # Find largest font that fits using QTextDocument
            final_font_size = 6
            for size in range(30, 5, -2):
                doc = QTextDocument()
                doc.setPlainText(text)
                font = QFont("Arial", size)
                doc.setDefaultFont(font)
                doc.setTextWidth(w)
                opt = QTextOption()
                opt.setAlignment(Qt.AlignmentFlag.AlignCenter)
                opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
                doc.setDefaultTextOption(opt)
                cursor = QTextCursor(doc)
                cursor.select(QTextCursor.SelectionType.Document)
                fmt = cursor.charFormat()
                fmt.setForeground(QColor("black"))
                cursor.mergeCharFormat(fmt)
                if doc.size().height() <= h:
                    final_font_size = size
                    break

            doc = QTextDocument()
            doc.setPlainText(text)
            font = QFont("Arial", final_font_size)
            doc.setDefaultFont(font)
            doc.setTextWidth(w)
            opt = QTextOption()
            opt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            doc.setDefaultTextOption(opt)
            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = cursor.charFormat()
            fmt.setForeground(QColor("black"))
            cursor.mergeCharFormat(fmt)

            doc_h = doc.size().height()
            y_offset = max(0, (h - doc_h) / 2)
            painter.save()
            painter.translate(x, y + y_offset)
            doc.drawContents(painter)
            painter.restore()

        painter.end()

        original_path = Path(image_path)
        translations_dir = original_path.parent / "translations" / target_lang.value
        translations_dir.mkdir(parents=True, exist_ok=True)
        save_path = translations_dir / f"{original_path.stem}_{target_lang.value}.jpg"
        q_img.save(str(save_path), "JPG")

        AltManager.link_translation(series_path, chapter_name, image_path, target_lang, str(save_path))
        print(f"Saved translated page to {save_path}")
        return str(save_path)

    except Exception as e:
        print(f"Error painting translated image: {e}")
        import traceback
        traceback.print_exc()
        return None
