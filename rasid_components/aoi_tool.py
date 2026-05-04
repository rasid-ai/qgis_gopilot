"""Map tool for drawing an AOI polygon on the QGIS canvas."""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsWkbTypes, QgsPointXY, QgsProject,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
)
from qgis.gui import QgsMapTool, QgsRubberBand


class AoiDrawTool(QgsMapTool):
    """Left-click to add points, right-click to finish the polygon."""
    polygon_finished = pyqtSignal(list)  # list of [lon, lat] in EPSG:4326

    def __init__(self, canvas):
        super().__init__(canvas)
        self._rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self._rb.setColor(QColor(255, 0, 0, 80))
        self._rb.setStrokeColor(QColor(255, 0, 0))
        self._rb.setWidth(2)
        self._points = []

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pt = self.toMapCoordinates(event.pos())
            self._points.append(pt)
            self._rb.addPoint(pt, True)
        elif event.button() == Qt.RightButton:
            self._finish()

    def _finish(self):
        if len(self._points) >= 3:
            # Transform from canvas CRS to EPSG:4326 (lon/lat)
            canvas_crs = self.canvas().mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            xform = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())

            coords = []
            for p in self._points:
                transformed = xform.transform(p)
                coords.append([transformed.x(), transformed.y()])
            coords.append(coords[0])  # close ring
            self.polygon_finished.emit(coords)
        self.reset()

    def reset(self):
        self._rb.reset(QgsWkbTypes.PolygonGeometry)
        self._points = []

    def deactivate(self):
        self.reset()
        super().deactivate()
