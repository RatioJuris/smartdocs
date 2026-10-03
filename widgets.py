"""
Ratio Juris Smart Scanner - High-DPI UI Graphics Canvas Engine
"""

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPixmap, QImage, QPen, QBrush, QPainter, QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsEllipseItem, QGraphicsPathItem

class InteractiveCornerHandle(QGraphicsEllipseItem):
    def __init__(self, index, radius=12):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.index = index
        # Midpoints are slightly smaller and a different color
        is_midpoint = index % 2 != 0
        color = QColor(0, 255, 122, 200) if is_midpoint else QColor(0, 122, 255, 200)
        
        if is_midpoint:
            self.setRect(-radius*0.75, -radius*0.75, radius*1.5, radius*1.5)
            
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(255, 255, 255), 2))
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    def itemChange(self, change, value):
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionChange and self.scene():
            rect = self.scene().sceneRect()
            new_pos = value
            if not rect.contains(new_pos):
                new_pos.setX(min(max(new_pos.x(), rect.left()), rect.right()))
                new_pos.setY(min(max(new_pos.y(), rect.top()), rect.bottom()))
                if hasattr(self, 'positionChanged'):
                    self.positionChanged()
                return new_pos
            if hasattr(self, 'positionChanged'):
                self.positionChanged()
        return super().itemChange(change, value)

class DocumentCropView(QGraphicsView):
    polygon_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.handles = []
        self.path_item = None
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def set_image(self, q_img: QImage, pts: list):
        self.scene.clear()
        self.handles.clear()
        
        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(q_img))
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(QRectF(q_img.rect()))

        self.path_item = self.scene.addPath(QPainterPath(), QPen(QColor(0, 122, 255, 180), 3), QBrush(QColor(0, 122, 255, 30)))

        for i, pt in enumerate(pts):
            handle = InteractiveCornerHandle(index=i)
            handle.setPos(QPointF(pt[0], pt[1]))
            self.scene.addItem(handle)
            self.handles.append(handle)
            handle.positionChanged = self.update_curve
            
        self.update_curve()
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def update_curve(self):
        if len(self.handles) == 8 and self.path_item:
            pts = [h.pos() for h in self.handles]
            
            # Create a smooth Bezier curve through the 8 points
            path = QPainterPath()
            path.moveTo(pts[0])
            path.quadTo(pts[1], pts[2])
            path.quadTo(pts[3], pts[4])
            path.quadTo(pts[5], pts[6])
            path.quadTo(pts[7], pts[0])
            
            self.path_item.setPath(path)
            self.polygon_updated.emit()

    def get_selected_points(self) -> np.ndarray:
        return np.array([[h.pos().x(), h.pos().y()] for h in self.handles], dtype=np.float32)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene:
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            
    def update_background(self, q_img: QImage):
        if hasattr(self, 'pixmap_item') and self.pixmap_item:
            self.pixmap_item.setPixmap(QPixmap.fromImage(q_img))