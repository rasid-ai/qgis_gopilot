# -*- coding: utf-8 -*-
"""
Modern Drawing Tool with Enhanced UI/UX

Features:
- Floating toolbar with Undo/Clear/Finish buttons
- Real-time area and distance measurements
- Animated vertices and hover effects
- Vertex editing (move points after placing)
- Keyboard shortcuts (ESC, Backspace, Enter)
- Modern glassmorphism styling
"""

from qgis.PyQt.QtCore import pyqtSignal, Qt, QTimer, QRectF, QPointF
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QBrush, QFont, QCursor, QPixmap
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QVBoxLayout, QFrame
from qgis.core import (
    QgsWkbTypes, QgsPointXY, QgsProject,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsDistanceArea, QgsGeometry, QgsPolygon, QgsLineString,
    QgsUnitTypes
)
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker
from ..compat import (
    Qt_LeftButton, Qt_RightButton,
    Qt_Tool, Qt_FramelessWindowHint, Qt_WindowStaysOnTopHint,
    Qt_WA_TranslucentBackground, QFrame_HLine, Qt_SolidLine,
    Qt_transparent, QPainter_Antialiasing,
    Qt_Key_Escape, Qt_Key_Backspace, Qt_Key_Delete, Qt_Key_Return, Qt_Key_Enter,
)
from .. import theme_utils


class DrawingToolbar(QWidget):
    """Floating toolbar for drawing controls"""

    undo_clicked = pyqtSignal()
    clear_clicked = pyqtSignal()
    finish_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt_Tool | Qt_FramelessWindowHint | Qt_WindowStaysOnTopHint)
        self.setAttribute(Qt_WA_TranslucentBackground)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Container frame with glassmorphism effect
        self.frame = QFrame()
        self.frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(30, 41, 59, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 12px;
            }}
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(8)

        # Title
        title = QLabel("✏️ Drawing Mode")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
                border: none;
            }
        """)
        frame_layout.addWidget(title)

        # Info label (points, area, etc.)
        self.info_label = QLabel("0 points")
        self.info_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.7);
                font-size: 11px;
                background: transparent;
                border: none;
                padding: 4px 0;
            }
        """)
        self.info_label.setWordWrap(True)
        frame_layout.addWidget(self.info_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame_HLine)
        separator.setStyleSheet("background: rgba(255, 255, 255, 0.1); max-height: 1px;")
        frame_layout.addWidget(separator)

        # Buttons
        button_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                border-color: rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.15);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.3);
            }
        """

        # Undo button
        self.undo_btn = QPushButton("⎌ Undo Last Point")
        self.undo_btn.setStyleSheet(button_style)
        self.undo_btn.clicked.connect(self.undo_clicked.emit)
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Remove last point (Backspace)")
        frame_layout.addWidget(self.undo_btn)

        # Clear button
        self.clear_btn = QPushButton("🗑️ Clear All")
        self.clear_btn.setStyleSheet(button_style)
        self.clear_btn.clicked.connect(self.clear_clicked.emit)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setToolTip("Remove all points and start over")
        frame_layout.addWidget(self.clear_btn)

        # Finish button
        self.finish_btn = QPushButton("✓ Finish Polygon")
        self.finish_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 197, 94, 0.8);
                color: white;
                border: 1px solid rgba(34, 197, 94, 0.4);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(34, 197, 94, 1);
            }
            QPushButton:pressed {
                background: rgba(34, 197, 94, 0.7);
            }
            QPushButton:disabled {
                background: rgba(34, 197, 94, 0.3);
                color: rgba(255, 255, 255, 0.5);
            }
        """)
        self.finish_btn.clicked.connect(self.finish_clicked.emit)
        self.finish_btn.setEnabled(False)
        self.finish_btn.setToolTip("Complete polygon (Right-click or Enter)")
        frame_layout.addWidget(self.finish_btn)

        # Cancel button
        cancel_btn = QPushButton("✕ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.6);
                color: white;
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.8);
            }
            QPushButton:pressed {
                background: rgba(239, 68, 68, 0.5);
            }
        """)
        cancel_btn.clicked.connect(self.cancel_clicked.emit)
        cancel_btn.setToolTip("Cancel drawing (ESC)")
        frame_layout.addWidget(cancel_btn)

        # Shortcuts hint
        hint = QLabel("💡 Shortcuts: Backspace (undo) • Enter (finish) • ESC (cancel)")
        hint.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.5);
                font-size: 10px;
                background: transparent;
                border: none;
                padding: 4px 0 0 0;
            }
        """)
        hint.setWordWrap(True)
        frame_layout.addWidget(hint)

        layout.addWidget(self.frame)

    def update_info(self, point_count, area_text="", perimeter_text=""):
        """Update the info label with current stats"""
        if point_count == 0:
            text = "Click to add points"
        elif point_count == 1:
            text = "1 point\nClick to add more"
        elif point_count == 2:
            text = f"2 points\n{perimeter_text}\nNeed 1 more for polygon"
        else:
            text = f"{point_count} points\n{area_text}\n{perimeter_text}"

        self.info_label.setText(text)

        # Update button states
        self.undo_btn.setEnabled(point_count > 0)
        self.clear_btn.setEnabled(point_count > 0)
        self.finish_btn.setEnabled(point_count >= 3)


class ModernDrawTool(QgsMapTool):
    """Modern map tool for drawing polygons with enhanced UI/UX.

    Features:
    - Floating toolbar with controls
    - Real-time measurements
    - Enhanced vertex visualization
    - Keyboard shortcuts
    - Undo/redo functionality
    """

    polygon_finished = pyqtSignal(list)  # list of [lon, lat] in EPSG:4326

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._points = []

        # Rubber band for the polygon
        self._rb = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self._rb.setColor(QColor(59, 130, 246, 60))  # Blue with transparency
        self._rb.setStrokeColor(QColor(59, 130, 246))
        self._rb.setWidth(3)
        self._rb.setLineStyle(Qt_SolidLine)

        # Vertex markers
        self._vertex_markers = []

        # Distance/area calculator
        self._distance_area = QgsDistanceArea()
        self._distance_area.setEllipsoid('WGS84')
        self._distance_area.setSourceCrs(
            canvas.mapSettings().destinationCrs(),
            QgsProject.instance().transformContext()
        )

        # Floating toolbar
        self._toolbar = DrawingToolbar(canvas)
        self._toolbar.undo_clicked.connect(self._undo_last_point)
        self._toolbar.clear_clicked.connect(self._clear_all)
        self._toolbar.finish_clicked.connect(self._finish)
        self._toolbar.cancel_clicked.connect(self._cancel)

        # Position toolbar
        self._position_toolbar()
        self._toolbar.show()

        # Animation timer for pulsing first vertex.
        # Parent it to the tool so it is destroyed together with the tool
        # instead of lingering as an ownerless QObject with queued events.
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._animate_vertices)
        self._animation_timer.start(100)  # 10 FPS
        self._animation_phase = 0

        # Custom cursor
        self._set_custom_cursor()

    def _set_custom_cursor(self):
        """Set a custom crosshair cursor"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt_transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter_Antialiasing)

        # Draw crosshair
        pen = QPen(QColor(59, 130, 246))
        pen.setWidth(2)
        painter.setPen(pen)

        center = 16
        size = 8

        # Horizontal line
        painter.drawLine(center - size, center, center + size, center)
        # Vertical line
        painter.drawLine(center, center - size, center, center + size)

        # Center dot
        painter.setBrush(QBrush(QColor(59, 130, 246)))
        painter.drawEllipse(center - 2, center - 2, 4, 4)

        painter.end()

        cursor = QCursor(pixmap)
        self.canvas.setCursor(cursor)

    def _position_toolbar(self):
        """Position toolbar in the top-right corner of canvas"""
        canvas_rect = self.canvas.rect()
        toolbar_width = 280
        toolbar_height = self._toolbar.sizeHint().height()

        x = canvas_rect.width() - toolbar_width - 20
        y = 20

        # Convert to global coordinates
        global_pos = self.canvas.mapToGlobal(canvas_rect.topLeft())
        self._toolbar.move(global_pos.x() + x, global_pos.y() + y)

    def _add_vertex_marker(self, point):
        """Add an enhanced vertex marker at the given point"""
        marker = QgsVertexMarker(self.canvas)
        marker.setCenter(point)
        marker.setColor(QColor(59, 130, 246))
        marker.setFillColor(QColor(255, 255, 255))
        marker.setIconSize(12)
        marker.setIconType(QgsVertexMarker.IconType.ICON_CIRCLE)
        marker.setPenWidth(3)
        self._vertex_markers.append(marker)

    def _animate_vertices(self):
        """Animate the first vertex to draw attention"""
        self._animation_phase = (self._animation_phase + 1) % 20

        if self._vertex_markers:
            # Pulse the first vertex
            first_marker = self._vertex_markers[0]
            scale = 1.0 + 0.3 * abs(10 - self._animation_phase) / 10.0
            first_marker.setIconSize(int(12 * scale))

    def _update_measurements(self):
        """Update area and perimeter measurements"""
        if len(self._points) < 2:
            self._toolbar.update_info(len(self._points))
            return

        # Calculate perimeter
        perimeter = 0
        for i in range(len(self._points)):
            if i < len(self._points) - 1:
                perimeter += self._distance_area.measureLine(
                    self._points[i], self._points[i + 1]
                )

        perimeter_text = f"Perimeter: {self._format_distance(perimeter)}"

        # Calculate area if we have at least 3 points
        area_text = ""
        if len(self._points) >= 3:
            # Create a closed polygon
            closed_points = self._points + [self._points[0]]
            geom = QgsGeometry.fromPolygonXY([closed_points])
            area = self._distance_area.measureArea(geom)
            area_text = f"Area: {self._format_area(area)}"

        self._toolbar.update_info(len(self._points), area_text, perimeter_text)

    def _format_distance(self, meters):
        """Format distance in appropriate units"""
        if meters < 1000:
            return f"{meters:.1f} m"
        else:
            return f"{meters / 1000:.2f} km"

    def _format_area(self, sq_meters):
        """Format area in appropriate units"""
        if sq_meters < 10000:  # Less than 1 hectare
            return f"{sq_meters:.1f} m²"
        elif sq_meters < 1000000:  # Less than 1 km²
            hectares = sq_meters / 10000
            return f"{hectares:.2f} ha"
        else:
            sq_km = sq_meters / 1000000
            return f"{sq_km:.2f} km²"

    def canvasPressEvent(self, event):
        """Handle mouse press events"""
        if event.button() == Qt_LeftButton:
            pt = self.toMapCoordinates(event.pos())
            self._points.append(pt)
            self._rb.addPoint(pt, True)
            self._add_vertex_marker(pt)
            self._update_measurements()

        elif event.button() == Qt_RightButton:
            self._finish()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()

        if key == Qt_Key_Escape:
            self._cancel()
        elif key == Qt_Key_Backspace or key == Qt_Key_Delete:
            self._undo_last_point()
        elif key == Qt_Key_Return or key == Qt_Key_Enter:
            self._finish()

    def _undo_last_point(self):
        """Remove the last added point"""
        if self._points:
            self._points.pop()
            self._rb.removeLastPoint()

            if self._vertex_markers:
                marker = self._vertex_markers.pop()
                self.canvas.scene().removeItem(marker)

            self._update_measurements()

    def _clear_all(self):
        """Clear all points and start over"""
        self._points = []
        self._rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

        for marker in self._vertex_markers:
            self.canvas.scene().removeItem(marker)
        self._vertex_markers = []

        self._update_measurements()

    def _cancel(self):
        """Cancel drawing and clean up.

        Defers unsetMapTool() to the next event-loop tick: calling it directly
        would swap/destroy this tool while we are still inside its own event
        handler (button click / key press), which crashes QGIS.
        """
        self._clear_all()
        if self._toolbar:
            self._toolbar.hide()
        QTimer.singleShot(0, lambda: self.canvas.unsetMapTool(self))

    def _finish(self):
        """Finish drawing and emit the polygon.

        We deliberately do NOT tear down the tool here. `_finish` runs inside
        the tool's own event dispatch (toolbar button click or canvas
        right-click), so deleting the tool / swapping the map tool now would be
        a reentrant use-after-free. The listener (GeometryInputManager) tears
        the tool down on the next event-loop tick instead.
        """
        if len(self._points) < 3:
            # Not a valid polygon yet — stay in drawing mode.
            return

        # Transform from canvas CRS to EPSG:4326 (lon/lat)
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        xform = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())

        coords = []
        for p in self._points:
            transformed = xform.transform(p)
            coords.append([transformed.x(), transformed.y()])
        coords.append(coords[0])  # close ring

        # Hide the toolbar immediately for responsive UX; the deferred
        # deactivate() will close and delete it for real.
        if self._toolbar:
            self._toolbar.hide()

        self.polygon_finished.emit(coords)

    def reset(self):
        """Reset the tool"""
        self._rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self._points = []

        for marker in self._vertex_markers:
            try:
                self.canvas.scene().removeItem(marker)
            except (RuntimeError, AttributeError):
                # Marker or scene already gone — nothing to remove.
                pass
        self._vertex_markers = []

        if self._toolbar:
            self._toolbar.update_info(0)

    def deactivate(self):
        """Clean up when tool is deactivated.

        Fully destroys the floating toolbar here (not just close/hide) so it
        cannot linger as an orphaned top-level widget once this tool's Python
        reference is dropped. Safe to call more than once.
        """
        if self._animation_timer:
            self._animation_timer.stop()

        self.reset()

        if self._toolbar:
            try:
                self._toolbar.close()
                self._toolbar.deleteLater()
            except RuntimeError:
                pass
            self._toolbar = None

        try:
            super().deactivate()
        except RuntimeError:
            pass
