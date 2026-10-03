"""
Ratio Juris Smart Scanner - Production Application Engine Entry Point
"""

import sys
import os
import tempfile
import cv2
import numpy as np
import platform
from datetime import datetime
from PIL import Image

from PySide6.QtCore import Qt, QSize, QMimeData, QUrl
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap, QImage, QDrag, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QListWidget, QListWidgetItem, QPushButton, QComboBox, QSlider, 
    QLabel, QFileDialog, QMessageBox, QSplitter, QProgressBar, QGroupBox,
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QSplashScreen
)

from core_processing import ImageProcessor
from workers import DocumentProcessingWorker
from widgets import DocumentCropView

class ScanDocumentPage:
    def __init__(self, raw_cv_img: np.ndarray, corners: np.ndarray, orig_ext: str):
        self.raw_image = raw_cv_img
        self.corners = corners
        self.orig_ext = orig_ext
        self.enhancement_mode = "Original"
        self.brightness = 1.0
        self.contrast = 1.0
        self.sharpness = 1.0
        self.remove_bg = False

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SmartDocs System Settings")
        self.setMinimumWidth(400)
        
        layout = QFormLayout(self)
        self.btn_install_ctx = QPushButton("Install Windows Context Menu")
        self.btn_install_ctx.clicked.connect(self.install_context_menu)
        
        layout.addRow("OS Integration:", self.btn_install_ctx)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def install_context_menu(self):
        if platform.system() != "Windows":
            QMessageBox.warning(self, "Unsupported OS", "Context menu integration is only available on Windows.")
            return
            
        try:
            import winreg
            app_path = sys.executable if getattr(sys, 'frozen', False) else f'python "{os.path.abspath(sys.argv[0])}"'
            
            # Create cascade menu
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\*\shell\SmartDocs")
            winreg.SetValue(key, "", winreg.REG_SZ, "Smart Docs")
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "Smart Docs")
            winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "SmartDocs.Align;SmartDocs.RemBG;SmartDocs.Merge")
            
            # Commands
            cmds = {
                "SmartDocs.Align": ("Set Alignment", f'{app_path} --align "%1"'),
                "SmartDocs.RemBG": ("Remove Background", f'{app_path} --rembg "%1"'),
                "SmartDocs.Merge": ("Merge Files", f'{app_path} --merge "%1"')
            }
            
            for sub_key, (title, cmd) in cmds.items():
                k = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\CommandStore\\shell\\{sub_key}")
                winreg.SetValue(k, "", winreg.REG_SZ, title)
                cmd_k = winreg.CreateKey(k, "command")
                winreg.SetValue(cmd_k, "", winreg.REG_SZ, cmd)
                
            QMessageBox.information(self, "Success", "Context menu entries added successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Registry Error", f"Run as Administrator required.\n{str(e)}")


class DragExportWidget(QLabel):
    def __init__(self, scanner_ref):
        super().__init__("🖐️ Grab & Drag Here to Export")
        self.scanner = scanner_ref
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #2F2F2F; border: 2px dashed #505050; border-radius: 6px; padding: 20px; color: #007AFF; font-weight: bold;")
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.position()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        if not self.scanner.pages:
            return

        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        fmt = self.scanner.combo_export_format.currentText()
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        urls = []
        
        if fmt == "PDF" or self.scanner.cb_merge.isChecked():
            temp_path = os.path.join(temp_dir, f"smart_docs_{timestamp}.pdf")
            if self.scanner.build_pdf_silently(temp_path):
                urls.append(QUrl.fromLocalFile(temp_path))
        else:
            paths = self.scanner.build_images_silently(temp_dir, f"smart_docs_{timestamp}", fmt)
            urls = [QUrl.fromLocalFile(p) for p in paths]
            
        if urls:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls(urls)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
            
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class RatioJurisSplash(QSplashScreen):
    """Branded startup splash screen for Ratio Juris Smart Scanner."""

    def __init__(self):
        pixmap = QPixmap(760, 430)
        pixmap.fill(QColor("#121212"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Accent panel.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#007AFF"))
        painter.drawRoundedRect(34, 34, 692, 362, 18, 18)

        # Inner surface.
        painter.setBrush(QColor("#1E1E1E"))
        painter.drawRoundedRect(38, 38, 684, 354, 15, 15)

        painter.setPen(QColor("#FFFFFF"))
        title_font = QFont("Segoe UI", 28, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(70, 145, "RATIO JURIS")

        subtitle_font = QFont("Segoe UI", 18, QFont.Weight.DemiBold)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#D9E8FF"))
        painter.drawText(70, 185, "Smart Document Scanner")

        body_font = QFont("Segoe UI", 11)
        painter.setFont(body_font)
        painter.setPen(QColor("#AEB8C4"))
        painter.drawText(70, 225, "Document detection  •  Curve correction  •  Smart enhancement")

        # Loading indicator.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#007AFF"))
        painter.drawRoundedRect(70, 300, 620, 5, 2, 2)

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#7F8A96"))
        painter.drawText(70, 345, "Initialising scanner engine…")
        painter.drawText(70, 370, "Ratio Juris")

        painter.end()
        super().__init__(pixmap)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)


class RatioJurisSmartScanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ratio Juris Smart Document Scanner and Aligner")
        self.setMinimumSize(QSize(1200, 800))
        
        self.pages = []
        self.current_index = -1
        self.active_workers = []
        
        self.setup_menubar()
        self.init_ui()
        
        # Enable Global Drag & Drop for importing anywhere on the GUI
        self.setAcceptDrops(True)
        self.apply_theme()

    def setup_menubar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("📁 File")
        
        import_action = QAction("➕ Import Image(s)...", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(import_action)
        
        export_action = QAction("📥 Export Document...", self)
        export_action.setShortcut(QKeySequence("Ctrl+S"))
        export_action.triggered.connect(self.export_document)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("⚙️ Settings", self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("❌ Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        help_menu = menubar.addMenu("❓ Help")
        about_action = QAction("ℹ️ About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def show_about(self):
        QMessageBox.about(
            self, 
            "About Ratio Juris Smart Scanner",
            "<h3>Ratio Juris Smart Scanner</h3>"
            "<p><b>Version:</b> 1.0</p>"
            "<p><b>Developer:</b> Isrg Rajan</p>"
            "<p><b>Source Code:</b> <a href='https://github.com/RatioJuris/smartdocs'>https://github.com/RatioJuris/smartdocs</a></p>"
        )

    def init_ui(self):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)

        # Left Panel - Thumbnails
        left_panel = QWidget()
        left_vbox = QVBoxLayout(left_panel)
        left_vbox.addWidget(QLabel("<b>Document Assembly Pages:</b>"))
        
        self.page_list_widget = QListWidget()
        self.page_list_widget.setIconSize(QSize(100, 100))
        self.page_list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.page_list_widget.currentRowChanged.connect(self.load_selected_page)
        left_vbox.addWidget(self.page_list_widget)

        btn_import = QPushButton("➕ Import Image File(s)")
        btn_import.clicked.connect(self.open_file_dialog)
        left_vbox.addWidget(btn_import)
        
        btn_delete = QPushButton("🗑️ Remove Page")
        btn_delete.clicked.connect(self.delete_current_page)
        left_vbox.addWidget(btn_delete)
        main_splitter.addWidget(left_panel)

        # Center Panel - Canvas
        center_panel = QWidget()
        center_vbox = QVBoxLayout(center_panel)
        center_vbox.addWidget(QLabel("<b>Corner & Curve Calibration Canvas:</b>"))
        
        self.crop_viewer = DocumentCropView()
        self.crop_viewer.polygon_updated.connect(self.on_polygon_modified)
        center_vbox.addWidget(self.crop_viewer)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        center_vbox.addWidget(self.progress_bar)
        main_splitter.addWidget(center_panel)

        # Right Panel - Controls
        right_panel = QWidget()
        right_vbox = QVBoxLayout(right_panel)
        right_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        filter_group = QGroupBox("1. Real-Time Image Enhancement Presets")
        filter_layout = QVBoxLayout(filter_group)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Original", "Document/B&W", "Magic Color", "Grayscale"])
        self.combo_mode.currentTextChanged.connect(self.update_enhancements_pipeline)
        filter_layout.addWidget(self.combo_mode)
        
        self.cb_rm_bg = QCheckBox("✂️ Remove Background")
        self.cb_rm_bg.stateChanged.connect(self.update_enhancements_pipeline)
        filter_layout.addWidget(self.cb_rm_bg)
        right_vbox.addWidget(filter_group)

        tuning_group = QGroupBox("2. Continuous Fine-Tuning Controls")
        tuning_layout = QVBoxLayout(tuning_group)
        
        tuning_layout.addWidget(QLabel("Brightness Factor:"))
        self.slider_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_bright.setRange(5, 20) 
        self.slider_bright.setValue(10)
        self.slider_bright.sliderReleased.connect(self.update_enhancements_pipeline)
        tuning_layout.addWidget(self.slider_bright)

        tuning_layout.addWidget(QLabel("Contrast Matrix Factor:"))
        self.slider_contrast = QSlider(Qt.Orientation.Horizontal)
        self.slider_contrast.setRange(5, 20)
        self.slider_contrast.setValue(10)
        self.slider_contrast.sliderReleased.connect(self.update_enhancements_pipeline)
        tuning_layout.addWidget(self.slider_contrast)
        right_vbox.addWidget(tuning_group)

        export_group = QGroupBox("3. Export Output")
        export_layout = QVBoxLayout(export_group)
        
        export_layout.addWidget(QLabel("Output Format (Auto-Detect Default):"))
        self.combo_export_format = QComboBox()
        self.combo_export_format.addItems(["Default (Keep Original)", "PDF", "PNG", "JPEG"])
        export_layout.addWidget(self.combo_export_format)
        
        self.cb_merge = QCheckBox("🔗 Merge Files into Single PDF")
        export_layout.addWidget(self.cb_merge)
        
        btn_compile = QPushButton("📥 Export Project Document")
        btn_compile.setStyleSheet("background-color: #007AFF; color: white; font-weight: bold; padding: 10px; margin-top: 5px;")
        btn_compile.clicked.connect(self.export_document)
        export_layout.addWidget(btn_compile)
        
        export_layout.addSpacing(10)
        self.drag_export_box = DragExportWidget(self)
        export_layout.addWidget(self.drag_export_box)
        right_vbox.addWidget(export_group)

        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([200, 600, 300])

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1E1E1E; }
            QWidget { color: #E0E0E0; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; }
            QMenuBar { background-color: #2F2F2F; color: white; }
            QMenuBar::item:selected { background-color: #3D3D3D; }
            QMenu { background-color: #2F2F2F; color: white; border: 1px solid #3A3A3A; }
            QMenu::item:selected { background-color: #007AFF; }
            QGroupBox { font-weight: bold; border: 1px solid #3A3A3A; border-radius: 6px; margin-top: 12px; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
            QPushButton { background-color: #2F2F2F; border: 1px solid #3A3A3A; border-radius: 4px; padding: 6px 12px; color: #FFFFFF; }
            QPushButton:hover { background-color: #3D3D3D; }
            QPushButton:pressed { background-color: #505050; }
            QListWidget { background-color: #121212; border: 1px solid #2A2A2A; border-radius: 4px; }
            QComboBox { background-color: #2F2F2F; border: 1px solid #3A3A3A; border-radius: 4px; padding: 4px; color: white; }
            QSlider::groove:horizontal { border: 1px solid #3A3A3A; height: 4px; background: #2F2F2F; border-radius: 2px; }
            QSlider::handle:horizontal { background: #007AFF; width: 14px; margin: -5px 0; border-radius: 7px; }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp')):
                self.process_input_file(file_path)

    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Document Images/PDFs", "", "Supported Files (*.pdf *.png *.jpg *.jpeg *.tiff *.bmp *.webp)"
        )
        for f in files:
            self.process_input_file(f)

    def process_input_file(self, file_path: str):
        self.progress_bar.setVisible(True)
        worker = DocumentProcessingWorker(file_path)
        self.active_workers.append(worker)
        
        worker.result_ready.connect(self.on_worker_success)
        worker.error_occurred.connect(self.on_worker_failure)
        worker.finished.connect(lambda w=worker: self.cleanup_worker(w))
        worker.start()
        
    def cleanup_worker(self, worker):
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        worker.deleteLater()
        if not self.active_workers:
            self.progress_bar.setVisible(False)

    def on_worker_success(self, cv_img: np.ndarray, corners: np.ndarray, path: str, ext: str):
        page = ScanDocumentPage(cv_img, corners, ext)
        self.pages.append(page)
        
        item = QListWidgetItem(os.path.basename(path))
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        item.setIcon(QIcon(QPixmap.fromImage(q_img).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio)))
        
        self.page_list_widget.addItem(item)
        self.page_list_widget.setCurrentRow(len(self.pages) - 1)

    def on_worker_failure(self, err_msg: str):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Data Execution Failure", f"Failed processing input source:\n{err_msg}")

    def load_selected_page(self, row: int):
        if row < 0 or row >= len(self.pages):
            return
        self.current_index = row
        page = self.pages[row]
        
        self.combo_mode.blockSignals(True)
        self.slider_bright.blockSignals(True)
        self.slider_contrast.blockSignals(True)
        self.cb_rm_bg.blockSignals(True)
        
        self.combo_mode.setCurrentText(page.enhancement_mode)
        self.slider_bright.setValue(int(page.brightness * 10))
        self.slider_contrast.setValue(int(page.contrast * 10))
        self.cb_rm_bg.setChecked(page.remove_bg)
        
        self.combo_mode.blockSignals(False)
        self.slider_bright.blockSignals(False)
        self.slider_contrast.blockSignals(False)
        self.cb_rm_bg.blockSignals(False)
        
        self.update_enhancements_pipeline(setup_handles=True)

    def on_polygon_modified(self):
        if self.current_index == -1: return
        self.pages[self.current_index].corners = self.crop_viewer.get_selected_points()

    def update_enhancements_pipeline(self, setup_handles=False):
        if self.current_index == -1: return
            
        page = self.pages[self.current_index]
        page.enhancement_mode = self.combo_mode.currentText()
        page.brightness = self.slider_bright.value() / 10.0
        page.contrast = self.slider_contrast.value() / 10.0
        page.remove_bg = self.cb_rm_bg.isChecked()

        enhanced_cv = ImageProcessor.apply_enhancements(
            page.raw_image, page.enhancement_mode, page.brightness, page.contrast, page.sharpness, page.remove_bg
        )
        
        is_rgba = (enhanced_cv.shape[2] == 4)
        cv_fmt = cv2.COLOR_BGRA2RGBA if is_rgba else cv2.COLOR_BGR2RGB
        qt_fmt = QImage.Format.Format_RGBA8888 if is_rgba else QImage.Format.Format_RGB888
        
        rgb = cv2.cvtColor(enhanced_cv, cv_fmt)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, qt_fmt)
        
        if setup_handles:
            self.crop_viewer.set_image(q_img, page.corners)
        else:
            self.crop_viewer.update_background(q_img)

    def delete_current_page(self):
        if self.current_index == -1: return
        idx = self.current_index
        self.page_list_widget.takeItem(idx)
        self.pages.pop(idx)
        if len(self.pages) > 0:
            self.load_selected_page(max(0, idx - 1))
        else:
            self.current_index = -1
            self.crop_viewer.scene.clear()

    def get_processed_images(self) -> list:
        compiled_pil_images = []
        for p in self.pages:
            warped_cv = ImageProcessor.warp_perspective_curved(p.raw_image, p.corners)
            enhanced_cv = ImageProcessor.apply_enhancements(
                warped_cv, p.enhancement_mode, p.brightness, p.contrast, p.sharpness, p.remove_bg
            )
            
            is_rgba = (enhanced_cv.shape[2] == 4)
            color_cvt = cv2.COLOR_BGRA2RGBA if is_rgba else cv2.COLOR_BGR2RGB
            rgb_cv = cv2.cvtColor(enhanced_cv, color_cvt)
            compiled_pil_images.append(Image.fromarray(rgb_cv))
        return compiled_pil_images

    def export_document(self):
        if not self.pages:
            QMessageBox.warning(self, "Export Blocked", "No document pages available to export.")
            return
            
        fmt = self.combo_export_format.currentText()
        merge = self.cb_merge.isChecked()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if fmt == "PDF" or merge:
            suggested_name = f"smart_docs_{timestamp}.pdf"
            save_path, _ = QFileDialog.getSaveFileName(self, "Export Merged PDF", suggested_name, "Portable Document Format (*.pdf)")
            if save_path and self.build_pdf_silently(save_path):
                QMessageBox.information(self, "Export Success", f"Successfully written PDF to:\n{save_path}")
        else:
            save_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
            if save_dir:
                paths = self.build_images_silently(save_dir, f"smart_docs_{timestamp}", fmt)
                if paths:
                    QMessageBox.information(self, "Export Success", f"Saved {len(paths)} grouped images to:\n{save_dir}")

    def build_pdf_silently(self, save_path: str) -> bool:
        self.progress_bar.setVisible(True)
        try:
            images = self.get_processed_images()
            if images:
                safe_images = [img.convert("RGB") if img.mode in ("RGBA", "P") else img for img in images]
                safe_images[0].save(save_path, save_all=True, append_images=safe_images[1:], options={"quality": 95})
            self.progress_bar.setVisible(False)
            return True
        except Exception as e:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Export Error", f"Fatal structure breakdown running layout compilers:\n{str(e)}")
            return False

    def build_images_silently(self, base_dir: str, base_name: str, fmt: str) -> list:
        self.progress_bar.setVisible(True)
        saved_paths = []
        try:
            images = self.get_processed_images()
            for i, img in enumerate(images):
                suffix = f"_{i+1}" if len(images) > 1 else ""
                
                # Default logic: Keep original extension if requested
                ext = self.pages[i].orig_ext if "Default" in fmt else (".png" if fmt == "PNG" else ".jpg")
                path = os.path.join(base_dir, f"{base_name}{suffix}{ext}")
                
                if ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                    
                img.save(path, quality=95)
                saved_paths.append(path)
                
            self.progress_bar.setVisible(False)
            return saved_paths
        except Exception as e:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Export Error", f"Failed to export Image configurations:\n{str(e)}")
            return []

if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)

    # Show the branded splash while the main UI and processing components initialise.
    splash = RatioJurisSplash()
    screen = app.primaryScreen()
    if screen:
        splash.move(
            screen.availableGeometry().center() - splash.rect().center()
        )
    splash.show()
    app.processEvents()

    scanner_main = RatioJurisSmartScanner()
    splash.showMessage(
        "Scanner ready",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
        QColor("#AEB8C4")
    )
    app.processEvents()

    scanner_main.show()
    splash.finish(scanner_main)
    sys.exit(app.exec())