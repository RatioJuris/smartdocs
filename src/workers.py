"""
Ratio Juris Smart Scanner - Background Thread Workers
Prevents application locking during visual data pipelines.
"""

import os
import logging
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class DocumentProcessingWorker(QThread):
    """
    Handles asynchronous reading (including PDFs), corner detection, and image formatting.
    """
    # Emits: cv_image, corner_points, file_path_reference, original_extension
    result_ready = Signal(np.ndarray, np.ndarray, str, str) 
    error_occurred = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from core_processing import ImageProcessor
            
            ext = os.path.splitext(self.file_path)[1].lower()
            
            if ext == ".pdf":
                if not HAS_FITZ:
                    raise ImportError("PyMuPDF (fitz) is required to import PDFs. Run: pip install pymupdf")
                
                doc = fitz.open(self.file_path)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(dpi=200)
                    
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    cv_img = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
                    
                    corners = ImageProcessor.auto_detect_corners(cv_img)
                    pseudo_path = f"{self.file_path} - Page {page_num + 1}"
                    self.result_ready.emit(cv_img, corners, pseudo_path, ".pdf")
                doc.close()
                
            else:
                img_array = np.fromfile(self.file_path, np.uint8)
                cv_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if cv_img is None:
                    raise ValueError("Could not decode image array structure safely.")
                    
                corners = ImageProcessor.auto_detect_corners(cv_img)
                self.result_ready.emit(cv_img, corners, self.file_path, ext if ext else ".png")
                
        except Exception as e:
            logging.error(f"Error handling file execution thread: {str(e)}")
            self.error_occurred.emit(str(e))