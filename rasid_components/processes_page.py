from qgis.PyQt.QtWidgets import (
    QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QScrollArea, QFrame, QSplitter,
    QMessageBox, QStackedWidget,
)
from qgis.PyQt.QtCore import QThread, pyqtSignal, QTimer
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from .compat import (
    Qt_Horizontal, Qt_AlignTop, Qt_AlignCenter, Qt_AlignLeft,
    Qt_PointingHandCursor, Qt_RichText, Qt_TextBrowserInteraction, Qt_transparent,
    QFrame_NoFrame, QFrame_StyledPanel, exec_dialog, QPainter_Antialiasing,
    QMessageBox_Question, QMessageBox_Yes, QMessageBox_No
)
from .image_loader import load_image
from .create_process_wizard import CreateProcessWizard
from . import theme_utils
from .config import APP_BASE_URL

LIST_THUMB = 40
DETAIL_THUMB = 280

# Only three user-facing states: Completed (green), Failed (red), Preparing (blue)
_COMPLETED = ("Completed", "#00856F")
_FAILED = ("Failed", "#e74c3c")
_PREPARING = ("Preparing", "#1E293B")

SITUATION_LABELS = {
    "is": _COMPLETED,
    "done": _COMPLETED,
    "if": _FAILED,
    "failed": _FAILED,
    "pdmf": _FAILED,
}


def create_trash_icon(size=24, color="#e74c3c"):
    """Create a red trash bin icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt_transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter_Antialiasing)

    pen = QPen(QColor(color))
    pen.setWidth(2)
    painter.setPen(pen)

    # Draw trash bin body
    body_top = int(size * 0.35)
    body_bottom = int(size * 0.85)
    body_left = int(size * 0.25)
    body_right = int(size * 0.75)
    painter.drawRect(body_left, body_top, body_right - body_left, body_bottom - body_top)

    # Draw lid
    lid_y = int(size * 0.3)
    painter.drawLine(int(size * 0.2), lid_y, int(size * 0.8), lid_y)

    # Draw handle
    handle_y = int(size * 0.2)
    painter.drawLine(int(size * 0.4), lid_y, int(size * 0.4), handle_y)
    painter.drawLine(int(size * 0.6), lid_y, int(size * 0.6), handle_y)
    painter.drawLine(int(size * 0.4), handle_y, int(size * 0.6), handle_y)

    # Draw vertical lines inside bin
    painter.drawLine(int(size * 0.5), int(size * 0.45), int(size * 0.5), int(size * 0.75))

    painter.end()
    return QIcon(pixmap)


class FetchProcessesThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, client, project_slug):
        super().__init__()
        self.client = client
        self.project_slug = project_slug

    def run(self):
        try:
            processes = self.client.get_processes(self.project_slug)
            self.finished.emit(processes)
        except Exception as e:
            self.error.emit(str(e))


class FetchProcessDetailThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, process_id):
        super().__init__()
        self.client = client
        self.process_id = process_id

    def run(self):
        try:
            detail = self.client.get_process_detail(self.process_id)
            self.finished.emit(detail)
        except Exception as e:
            self.error.emit(str(e))


class HideProcessThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, client, project_slug, process_id):
        super().__init__()
        self.client = client
        self.project_slug = project_slug
        self.process_id = process_id

    def run(self):
        try:
            self.client.hide_process(self.project_slug, self.process_id)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class DownloadThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, client, url):
        super().__init__()
        self.client = client
        self.url = url

    def run(self):
        try:
            path = self.client.download_file(self.url)
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


def _layer_exists_in_qgis(layer_name):
    """Check if a layer with the given name already exists in QGIS project."""
    from qgis.core import QgsProject
    for layer in QgsProject.instance().mapLayers().values():
        if layer.name() == layer_name:
            return True
    return False


def _add_layer_to_qgis(filepath, layer_name):
    from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer
    root = QgsProject.instance().layerTreeRoot()
    rasid_group = root.findGroup("RASID")
    if rasid_group is None:
        rasid_group = root.insertGroup(0, "RASID")

    ext = filepath.rsplit(".", 1)[-1].lower()
    if ext in ("tif", "tiff"):
        layer = QgsRasterLayer(filepath, layer_name)
    else:
        layer = QgsVectorLayer(filepath, layer_name, "ogr")

    if not layer.isValid():
        raise Exception(f"Could not load layer from {filepath}")

    QgsProject.instance().addMapLayer(layer, False)
    rasid_group.addLayer(layer)


class ProcessesPage(QWidget):

    def __init__(self, client, iface=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.iface = iface
        self._threads = []
        self._current_project = None
        self._selected_row = None
        self._current_processes = []
        self._selected_process_id = None  # Track selected process for silent refresh

        # Track detail panel sections for selective updates during auto-refresh
        self._detail_thumbnail = None
        self._status_badge = None
        self._general_info_layout = None
        self._analytics_layout = None
        self._not_completed_message = None  # Track "not yet completed" message
        self._downloads_section_exists = False  # Track if download buttons have been added
        self._last_known_situation = None  # Track status to detect changes

        # Auto-refresh timer for polling process status (completely invisible)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_auto_refresh)
        self._refresh_timer.setInterval(10000)  # Poll every 10 seconds

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ──
        header = QFrame()
        header_bg = theme_utils.get_sidebar_bg()
        header_border = theme_utils.get_separator_color()
        header.setStyleSheet(f"background: {header_bg}; border-bottom: 1px solid {header_border};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)

        self._title_label = QLabel("")
        text_color = theme_utils.get_text_color()
        self._title_label.setStyleSheet(f"font-weight: bold; font-size: 15px; color: {text_color};")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        # Back button (shown when in wizard view)
        self._back_btn = QPushButton("← Back to Processes")
        self._back_btn.setCursor(Qt_PointingHandCursor)
        self._back_btn.setStyleSheet(
            "QPushButton { background: #64748b; color: white; border: none;"
            "border-radius: 4px; padding: 6px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #475569; }"
        )
        self._back_btn.clicked.connect(self._on_wizard_cancel)
        self._back_btn.hide()  # Hidden by default
        header_layout.addWidget(self._back_btn)

        self._new_process_btn = QPushButton("+ New Process")
        self._new_process_btn.setCursor(Qt_PointingHandCursor)
        self._new_process_btn.setStyleSheet(
            f"QPushButton {{ background: {theme_utils.BRAND_PRIMARY}; color: white; border: none;"
            f"border-radius: 4px; padding: 6px 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {theme_utils.BRAND_HOVER}; }}"
        )
        self._new_process_btn.clicked.connect(self._on_new_process)
        header_layout.addWidget(self._new_process_btn)

        outer.addWidget(header)

        # ── Body: stacked widget switching between list view and create wizard ──
        self._body_stack = QStackedWidget()
        outer.addWidget(self._body_stack, stretch=1)

        # Page 0: process list + detail splitter
        self._list_view = QWidget()
        self._build_list_view()
        self._body_stack.addWidget(self._list_view)

        # Page 1: create process wizard (added dynamically)
        self._wizard = None

    def _build_list_view(self):
        layout = QVBoxLayout(self._list_view)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt_Horizontal)
        layout.addWidget(splitter)

        # Left: scrollable process list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame_NoFrame)
        self._list_scroll.setMinimumWidth(220)
        left_layout.addWidget(self._list_scroll)

        self._list_inner = QWidget()
        self._list_layout = QVBoxLayout(self._list_inner)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(6, 6, 6, 6)
        self._list_layout.setAlignment(Qt_AlignTop)
        self._list_scroll.setWidget(self._list_inner)

        splitter.addWidget(left)

        # Right: detail panel
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QFrame_NoFrame)
        splitter.addWidget(self._detail_scroll)

        self._detail_widget = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_widget)
        self._detail_layout.setContentsMargins(12, 12, 12, 12)
        self._detail_layout.setSpacing(8)
        self._detail_layout.setAlignment(Qt_AlignTop)
        self._detail_scroll.setWidget(self._detail_widget)

        self._show_detail_placeholder()

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def closeEvent(self, event):
        """Stop auto-refresh timer when widget is closed."""
        self._stop_auto_refresh()
        super().closeEvent(event)

    def hideEvent(self, event):
        """Stop auto-refresh timer when widget is hidden."""
        self._stop_auto_refresh()
        super().hideEvent(event)

    # ── Public ──

    def load_processes(self, project):
        self._current_project = project
        self._title_label.setText(project.get("title", "Project"))
        self._body_stack.setCurrentWidget(self._list_view)
        self._new_process_btn.show()
        self._back_btn.hide()
        self._clear_list()
        self._show_detail_placeholder()

        loading = QLabel("Loading processes...")
        loading.setAlignment(Qt_AlignCenter)
        self._list_layout.addWidget(loading)

        slug = project.get("slug", "")
        self._fetch_thread = FetchProcessesThread(self.client, slug)
        self._fetch_thread.finished.connect(self._on_loaded)
        self._fetch_thread.error.connect(self._on_error)
        self._fetch_thread.start()

    # ── List callbacks ──

    def _on_loaded(self, processes, preserve_selection=False):
        """Load processes into list. If preserve_selection=True, restore previously selected process."""
        self._current_processes = processes

        # Save scroll positions (both list and detail)
        list_scroll_pos = self._list_scroll.verticalScrollBar().value()
        detail_scroll_pos = self._detail_scroll.verticalScrollBar().value()

        self._clear_list()

        if not processes:
            lbl = QLabel("No processes yet. Click '+ New Process' to create one.")
            lbl.setAlignment(Qt_AlignCenter)
            secondary_color = theme_utils.get_secondary_text_color()
            lbl.setStyleSheet(f"color: {secondary_color}; font-size: 13px;")
            self._list_layout.addWidget(lbl)
            self._stop_auto_refresh()
            return

        selected_index = None
        selected_proc = None
        for i, proc in enumerate(processes):
            row = self._create_row(proc)
            self._list_layout.addWidget(row)

            # Track which row should be selected
            if preserve_selection and proc.get("id") == self._selected_process_id:
                selected_index = i
                selected_proc = proc

        # Restore selection or select first process
        if processes:
            if preserve_selection and selected_index is not None:
                # Silently restore previously selected process (don't trigger full reload)
                selected_row = self._list_layout.itemAt(selected_index).widget()

                # Update row selection styling without triggering detail fetch
                if self._selected_row:
                    card_bg = theme_utils.get_card_bg()
                    card_border = theme_utils.get_card_border()
                    hover_bg = theme_utils.get_hover_bg()
                    self._selected_row.setStyleSheet(f"""
                        QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 4px; }}
                        QFrame:hover {{ background: {hover_bg}; }}
                    """)
                selected_bg = "#d1fae5" if not theme_utils.is_dark_theme() else "#1a4d3f"
                selected_row.setStyleSheet(
                    f"QFrame {{ background: {selected_bg}; border: 2px solid {theme_utils.BRAND_PRIMARY}; border-radius: 4px; }}"
                )
                self._selected_row = selected_row

                # Silently update detail view - only update status badge, don't rebuild everything
                if selected_proc and selected_proc.get("id"):
                    self._detail_thread = FetchProcessDetailThread(self.client, selected_proc.get("id"))
                    self._detail_thread.finished.connect(lambda proc: self._update_detail_status_only(proc))
                    self._detail_thread.error.connect(self._on_detail_error)
                    self._detail_thread.start()

            elif not preserve_selection:
                # First load - select first process
                first_proc = processes[0]
                first_row = self._list_layout.itemAt(0).widget()
                self._on_row_clicked(first_proc, first_row)

        # Restore scroll position
        self._list_scroll.verticalScrollBar().setValue(list_scroll_pos)

        # Check if we have any "Preparing" processes (silently)
        self._manage_auto_refresh()

    def _on_error(self, msg):
        self._clear_list()
        lbl = QLabel(f"Failed to load processes: {msg}")
        lbl.setAlignment(Qt_AlignCenter)
        lbl.setWordWrap(True)
        self._list_layout.addWidget(lbl)
        self._stop_auto_refresh()

    # ── Auto-refresh logic (completely invisible to user) ──

    def _has_preparing_processes(self):
        """Check if any processes are still preparing (not completed or failed)."""
        for proc in self._current_processes:
            situation = proc.get("situation", "")
            # If situation is not in SITUATION_LABELS, it's "Preparing"
            if situation not in SITUATION_LABELS:
                return True
        return False

    def _manage_auto_refresh(self):
        """Silently start or stop auto-refresh based on process states."""
        if self._has_preparing_processes():
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._stop_auto_refresh()

    def _on_auto_refresh(self):
        """Called by timer to silently refresh process list in background."""
        if self._current_project:
            slug = self._current_project.get("slug", "")
            self._fetch_thread = FetchProcessesThread(self.client, slug)
            # Use lambda to pass preserve_selection=True for silent refresh
            self._fetch_thread.finished.connect(lambda procs: self._on_loaded(procs, preserve_selection=True))
            self._fetch_thread.error.connect(self._on_error)
            self._fetch_thread.start()

    def _stop_auto_refresh(self):
        """Silently stop the auto-refresh timer."""
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()

    # ── List helpers ──

    def _clear_list(self):
        self._selected_row = None
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _create_row(self, proc):
        row = QFrame()
        row.setFrameShape(QFrame_StyledPanel)
        row.setCursor(Qt_PointingHandCursor)
        card_bg = theme_utils.get_card_bg()
        card_border = theme_utils.get_card_border()
        hover_bg = theme_utils.get_hover_bg()
        row.setStyleSheet(f"""
            QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 4px; }}
            QFrame:hover {{ background: {hover_bg}; }}
        """)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(LIST_THUMB, LIST_THUMB)
        thumb.setAlignment(Qt_AlignCenter)
        thumb_bg = theme_utils.get_sidebar_bg()
        thumb.setStyleSheet(f"background: {thumb_bg}; border-radius: 4px; border: none;")
        load_image(self.client, proc.get("thumbnail"), thumb, self._threads,
                   size=(LIST_THUMB, LIST_THUMB))
        layout.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(proc.get("name", "Unnamed"))
        text_color = theme_utils.get_text_color()
        name.setStyleSheet(f"font-weight: bold; font-size: 12px; border: none; color: {text_color};")
        info.addWidget(name)

        situation = proc.get("situation", "idle") or "idle"
        label_text, color = SITUATION_LABELS.get(situation, _PREPARING)
        badge = QLabel(label_text)
        badge.setFixedHeight(16)
        badge.setStyleSheet(
            f"color: white; background: {color}; border-radius: 3px;"
            "padding: 1px 6px; font-size: 9px; border: none;"
        )
        info.addWidget(badge, alignment=Qt_AlignLeft)
        layout.addLayout(info, stretch=1)

        hide_btn = QPushButton()
        hide_btn.setIcon(create_trash_icon(20, theme_utils.BRAND_DANGER))
        hide_btn.setFixedSize(28, 28)
        hide_btn.setCursor(Qt_PointingHandCursor)
        hide_btn.setToolTip("Hide process")
        btn_bg = theme_utils.get_card_bg()
        btn_border = theme_utils.get_card_border()
        danger_hover = theme_utils.get_danger_hover_bg()
        hide_btn.setStyleSheet(
            f"QPushButton {{ background: {btn_bg}; border: 1px solid {btn_border};"
            f"border-radius: 4px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {danger_hover}; border-color: {theme_utils.BRAND_DANGER}; }}"
        )
        hide_btn.clicked.connect(lambda _, p=proc: self._on_hide_process(p))
        layout.addWidget(hide_btn, alignment=Qt_AlignTop)

        row.mousePressEvent = lambda e, p=proc, r=row: self._on_row_clicked(p, r)
        return row

    def _on_row_clicked(self, proc, row):
        if self._selected_row:
            # Deselect previous row - restore normal colors
            card_bg = theme_utils.get_card_bg()
            card_border = theme_utils.get_card_border()
            hover_bg = theme_utils.get_hover_bg()
            self._selected_row.setStyleSheet(f"""
                QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 4px; }}
                QFrame:hover {{ background: {hover_bg}; }}
            """)
        # Select new row - highlight with brand color
        selected_bg = "#d1fae5" if not theme_utils.is_dark_theme() else "#1a4d3f"
        row.setStyleSheet(
            f"QFrame {{ background: {selected_bg}; border: 2px solid {theme_utils.BRAND_PRIMARY}; border-radius: 4px; }}"
        )
        self._selected_row = row

        # Save selected process ID for invisible refresh
        process_id = proc.get("id")
        self._selected_process_id = process_id
        if not process_id:
            self._show_detail(proc)
            return

        self._clear_detail()
        loading = QLabel("Loading details...")
        loading.setAlignment(Qt_AlignCenter)
        secondary_color = theme_utils.get_secondary_text_color()
        loading.setStyleSheet(f"color: {secondary_color}; font-size: 13px;")
        self._detail_layout.addWidget(loading)

        self._detail_thread = FetchProcessDetailThread(self.client, process_id)
        self._detail_thread.finished.connect(self._show_detail)
        self._detail_thread.error.connect(self._on_detail_error)
        self._detail_thread.start()

    def _on_detail_error(self, msg):
        self._clear_detail()
        lbl = QLabel(f"Failed to load detail: {msg}")
        lbl.setAlignment(Qt_AlignCenter)
        lbl.setStyleSheet(f"color: {theme_utils.BRAND_DANGER}; font-size: 12px;")
        self._detail_layout.addWidget(lbl)

    # ── Detail panel ──

    def _show_detail_placeholder(self):
        self._clear_detail()
        lbl = QLabel("Select a process to view details")
        lbl.setAlignment(Qt_AlignCenter)
        lbl.setStyleSheet("color: #aaa; font-size: 14px;")
        self._detail_layout.addWidget(lbl)

    def _clear_detail(self):
        # Clear references to detail sections
        self._detail_thumbnail = None
        self._status_badge = None
        self._general_info_layout = None
        self._analytics_layout = None
        self._not_completed_message = None
        self._downloads_section_exists = False
        self._last_known_situation = None

        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            w = child.widget()
            if w:
                w.deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def _add_info_row(self, label, value):
        """Add info row to the main detail layout."""
        self._add_info_row_to_layout(self._detail_layout, label, value)

    def _add_info_row_to_layout(self, parent_layout, label, value):
        """Add info row to a specific layout."""
        row = QHBoxLayout()
        key = QLabel(f"{label}:")
        key.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
        key.setFixedWidth(100)
        val = QLabel(str(value))
        val.setStyleSheet("font-size: 12px;")
        val.setWordWrap(True)
        row.addWidget(key)
        row.addWidget(val, stretch=1)
        parent_layout.addLayout(row)

    def _add_section_header(self, text):
        header = QLabel(text)
        header.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #2c3e50;"
            "border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 8px;"
        )
        self._detail_layout.addWidget(header)

    def _update_detail_status_only(self, proc):
        """Update dynamic sections (thumbnail, status, general info, analytics) without touching downloads.
        This prevents interrupting downloads during auto-refresh."""
        if not self._status_badge:
            # Detail panel not yet created, skip silent update
            return

        try:
            # 1. Update thumbnail
            if self._detail_thumbnail:
                load_image(self.client, proc.get("thumbnail"), self._detail_thumbnail,
                          self._threads, size=(DETAIL_THUMB, DETAIL_THUMB))

            # 2. Update status badge
            situation = proc.get("situation", "idle") or "idle"
            label_text, color = SITUATION_LABELS.get(situation, _PREPARING)
            self._status_badge.setText(label_text)
            self._status_badge.setStyleSheet(
                f"color: white; background: {color}; border-radius: 4px;"
                "padding: 2px 12px; font-size: 12px; font-weight: bold;"
            )

            # 3. Update general info section
            if self._general_info_layout:
                # Clear existing general info
                while self._general_info_layout.count():
                    item = self._general_info_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                    elif item.layout():
                        self._clear_layout(item.layout())

                # Rebuild general info
                fees = proc.get("fees")
                self._add_info_row_to_layout(self._general_info_layout, "Fees",
                                             f"€{fees}" if fees is not None else "-")
                create_date = proc.get("create_date", "-") or "-"
                self._add_info_row_to_layout(self._general_info_layout, "Date", create_date)
                area = proc.get("area")
                self._add_info_row_to_layout(self._general_info_layout, "Area",
                                            f"{area} km²" if area is not None else "-")

            # 4. Update/Add analytics section
            analytics = proc.get("analytics", {})
            if analytics:
                if not self._analytics_layout:
                    # Analytics just became available - add section for first time
                    self._add_section_header("Data Analytics")
                    analytics_container = QVBoxLayout()
                    analytics_container.setSpacing(4)
                    self._detail_layout.addLayout(analytics_container)
                    self._analytics_layout = analytics_container

                # Clear and rebuild analytics
                while self._analytics_layout.count():
                    item = self._analytics_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                    elif item.layout():
                        self._clear_layout(item.layout())

                for key, value in analytics.items():
                    self._add_info_row_to_layout(self._analytics_layout, key, value)

            # 5. Add download buttons if status just changed to "Completed"
            is_completed = situation == "is"
            status_changed_to_completed = (is_completed and
                                          self._last_known_situation != "is" and
                                          not self._downloads_section_exists)

            if status_changed_to_completed:
                # Delete "not yet completed" message if it exists
                if self._not_completed_message:
                    try:
                        self._not_completed_message.deleteLater()
                        self._not_completed_message = None
                    except RuntimeError:
                        pass  # Widget already deleted

                result_vector = proc.get("result_file_shp") or proc.get("result_file")
                dataset = proc.get("dataset")
                process_name = proc.get("name", "process")

                if result_vector or dataset:
                    self._add_section_header("Downloads")
                    self._add_download_buttons(result_vector, dataset, process_name)
                    self._downloads_section_exists = True

            # Track current situation for next refresh
            self._last_known_situation = situation

        except RuntimeError:
            # Widgets were deleted, skip update
            pass

    def _show_detail(self, proc, restore_scroll=None):
        """Display process detail. If restore_scroll is provided, restore scroll position after rendering."""
        self._clear_detail()

        # Large thumbnail
        thumb = QLabel()
        thumb.setFixedSize(DETAIL_THUMB, DETAIL_THUMB)
        thumb.setAlignment(Qt_AlignCenter)
        thumb.setStyleSheet("background: #f0f0f0; border-radius: 6px;")
        load_image(self.client, proc.get("thumbnail"), thumb, self._threads,
                   size=(DETAIL_THUMB, DETAIL_THUMB))
        self._detail_layout.addWidget(thumb, alignment=Qt_AlignCenter)

        # Save reference to thumbnail for silent updates
        self._detail_thumbnail = thumb

        # Name
        name = QLabel(proc.get("name", "Unnamed Process"))
        name.setStyleSheet("font-weight: bold; font-size: 16px;")
        name.setWordWrap(True)
        self._detail_layout.addWidget(name)

        # Situation badge
        situation = proc.get("situation", "idle") or "idle"
        label_text, color = SITUATION_LABELS.get(situation, _PREPARING)
        badge = QLabel(label_text)
        badge.setFixedHeight(22)
        badge.setStyleSheet(
            f"color: white; background: {color}; border-radius: 4px;"
            "padding: 2px 12px; font-size: 12px; font-weight: bold;"
        )
        self._detail_layout.addWidget(badge, alignment=Qt_AlignLeft)

        # Save reference to status badge for silent updates
        self._status_badge = badge

        # ── General Info ──
        self._add_section_header("General Info")

        # Create container layout for general info (so we can update it without rebuilding everything)
        general_info_container = QVBoxLayout()
        general_info_container.setSpacing(4)

        fees = proc.get("fees")
        self._add_info_row_to_layout(general_info_container, "Fees", f"€{fees}" if fees is not None else "-")

        create_date = proc.get("create_date", "-") or "-"
        self._add_info_row_to_layout(general_info_container, "Date", create_date)

        area = proc.get("area")
        self._add_info_row_to_layout(general_info_container, "Area", f"{area} km²" if area is not None else "-")

        self._detail_layout.addLayout(general_info_container)
        self._general_info_layout = general_info_container

        # ── Data Analytics (solution-specific) ──
        analytics = proc.get("analytics", {})
        if analytics:
            self._add_section_header("Data Analytics")

            # Create container layout for analytics (so we can update it without rebuilding everything)
            analytics_container = QVBoxLayout()
            analytics_container.setSpacing(4)

            for key, value in analytics.items():
                self._add_info_row_to_layout(analytics_container, key, value)

            self._detail_layout.addLayout(analytics_container)
            self._analytics_layout = analytics_container
        else:
            self._analytics_layout = None

        # ── Download / Load buttons (only when completed) ──
        is_completed = situation == "is"
        result_vector = proc.get("result_file_shp") or proc.get("result_file")
        dataset = proc.get("dataset")
        process_name = proc.get("name", "process")

        if is_completed and (result_vector or dataset):
            self._add_section_header("Downloads")
            self._add_download_buttons(result_vector, dataset, process_name)
            self._downloads_section_exists = True
        elif not is_completed:
            status_msg = QLabel(f"Process is not yet completed ({label_text})")
            status_msg.setStyleSheet("color: #888; font-size: 12px; font-style: italic; margin-top: 8px;")
            status_msg.setWordWrap(True)
            self._detail_layout.addWidget(status_msg)
            self._downloads_section_exists = False

            # Save reference so we can delete it during auto-refresh when completed
            self._not_completed_message = status_msg

        # Track current situation
        self._last_known_situation = situation

        self._detail_layout.addStretch()

        # Restore scroll position if this is a silent refresh
        if restore_scroll is not None:
            self._detail_scroll.verticalScrollBar().setValue(restore_scroll)

    def _add_download_buttons(self, result_vector, dataset, process_name):
        """Add download buttons to the detail panel. Should only be called once when process completes."""
        btn_style = (
            "QPushButton {{ background: {bg}; color: white; border: none;"
            "border-radius: 4px; padding: 8px; font-weight: bold; }}"
            "QPushButton:hover {{ background: {hover}; }}"
            "QPushButton:disabled {{ background: #bdc3c7; }}"
        )

        if result_vector:
            result_layer_name = f"{process_name} (result)"
            vec_btn = QPushButton()

            # Check if layer already exists in QGIS
            if _layer_exists_in_qgis(result_layer_name):
                vec_btn.setText("✓ Already Loaded")
                vec_btn.setEnabled(False)
                vec_btn.setStyleSheet(btn_style.format(bg="#10b981", hover="#10b981"))
            else:
                vec_btn.setText("Download Result (Shapefile)")
                vec_btn.setCursor(Qt_PointingHandCursor)
                vec_btn.setStyleSheet(btn_style.format(bg="#00856F", hover="#009980"))
                vec_btn.clicked.connect(
                    lambda _, url=result_vector, n=result_layer_name, btn=vec_btn: self._download_and_load(url, n, btn)
                )
            self._detail_layout.addWidget(vec_btn)

        if dataset:
            dataset_layer_name = f"{process_name} (dataset)"
            ds_btn = QPushButton()

            # Check if layer already exists in QGIS
            if _layer_exists_in_qgis(dataset_layer_name):
                ds_btn.setText("✓ Already Loaded")
                ds_btn.setEnabled(False)
                ds_btn.setStyleSheet(btn_style.format(bg="#10b981", hover="#10b981"))
            else:
                ds_btn.setText("Download Dataset (GeoTIFF)")
                ds_btn.setCursor(Qt_PointingHandCursor)
                ds_btn.setStyleSheet(btn_style.format(bg="#1E293B", hover="#334155"))
                ds_btn.clicked.connect(
                    lambda _, url=dataset, n=dataset_layer_name, btn=ds_btn: self._download_and_load(url, n, btn)
                )
            self._detail_layout.addWidget(ds_btn)

    # ── Download & load into QGIS ──

    def _download_and_load(self, url, layer_name, button):
        """Download file and load it into QGIS. Button reference is passed explicitly."""
        button.setEnabled(False)
        button.setText("Downloading...")

        thread = DownloadThread(self.client, url)

        def on_done(filepath):
            try:
                _add_layer_to_qgis(filepath, layer_name)
                # Update button to show it's loaded (keep disabled to prevent re-download)
                button.setText("✓ Loaded!")
                button.setStyleSheet(
                    "QPushButton { background: #10b981; color: white; border: none;"
                    "border-radius: 4px; padding: 8px; font-weight: bold; }"
                )
            except Exception as e:
                QMessageBox.warning(self, "Load Error", f"Downloaded but failed to load:\n{e}")
                button.setEnabled(True)
                button.setText("Retry Download")

        def on_err(msg):
            QMessageBox.warning(self, "Download Error", f"Failed to download:\n{msg}")
            button.setEnabled(True)
            button.setText("Retry Download")

        thread.finished.connect(on_done)
        thread.error.connect(on_err)
        self._threads.append(thread)
        thread.start()

    # ── Hide process ──

    def _on_hide_process(self, proc):
        process_name = proc.get("name", "this process")

        # Create message box with clickable link
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Hide Process")
        msg_box.setIcon(QMessageBox_Question)
        msg_box.setText(
            f'Are you sure you want to hide "{process_name}"?<br><br>'
            "This will hide the process. To fully delete it, visit:<br>"
            f'<a href="{APP_BASE_URL}/hidden-items">{APP_BASE_URL}/hidden-items</a>'
        )
        msg_box.setTextFormat(Qt_RichText)
        msg_box.setTextInteractionFlags(Qt_TextBrowserInteraction)
        msg_box.setStandardButtons(QMessageBox_Yes | QMessageBox_No)
        msg_box.setDefaultButton(QMessageBox_No)

        reply = exec_dialog(msg_box)
        if reply != QMessageBox_Yes:
            return

        slug = self._current_project.get("slug", "")
        process_id = proc.get("id")
        thread = HideProcessThread(self.client, slug, process_id)
        thread.finished.connect(lambda: self.load_processes(self._current_project))
        thread.error.connect(
            lambda msg: QMessageBox.warning(self, "Error", f"Failed to hide process:\n{msg}")
        )
        self._threads.append(thread)
        thread.start()

    # ── New process: embedded wizard ──

    def _on_new_process(self):
        if not self._current_project or not self.iface:
            return

        # Stop auto-refresh while in wizard
        self._stop_auto_refresh()

        # Remove previous wizard if any
        if self._wizard:
            self._body_stack.removeWidget(self._wizard)
            self._wizard.deleteLater()
            self._wizard = None

        slug = self._current_project.get("slug", "")
        title = self._current_project.get("title", "Project")

        self._wizard = CreateProcessWizard(
            self.client, self.iface, slug, title
        )
        self._wizard.process_created.connect(self._on_wizard_done)
        self._wizard.cancelled.connect(self._on_wizard_cancel)
        self._body_stack.addWidget(self._wizard)
        self._body_stack.setCurrentWidget(self._wizard)
        self._new_process_btn.hide()
        self._back_btn.show()

    def _on_wizard_done(self, result):
        self._body_stack.setCurrentWidget(self._list_view)
        self._new_process_btn.show()
        self._back_btn.hide()
        if self._wizard:
            self._body_stack.removeWidget(self._wizard)
            self._wizard.deleteLater()
            self._wizard = None
        self.load_processes(self._current_project)

    def _on_wizard_cancel(self):
        self._body_stack.setCurrentWidget(self._list_view)
        self._new_process_btn.show()
        self._back_btn.hide()
        if self._wizard:
            self._body_stack.removeWidget(self._wizard)
            self._wizard.deleteLater()
            self._wizard = None
