"""
Ratio Juris Smart Scanner - Core Image Processing Module
Handles document detection, curved perspective transformation, and image enhancements.
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance

class ImageProcessor:
    @staticmethod
    def auto_detect_corners(cv_img: np.ndarray) -> np.ndarray:
        h, w = cv_img.shape[:2]
        
        default_pts = np.array([
            [0, 0], [w/2, 0], [w-1, 0], 
            [w-1, h/2], [w-1, h-1], [w/2, h-1], 
            [0, h-1], [0, h/2]
        ], dtype=np.float32)
        
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
        
        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.contourArea(approx) > (w * h * 0.1):
                pts = approx.reshape(4, 2).astype(np.float32)
                rect = ImageProcessor.order_points(pts)
                
                tl, tr, br, bl = rect
                top_mid = (tl + tr) / 2
                right_mid = (tr + br) / 2
                bottom_mid = (br + bl) / 2
                left_mid = (bl + tl) / 2
                
                return np.array([tl, top_mid, tr, right_mid, br, bottom_mid, bl, left_mid], dtype=np.float32)
                
        return default_pts

    @staticmethod
    def order_points(pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    @staticmethod
    def warp_perspective_curved(cv_img: np.ndarray, src_pts: np.ndarray) -> np.ndarray:
        if len(src_pts) == 4:
            src_pts = np.array([
                src_pts[0], (src_pts[0]+src_pts[1])/2, src_pts[1], 
                (src_pts[1]+src_pts[2])/2, src_pts[2], (src_pts[2]+src_pts[3])/2, 
                src_pts[3], (src_pts[3]+src_pts[0])/2
            ], dtype=np.float32)

        tl, _, tr, _, br, _, bl, _ = src_pts
        width = max(int(np.linalg.norm(br - bl)), int(np.linalg.norm(tr - tl)))
        height = max(int(np.linalg.norm(tr - br)), int(np.linalg.norm(tl - bl)))
        
        # Fallback to standard 4-point transform if ThinPlateSpline is missing (opencv-contrib-python not installed)
        if hasattr(cv2, 'createThinPlateSplineShapeTransformer'):
            dst_pts = np.array([
                [0, 0], [width/2, 0], [width-1, 0],
                [width-1, height/2], [width-1, height-1], [width/2, height-1],
                [0, height-1], [0, height/2]
            ], dtype=np.float32)
            
            tps = cv2.createThinPlateSplineShapeTransformer()
            src_pts_reshaped = src_pts.reshape(1, -1, 2)
            dst_pts_reshaped = dst_pts.reshape(1, -1, 2)
            
            matches = [cv2.DMatch(i, i, 0) for i in range(len(src_pts))]
            tps.estimateTransformation(dst_pts_reshaped, src_pts_reshaped, matches)
            
            warped = tps.warpImage(cv_img)
            return warped[:height, :width]
        else:
            # Execute standard fallback
            src_corners = np.array([src_pts[0], src_pts[2], src_pts[4], src_pts[6]], dtype="float32")
            dst_corners = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
            matrix = cv2.getPerspectiveTransform(src_corners, dst_corners)
            warped = cv2.warpPerspective(cv_img, matrix, (width, height))
            return warped

    @staticmethod
    def remove_background(cv_img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        _, alpha = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel)
        
        b, g, r = cv2.split(cv_img)
        rgba = [b, g, r, alpha]
        return cv2.merge(rgba, 4)

    @staticmethod
    def apply_enhancements(cv_img: np.ndarray, mode: str, brightness: float, contrast: float, sharpness: float, rm_bg: bool) -> np.ndarray:
        out_img = cv_img.copy()
        
        if rm_bg:
            out_img = ImageProcessor.remove_background(out_img)

        if mode == "Document/B&W":
            if out_img.shape[2] == 4:
                out_img = cv2.cvtColor(out_img, cv2.COLOR_BGRA2BGR)
            gray = cv2.cvtColor(out_img, cv2.COLOR_BGR2GRAY)
            out_img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            out_img = cv2.cvtColor(out_img, cv2.COLOR_GRAY2BGR)
        elif mode == "Magic Color":
            if out_img.shape[2] == 4:
                out_img = cv2.cvtColor(out_img, cv2.COLOR_BGRA2BGR)
            lab = cv2.cvtColor(out_img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl,a,b))
            out_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        
        is_rgba = (out_img.shape[2] == 4)
        color_cvt = cv2.COLOR_BGRA2RGBA if is_rgba else cv2.COLOR_BGR2RGB
        pil_img = Image.fromarray(cv2.cvtColor(out_img, color_cvt))
        
        if brightness != 1.0:
            pil_img = ImageEnhance.Brightness(pil_img).enhance(brightness)
        if contrast != 1.0:
            pil_img = ImageEnhance.Contrast(pil_img).enhance(contrast)
        if sharpness != 1.0:
            pil_img = ImageEnhance.Sharpness(pil_img).enhance(sharpness)
            
        color_cvt_back = cv2.COLOR_RGBA2BGRA if is_rgba else cv2.COLOR_RGB2BGR
        return cv2.cvtColor(np.array(pil_img), color_cvt_back)