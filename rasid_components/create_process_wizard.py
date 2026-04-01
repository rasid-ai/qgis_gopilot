"""Dynamic process creation wizard — embedded as a QWidget page."""
import json

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QDateEdit, QFileDialog, QWidget, QMessageBox, QRadioButton,
    QButtonGroup, QGroupBox, QTextEdit, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QSpinBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDate
from qgis.core import (
    QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsMapLayer,
)
from .aoi_tool import AoiDrawTool


# ---------------------------------------------------------------------------
#  Background threads
# ---------------------------------------------------------------------------

class FetchConfigThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, project_slug):
        super().__init__()
        self.client = client
        self.project_slug = project_slug

    def run(self):
        try:
            cfg = self.client.get_process_config(self.project_slug)
            self.finished.emit(cfg)
        except Exception as e:
            self.error.emit(str(e))


class SearchCatalogueThread(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, client, payload):
        super().__init__()
        self.client = client
        self.payload = payload

    def run(self):
        try:
            res = self.client.search_catalogue(self.payload)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class CreateProcessThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, project_slug, payload, files=None):
        super().__init__()
        self.client = client
        self.project_slug = project_slug
        self.payload = payload
        self.files = files

    def run(self):
        try:
            res = self.client.create_process(
                self.project_slug, self.payload, self.files
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
#  Wizard widget (embedded, not a popup)
# ---------------------------------------------------------------------------

BTN_STYLE = (
    "QPushButton {{ background: {bg}; color: white; border: none;"
    "border-radius: 4px; padding: 8px 16px; font-weight: bold; }}"
    "QPushButton:hover {{ background: {hover}; }}"
    "QPushButton:disabled {{ background: #bdc3c7; }}"
)


class CreateProcessWizard(QWidget):
    """Dynamic form that adapts to the solution's process-config."""

    process_created = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, client, iface, project_slug, project_title, parent=None):
        super().__init__(parent)
        self.client = client
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.project_slug = project_slug
        self._threads = []
        self._aoi_coords = None
        self._catalogue_results_raw = None
        self._config = {}
        self._draw_tool = None
        self._prev_map_tool = None
        self._upload_path = None
        self._parent_dialog = None

        # Main layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setStyleSheet("background: #f7f7f7; border-bottom: 1px solid #ddd;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 8, 12, 8)

        title_lbl = QLabel(f"New Process — {project_title}")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()
        outer.addWidget(title_bar)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, stretch=1)

        self._form = QWidget()
        self._form_layout = QVBoxLayout(self._form)
        self._form_layout.setSpacing(12)
        self._form_layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(self._form)

        # Loading state
        self._loading_label = QLabel("Loading process configuration...")
        self._loading_label.setAlignment(Qt.AlignCenter)
        self._form_layout.addWidget(self._loading_label)

        # Bottom button bar
        btn_bar = QFrame()
        btn_bar.setStyleSheet("background: #f7f7f7; border-top: 1px solid #ddd;")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(12, 8, 12, 8)

        self._submit_btn = QPushButton("Create Process")
        self._submit_btn.setStyleSheet(BTN_STYLE.format(bg="#00856F", hover="#009980"))
        self._submit_btn.setCursor(Qt.PointingHandCursor)
        self._submit_btn.setEnabled(False)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self._submit_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(BTN_STYLE.format(bg="#e74c3c", hover="#c0392b"))
        self._cancel_btn.clicked.connect(self.cancelled.emit)
        btn_layout.addWidget(self._cancel_btn)

        btn_layout.addStretch()
        outer.addWidget(btn_bar)

        # Fetch config
        self._fetch_config()

    # ------------------------------------------------------------------
    #  Config fetch
    # ------------------------------------------------------------------

    def _fetch_config(self):
        t = FetchConfigThread(self.client, self.project_slug)
        t.finished.connect(self._on_config_loaded)
        t.error.connect(self._on_config_error)
        self._threads.append(t)
        t.start()

    def _on_config_error(self, msg):
        self._loading_label.setText(f"Failed to load config: {msg}")

    def _on_config_loaded(self, config):
        self._config = config
        self._loading_label.hide()
        self._build_form(config)
        self._submit_btn.setEnabled(True)

    # ------------------------------------------------------------------
    #  Build dynamic form
    # ------------------------------------------------------------------

    def _build_form(self, config):
        supports = config.get("supports", {})
        fields = config.get("fields", {})
        sentinel_cfg = config.get("sentinel", {})

        # Process name
        grp = self._make_group("Process Name")
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter a name for this process")
        grp.layout().addWidget(self._name_input)

        # Dataset type selection
        supported_types = []
        type_labels = {
            "mapbox": "Mapbox Tiles",
            "sentinel_catalogue": "Sentinel Catalogue",
            "sentinel_series": "Sentinel Time Series",
            "planet": "Planet Imagery",
            "raster_upload": "Upload Raster",
            "raster_link": "Raster Link",
        }
        for key, label in type_labels.items():
            if supports.get(key):
                supported_types.append((key, label))

        self._dataset_type = None
        self._type_radios = {}

        if len(supported_types) == 1:
            self._dataset_type = supported_types[0][0]
        elif len(supported_types) > 1:
            grp = self._make_group("Dataset Type")
            self._type_btn_group = QButtonGroup(self)
            for i, (key, label) in enumerate(supported_types):
                rb = QRadioButton(label)
                self._type_radios[key] = rb
                self._type_btn_group.addButton(rb, i)
                grp.layout().addWidget(rb)
            # NOTE: connect signals and set default AFTER all sections are built (see below)

        # --- AOI section ---
        self._aoi_group = self._make_group("Area of Interest (AOI)")
        aoi_layout = self._aoi_group.layout()

        aoi_btn_row = QHBoxLayout()
        self._draw_btn = QPushButton("Draw on Map")
        self._draw_btn.setCursor(Qt.PointingHandCursor)
        self._draw_btn.setStyleSheet(BTN_STYLE.format(bg="#1E293B", hover="#334155"))
        self._draw_btn.clicked.connect(self._start_draw_aoi)
        aoi_btn_row.addWidget(self._draw_btn)

        self._layer_combo = QComboBox()
        self._layer_combo.addItem("-- From Layer --")
        # Only show vector layers (shapefiles, GeoJSON, etc.) - exclude rasters (TIFFs)
        vector_layer_count = 0
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                self._layer_combo.addItem(layer.name(), layer.id())
                vector_layer_count += 1

        # Add helpful message if no vector layers available
        if vector_layer_count == 0:
            self._layer_combo.addItem("(No vector layers in project)", None)
            self._layer_combo.setEnabled(False)

        self._layer_combo.currentIndexChanged.connect(self._on_layer_selected)
        aoi_btn_row.addWidget(self._layer_combo)
        aoi_layout.addLayout(aoi_btn_row)

        self._aoi_display = QTextEdit()
        self._aoi_display.setReadOnly(True)
        self._aoi_display.setMaximumHeight(60)
        self._aoi_display.setPlaceholderText("No AOI set. Draw on map or pick from layer.")
        aoi_layout.addWidget(self._aoi_display)

        # --- Date range ---
        sentinel_fields = sentinel_cfg.get("fields", {})
        start_date_cfg = sentinel_fields.get("start_date", {})
        end_date_cfg = sentinel_fields.get("end_date", {})

        start_label = start_date_cfg.get("label", "Start Date")
        self._end_date_hidden = end_date_cfg.get("hidden", False)

        self._date_group = self._make_group("Date Range")
        date_layout = self._date_group.layout()
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel(f"{start_label}:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(QDate.currentDate().addMonths(-1))
        date_row.addWidget(self._start_date)

        end_label = end_date_cfg.get("label", "End Date")
        self._end_date_label = QLabel(f"{end_label}:")
        date_row.addWidget(self._end_date_label)
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        date_row.addWidget(self._end_date)
        date_layout.addLayout(date_row)

        # --- Sentinel settings (populated from config) ---
        self._sentinel_group = self._make_group("Sentinel Settings")
        s_layout = self._sentinel_group.layout()
        sentinel_choices = sentinel_cfg.get("choices", {})
        sentinel_defaults = sentinel_cfg.get("defaults", {})

        # Data Collection
        s_layout.addWidget(QLabel("Data Collection:"))
        self._sentinel_collection = QComboBox()
        for ch in sentinel_choices.get("data_collection", []):
            self._sentinel_collection.addItem(ch.get("label", ch.get("value")), ch.get("value"))
        s_layout.addWidget(self._sentinel_collection)

        # Eval Script
        s_layout.addWidget(QLabel("Eval Script:"))
        self._sentinel_eval_script = QComboBox()
        for ch in sentinel_choices.get("eval_script", []):
            self._sentinel_eval_script.addItem(ch.get("label", "").strip(), ch.get("value"))
        s_layout.addWidget(self._sentinel_eval_script)

        # Sort By
        s_layout.addWidget(QLabel("Sort By:"))
        self._sentinel_sort = QComboBox()
        for ch in sentinel_choices.get("sort_by", []):
            self._sentinel_sort.addItem(ch.get("label", ch.get("value")), ch.get("value"))
        s_layout.addWidget(self._sentinel_sort)

        # Apply sentinel date defaults
        if sentinel_defaults.get("start_date"):
            self._start_date.setDate(QDate.fromString(sentinel_defaults["start_date"], "yyyy-MM-dd"))
        if sentinel_defaults.get("end_date"):
            self._end_date.setDate(QDate.fromString(sentinel_defaults["end_date"], "yyyy-MM-dd"))

        # --- Catalogue search ---
        self._catalogue_group = self._make_group("Catalogue Search")
        cat_layout = self._catalogue_group.layout()

        self._search_btn = QPushButton("Search Available Imagery")
        self._search_btn.setCursor(Qt.PointingHandCursor)
        self._search_btn.setStyleSheet(BTN_STYLE.format(bg="#1E293B", hover="#334155"))
        self._search_btn.clicked.connect(self._on_search_catalogue)
        cat_layout.addWidget(self._search_btn)

        self._catalogue_list = QListWidget()
        self._catalogue_list.setMaximumHeight(150)
        cat_layout.addWidget(self._catalogue_list)

        # --- Zoom level (for mapbox) ---
        defaults = config.get("defaults", {})
        self._zoom_group = self._make_group("Zoom Level")
        z_layout = self._zoom_group.layout()
        self._zoom_spin = QSpinBox()
        self._zoom_spin.setRange(0, 20)
        self._zoom_spin.setValue(defaults.get("zoom_level", 18))
        z_layout.addWidget(self._zoom_spin)

        # --- Raster upload ---
        self._upload_group = self._make_group("Upload Raster (TIFF)")
        u_layout = self._upload_group.layout()
        upload_row = QHBoxLayout()
        self._upload_label = QLabel("No file selected")
        upload_row.addWidget(self._upload_label, stretch=1)
        upload_btn = QPushButton("Choose File")
        upload_btn.clicked.connect(self._on_choose_file)
        upload_row.addWidget(upload_btn)
        u_layout.addLayout(upload_row)

        # --- Raster link ---
        self._link_group = self._make_group("Raster Link")
        l_layout = self._link_group.layout()
        self._link_input = QLineEdit()
        self._link_input.setPlaceholderText("https://example.com/raster.tif")
        l_layout.addWidget(self._link_input)

        self._form_layout.addStretch()

        # Now that all sections exist, connect radio signals and set default
        if self._type_radios:
            for key, rb in self._type_radios.items():
                rb.toggled.connect(lambda checked, k=key: self._on_type_changed(k, checked))
            first_key = supported_types[0][0]
            self._type_radios[first_key].setChecked(True)
        self._update_sections()

    def _make_group(self, title):
        grp = QGroupBox(title)
        grp.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #ddd;"
            "border-radius: 4px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )
        layout = QVBoxLayout()
        grp.setLayout(layout)
        self._form_layout.addWidget(grp)
        return grp

    # ------------------------------------------------------------------
    #  Section visibility
    # ------------------------------------------------------------------

    def _on_type_changed(self, key, checked):
        if checked:
            self._dataset_type = key
            self._update_sections()

    def _update_sections(self):
        dt = self._dataset_type
        self._aoi_group.setVisible(dt in ("mapbox", "sentinel_catalogue", "sentinel_series", "planet"))
        self._date_group.setVisible(dt in ("sentinel_catalogue", "sentinel_series", "planet"))
        self._sentinel_group.setVisible(dt == "sentinel_catalogue")
        self._catalogue_group.setVisible(dt in ("sentinel_catalogue", "planet"))
        # Only show zoom level if this is the pure mapbox solution (only supports mapbox, nothing else)
        supports = self._config.get("supports", {})
        is_pure_mapbox = (dt == "mapbox" and
                          supports.get("mapbox") and
                          not any(supports.get(k) for k in ["sentinel_catalogue", "sentinel_series", "planet", "raster_upload", "raster_link"]))
        self._zoom_group.setVisible(is_pure_mapbox)
        self._upload_group.setVisible(dt == "raster_upload")
        self._link_group.setVisible(dt == "raster_link")

        # Show/hide end date based on config's hidden flag
        if self._end_date_hidden:
            self._end_date.hide()
            self._end_date_label.hide()
        else:
            self._end_date.show()
            self._end_date_label.show()

    # ------------------------------------------------------------------
    #  AOI drawing
    # ------------------------------------------------------------------

    def _start_draw_aoi(self):
        self._prev_map_tool = self.canvas.mapTool()
        self._draw_tool = AoiDrawTool(self.canvas)
        self._draw_tool.polygon_finished.connect(self._on_aoi_drawn)
        self.canvas.setMapTool(self._draw_tool)
        # Find and minimize the parent dialog so the map is visible
        self._parent_dialog = self.window()
        if self._parent_dialog:
            self._parent_dialog.showMinimized()
        self.iface.messageBar().pushInfo(
            "RASID", "Left-click to add points, right-click to finish polygon."
        )

    def _on_aoi_drawn(self, coords):
        self._aoi_coords = coords
        self._aoi_display.setPlainText(json.dumps(coords))
        if self._prev_map_tool:
            self.canvas.setMapTool(self._prev_map_tool)
        if self._parent_dialog:
            self._parent_dialog.showNormal()
            self._parent_dialog.activateWindow()

    def _on_layer_selected(self, index):
        if index <= 0:
            return
        layer_id = self._layer_combo.itemData(index)
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        # Validate layer type
        from qgis.core import QgsVectorLayer, QgsWkbTypes
        if not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(
                self, "Invalid Layer Type",
                "Please select a vector layer (shapefile, GeoJSON, etc.)"
            )
            self._layer_combo.setCurrentIndex(0)
            return

        # Check if layer has features
        if layer.featureCount() == 0:
            QMessageBox.warning(
                self, "Empty Layer",
                "The selected layer has no features. Please select a layer with at least one polygon."
            )
            self._layer_combo.setCurrentIndex(0)
            return

        # Get features (selected or all)
        feats = layer.selectedFeatures() if layer.selectedFeatureCount() > 0 else list(layer.getFeatures())
        if not feats:
            QMessageBox.warning(
                self, "No Features",
                "No features found in the selected layer."
            )
            self._layer_combo.setCurrentIndex(0)
            return

        # Check geometry type
        geom = feats[0].geometry()
        if geom.isEmpty():
            QMessageBox.warning(
                self, "Invalid Geometry",
                "The selected feature has no geometry."
            )
            self._layer_combo.setCurrentIndex(0)
            return

        geom_type = geom.wkbType()
        is_polygon = QgsWkbTypes.flatType(geom_type) == QgsWkbTypes.Polygon
        is_multipolygon = QgsWkbTypes.flatType(geom_type) == QgsWkbTypes.MultiPolygon

        if not (is_polygon or is_multipolygon):
            QMessageBox.warning(
                self, "Invalid Geometry Type",
                "Please select a layer with Polygon or MultiPolygon geometry.\n\n"
                f"Current geometry type: {QgsWkbTypes.displayString(geom_type)}"
            )
            self._layer_combo.setCurrentIndex(0)
            return

        # Warn if multiple features
        if len(feats) > 1:
            reply = QMessageBox.question(
                self, "Multiple Features",
                f"The layer has {len(feats)} features. Only the first feature will be used.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self._layer_combo.setCurrentIndex(0)
                return

        # Transform to WGS84
        src_crs = layer.crs()
        dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

        try:
            if src_crs != dst_crs:
                geom.transform(xform)

            # Extract polygon coordinates
            poly = None
            if is_polygon:
                poly = geom.asPolygon()
            elif is_multipolygon:
                mpoly = geom.asMultiPolygon()
                if mpoly and len(mpoly) > 0:
                    poly = mpoly[0]
                    if len(mpoly) > 1:
                        QMessageBox.information(
                            self, "MultiPolygon Detected",
                            f"The feature is a MultiPolygon with {len(mpoly)} parts.\n"
                            "Only the first polygon will be used as AOI."
                        )

            if poly and len(poly) > 0:
                ring = poly[0]
                self._aoi_coords = [[p.x(), p.y()] for p in ring]
                self._aoi_display.setPlainText(json.dumps(self._aoi_coords))
                self._layer_combo.setCurrentIndex(0)
                return
            else:
                QMessageBox.warning(
                    self, "Invalid Polygon",
                    "Could not extract polygon coordinates from the selected feature."
                )
                self._layer_combo.setCurrentIndex(0)
                return

        except Exception as e:
            QMessageBox.critical(
                self, "Error Processing Layer",
                f"An error occurred while processing the layer:\n\n{str(e)}"
            )
            self._layer_combo.setCurrentIndex(0)
            return

    # ------------------------------------------------------------------
    #  Catalogue search
    # ------------------------------------------------------------------

    def _on_search_catalogue(self):
        if not self._aoi_coords or len(self._aoi_coords) < 3:
            QMessageBox.warning(self, "AOI Required", "Draw or select an AOI first.")
            return

        lons = [c[0] for c in self._aoi_coords]
        lats = [c[1] for c in self._aoi_coords]
        # Send bbox as list - the client will convert to string format if needed
        bbox = [min(lons), min(lats), max(lons), max(lats)]

        start = self._start_date.date().toString("yyyy-MM-dd")
        end = self._end_date.date().toString("yyyy-MM-dd")

        data_collection = self._sentinel_collection.currentData() or self._sentinel_collection.currentText()
        sort_by = self._sentinel_sort.currentData() or self._sentinel_sort.currentText()

        payload = {
            "bbox": bbox,  # Pass as list, not JSON string
            "sentinel_start_date": start,
            "sentinel_end_date": end,
            "sentinel_data_collection": data_collection,
            "sentinel_sort_by": sort_by,
        }

        if self._dataset_type == "planet":
            payload["planet_start_date"] = start
            payload["planet_end_date"] = end

        self._search_btn.setEnabled(False)
        self._search_btn.setText("Searching...")

        t = SearchCatalogueThread(self.client, payload)
        t.finished.connect(self._on_search_results)
        t.error.connect(self._on_search_error)
        self._threads.append(t)
        t.start()

    def _on_search_results(self, results):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Search Available Imagery")
        self._catalogue_list.clear()

        items = results if isinstance(results, list) else results.get("features", results.get("results", []))
        self._catalogue_results_raw = items

        if not items:
            self._catalogue_list.addItem("No imagery found for this area and date range.")
            return

        for i, item in enumerate(items):
            props = item.get("properties", item) if isinstance(item, dict) else {}
            item_id = props.get("id", item.get("id", f"Image {i + 1}"))
            date = props.get("datetime", props.get("acquired", ""))
            cloud = props.get("eo:cloud_cover", props.get("cloud_cover", ""))
            label = f"{item_id}"
            if date:
                label += f"  |  {date[:10]}"
            if cloud != "":
                label += f"  |  Cloud: {cloud}%"
            li = QListWidgetItem(label)
            li.setData(Qt.UserRole, i)
            self._catalogue_list.addItem(li)

        self._catalogue_list.setCurrentRow(0)

    def _on_search_error(self, msg):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Search Available Imagery")
        QMessageBox.warning(self, "Search Failed", msg)

    # ------------------------------------------------------------------
    #  File upload
    # ------------------------------------------------------------------

    def _on_choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Raster File", "", "TIFF Files (*.tif *.tiff)"
        )
        if path:
            self._upload_path = path
            self._upload_label.setText(path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])

    # ------------------------------------------------------------------
    #  Submit
    # ------------------------------------------------------------------

    def _on_submit(self):
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a process name.")
            return

        dt = self._dataset_type
        if not dt:
            QMessageBox.warning(self, "Missing Type", "Select a dataset type.")
            return

        # Get default zoom level from config
        defaults = self._config.get("defaults", {})
        default_zoom = defaults.get("zoom_level", 18)

        payload = {
            "name": name,
            "zoom_level": default_zoom,  # Always include default, will override for mapbox if needed
        }
        files = None

        # Resolve dataset_choice_id from config's dataset_type_to_id mapping
        # API uses short keys (mapb, lras, uras, sent, plan) — map from our full names
        _type_abbrev = {
            "mapbox": "mapb",
            "raster_link": "lras",
            "raster_upload": "uras",
            "sentinel_catalogue": "sent",
            "sentinel_series": "sts",
            "planet": "plan",
        }
        type_to_id = self._config.get("dataset_type_to_id", {})
        abbrev = _type_abbrev.get(dt, dt)
        choice_id = type_to_id.get(abbrev) or type_to_id.get(dt)

        if choice_id is not None:
            payload["dataset_choice_id"] = choice_id

        aoi_json = json.dumps(self._aoi_coords) if self._aoi_coords else None

        if dt == "mapbox":
            if not aoi_json:
                QMessageBox.warning(self, "Missing AOI", "Draw or select an AOI.")
                return
            payload["mapbox_aoi"] = aoi_json
            # Override zoom level if user can see the spinner (pure mapbox solution)
            if self._zoom_group.isVisible():
                payload["zoom_level"] = self._zoom_spin.value()

        elif dt == "sentinel_catalogue":
            if not aoi_json:
                QMessageBox.warning(self, "Missing AOI", "Draw or select an AOI.")
                return
            payload["sentinel_aoi"] = aoi_json
            payload["sentinel_data_collection"] = self._sentinel_collection.currentData() or self._sentinel_collection.currentText()
            payload["sentinel_start_date"] = self._start_date.date().toString("yyyy-MM-dd")
            payload["sentinel_end_date"] = self._end_date.date().toString("yyyy-MM-dd")
            payload["sentinel_sort_by"] = self._sentinel_sort.currentData() or self._sentinel_sort.currentText()
            # Use fixed_value from config if set, otherwise use dropdown selection
            sentinel_fields = self._config.get("sentinel", {}).get("fields", {})
            eval_fixed = sentinel_fields.get("eval_script", {}).get("fixed_value")
            if eval_fixed:
                payload["sentinel_eval_script"] = eval_fixed
            else:
                eval_script = self._sentinel_eval_script.currentData() or self._sentinel_eval_script.currentText()
                if eval_script:
                    payload["sentinel_eval_script"] = eval_script
            selected = self._catalogue_list.currentItem()
            if selected and self._catalogue_results_raw:
                idx = selected.data(Qt.UserRole)
                if idx is not None and idx < len(self._catalogue_results_raw):
                    payload["sentinel_search_results"] = json.dumps(
                        self._catalogue_results_raw[idx]
                    )

        elif dt == "sentinel_series":
            if not aoi_json:
                QMessageBox.warning(self, "Missing AOI", "Draw or select an AOI.")
                return
            sentinel_fields = self._config.get("sentinel", {}).get("fields", {})
            start_date = self._start_date.date().toString("yyyy-MM-dd")
            end_date_cfg = sentinel_fields.get("end_date", {})
            if end_date_cfg.get("hidden", False):
                end_date = start_date
            else:
                end_date = self._end_date.date().toString("yyyy-MM-dd")
            payload["sentinel_aoi"] = aoi_json
            payload["sentinel_start_date"] = start_date
            payload["sentinel_end_date"] = end_date
            # Use fixed values from config for all hidden fields
            payload["sentinel_data_collection"] = sentinel_fields.get(
                "data_collection", {}).get("fixed_value", "sentinel-2-l1c")
            payload["sentinel_eval_script"] = sentinel_fields.get(
                "eval_script", {}).get("fixed_value", "s2-l1c-all-bands")
            payload["sentinel_series_interval_range"] = sentinel_fields.get(
                "series_interval_range", {}).get("fixed_value", 7)
            payload["sentinel_series_gap_between_intervals"] = sentinel_fields.get(
                "series_gap_between_intervals", {}).get("fixed_value", 0)

        elif dt == "planet":
            if not aoi_json:
                QMessageBox.warning(self, "Missing AOI", "Draw or select an AOI.")
                return
            payload["planet_aoi"] = aoi_json
            payload["planet_start_date"] = self._start_date.date().toString("yyyy-MM-dd")
            payload["planet_end_date"] = self._end_date.date().toString("yyyy-MM-dd")
            selected = self._catalogue_list.currentItem()
            if selected and self._catalogue_results_raw:
                idx = selected.data(Qt.UserRole)
                if idx is not None and idx < len(self._catalogue_results_raw):
                    payload["planet_search_results"] = json.dumps(
                        self._catalogue_results_raw[idx]
                    )

        elif dt == "raster_upload":
            if not self._upload_path:
                QMessageBox.warning(self, "Missing File", "Choose a TIFF file to upload.")
                return
            files = {"upload_raster": open(self._upload_path, "rb")}

        elif dt == "raster_link":
            link = self._link_input.text().strip()
            if not link:
                QMessageBox.warning(self, "Missing Link", "Enter a raster URL.")
                return
            payload["link_to_raster"] = link

        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("Creating...")

        t = CreateProcessThread(self.client, self.project_slug, payload, files)
        t.finished.connect(self._on_created)
        t.error.connect(self._on_create_error)
        self._threads.append(t)
        t.start()

    def _on_created(self, result):
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("Create Process")
        QMessageBox.information(
            self, "Process Created",
            "Process created successfully!"
        )
        self.process_created.emit(result)

    def _on_create_error(self, msg):
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("Create Process")
        QMessageBox.critical(self, "Error", f"Failed to create process:\n{msg}")
