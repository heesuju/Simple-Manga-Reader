import os
import zipfile
from pathlib import Path

from PyQt6.QtCore import Qt, QRunnable, pyqtSlot, QObject, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QFont, QColor, QTextOption

from src.core.text_detector import TextDetector
from src.core.translator import Translator
from src.core.ocr import OCR
from PIL import Image, ImageQt
import io
from src.enums import Language
from src.core.alt_manager import AltManager

class TranslateSignals(QObject):
    finished = pyqtSignal(str, list) # path, overlays

class TranslateWorker(QRunnable):
    def __init__(self, image_path: str, target_lang: Language = Language.ENG):
        super().__init__()
        self.image_path = image_path
        self.target_lang = target_lang
        self.signals = TranslateSignals()

    @pyqtSlot()
    def run(self):
        try:
            print("Starting translation worker...")
            detector = TextDetector()
            # Initialize  lazily or here. It might take time to load model.
            try:
                ocr_engine = OCR()
            except Exception as e:
                print(f"OCR Init failed: {e}")
                self.signals.finished.emit([])
                return

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

            # Run Detection on the Full Image
            # YOLO expects file path or PIL Image
            if full_pil_img:
                detections = detector.detect(full_pil_img)
            else:
                detections = detector.detect(target_path)

            overlays = []
            
            for det in detections:
                bbox = det['bbox'] # [x, y, w, h] (top-left x, top-left y, width, height)
                
                # Perform OCR
                if full_pil_img:
                    x, y, w, h = bbox
                    # Crop the text bubble
                    # Ensure coordinates are within bounds
                    img_w, img_h = full_pil_img.size
                    x1 = max(0, int(x))
                    y1 = max(0, int(y))
                    x2 = min(img_w, int(x + w))
                    y2 = min(img_h, int(y + h))
                    
                    if x2 > x1 and y2 > y1:
                        crop = full_pil_img.crop((x1, y1, x2, y2))
                        try:
                            detected_text = ocr_engine.process(crop)
                            print(f"OCR: {detected_text}")
                        except Exception as e:
                            print(f"OCR failed for bubble: {e}")
                            detected_text = ""
                    else:
                        detected_text = ""
                else:
                    # If we don't have PIL image (e.g. video frame or something), skip OCR
                    detected_text = "" 

                if detected_text:
                    translated_text = translator.translate(detected_text, target_lang=self.target_lang)
                else:
                    translated_text = "[No Text Detected]"
                
                overlays.append({
                    'bbox': bbox,
                    'text': translated_text
                })
            
            # Emit overlays for immediate UI feedback (keep existing behavior)
            self.signals.finished.emit(self.image_path, overlays)

            # --- Save Translation as Alt ---
            if full_pil_img and overlays:
                try:
                    # Convert PIL Image to QImage for drawing
                    # (We already have full_pil_img loaded)
                    im_data = io.BytesIO()
                    full_pil_img.save(im_data, format='PNG')
                    q_img = QImage.fromData(im_data.getvalue())
                    
                    if q_img.isNull():
                        print("Failed to convert PIL image to QImage for saving.")
                        return

                    painter = QPainter(q_img)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                    
                    for overlay in overlays:
                        if not overlay['text'] or overlay['text'] == "[No Text Detected]":
                            continue
                            
                        x, y, w, h = overlay['bbox']
                        text = overlay['text']
                        
                        # Draw Background (White, Opaque)
                        painter.setBrush(QColor(255, 255, 255, 255))
                        painter.setPen(Qt.PenStyle.NoPen)
                        rect = QRectF(x, y, w, h)
                        painter.drawRect(rect)
                        
                        # Draw Text using QTextDocument for consistency with UI
                        from PyQt6.QtGui import QTextDocument, QTextCursor
                        
                        doc = QTextDocument()
                        doc.setHtml(text) # Or setPlainText, but UI uses QGraphicsTextItem which supports some HTML. 
                        # Actually QGraphicsTextItem uses setPlainText by default unless setHtml is called.
                        # In ImageViewer we use QGraphicsTextItem(text), which treats as plain text unless generic.
                        # Let's use setPlainText to be safe and match simple string.
                        doc.setPlainText(text)
                        
                        # Fix: Ensure text is black and opaque using text cursor and char format
                        cursor = QTextCursor(doc)
                        cursor.select(QTextCursor.SelectionType.Document)
                        fmt = cursor.charFormat()
                        fmt.setForeground(QColor("black"))
                        cursor.mergeCharFormat(fmt)
                        
                        opt = QTextOption()
                        opt.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
                        doc.setDefaultTextOption(opt)
                        
                        # Dynamic font sizing
                        font_size = 30 # Start max
                        min_font_size = 6
                        font = QFont("Arial", font_size)
                        
                        final_font_size = min_font_size
                        
                        # Iteratively find best fit
                        for size in range(font_size, min_font_size - 1, -2):
                            font.setPointSize(size)
                            doc.setDefaultFont(font)
                            doc.setTextWidth(w)
                            
                            if doc.size().height() <= h:
                                final_font_size = size
                                break
                                
                        font.setPointSize(final_font_size)
                        doc.setDefaultFont(font)
                        doc.setTextWidth(w)
                        
                        # Center vertically
                        doc_h = doc.size().height()
                        y_offset = (h - doc_h) / 2
                        if y_offset < 0: y_offset = 0
                        
                        painter.save()
                        painter.translate(x, y + y_offset)
                        doc.drawContents(painter)
                        painter.restore()
                            
                    painter.end()
                    
                    # Determine Save Path
                    # Logic assumes we are working with standard file paths (not zips) for saving new files.
                    # If original is zip, we save to a sidecar folder if possible, or fail if read-only.
                    # self.image_path could be "C:/.../chapter/image.jpg" or "C:/.../full.zip|image.jpg"
                    
                    original_file_path = ""
                    if '|' in self.image_path:
                        # Zip case: "C:/.../chapter.zip|img.jpg"
                        # We need a place to save. Default to "chapter_name_translations"?
                        # For now, let's assume the user is using Folders as implied by "make another directory on chapter"
                        # If ZIP, we can't easily add a directory "on chapter".
                        # We'll skip saving for ZIPs to avoid complexity/errors unless tasked.
                        print("Skipping save for ZIP archive.")
                        return 
                    else:
                        original_file_path = self.image_path
                        
                    original_path = Path(original_file_path)
                    chapter_dir = original_path.parent
                    translations_dir = chapter_dir / "translations"
                    translations_dir.mkdir(parents=True, exist_ok=True)
                    
                    lang_suffix = self.target_lang.value # "ENG", "KOR"
                    new_filename = f"{original_path.stem}_{lang_suffix}.jpg"
                    save_path = translations_dir / new_filename
                    
                    q_img.save(str(save_path), "JPG")
                    
                    # Register with AltManager
                    # link_pages(series_path, chapter_name, main_file, alt_files)
                    # series_path: chapter_dir.parent
                    series_path = chapter_dir.parent
                    chapter_name = chapter_dir.name
                    
                    AltManager.link_pages(str(series_path), chapter_name, str(original_path), [str(save_path)])
                    print(f"Saved translated page to {save_path}")

                except Exception as e:
                    print(f"Error saving translated image: {e}")
                    import traceback
                    traceback.print_exc()

            # self.signals.finished.emit(overlays) # Already emitted above
            
        except Exception as e:
            print(f"Error in translation worker: {e}")
            import traceback
            traceback.print_exc()
            self.signals.finished.emit(self.image_path, [])
