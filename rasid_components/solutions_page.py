import re

from qgis.PyQt.QtWidgets import (
    QLabel, QPushButton, QGridLayout, QVBoxLayout, QHBoxLayout, QWidget,
    QScrollArea, QFrame, QDialog, QLineEdit,
    QMessageBox,
)
from qgis.PyQt.QtCore import QThread, pyqtSignal
from .compat import (
    Qt_AlignTop, Qt_AlignHCenter, Qt_AlignCenter, Qt_PlainText, Qt_PointingHandCursor,
    QFrame_NoFrame, QFrame_StyledPanel, exec_dialog, QDialog_Accepted
)
from .image_loader import load_image
from . import theme_utils


def strip_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

CARD_WIDTH = 240
THUMB_SIZE = 200
MAX_COLS = 3


class FetchSolutionsThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            solutions = self.client.get_solutions()
            self.finished.emit(solutions)
        except Exception as e:
            self.error.emit(str(e))


class CreateProjectThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, solution_slug, title, tags=None):
        super().__init__()
        self.client = client
        self.solution_slug = solution_slug
        self.title = title
        self.tags = tags

    def run(self):
        try:
            result = self.client.create_project(self.solution_slug, self.title, self.tags)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class SolutionsPage(QWidget):
    project_created = pyqtSignal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self._threads = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame_NoFrame)
        outer.addWidget(self.scroll)

        self._inner = QWidget()
        self.grid = QGridLayout(self._inner)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt_AlignTop | Qt_AlignHCenter)
        self.scroll.setWidget(self._inner)

    def load_solutions(self):
        self._clear_grid()
        loading = QLabel("Loading solutions...")
        loading.setAlignment(Qt_AlignCenter)
        self.grid.addWidget(loading, 0, 0)

        self._fetch_thread = FetchSolutionsThread(self.client)
        self._fetch_thread.finished.connect(self._on_solutions_loaded)
        self._fetch_thread.error.connect(self._on_solutions_error)
        self._fetch_thread.start()

    def _on_solutions_loaded(self, solutions):
        self._clear_grid()
        if not solutions:
            lbl = QLabel("No solutions found.")
            lbl.setAlignment(Qt_AlignCenter)
            self.grid.addWidget(lbl, 0, 0)
            return

        # Sort solutions: "prod" status first, "coming soon" last
        sorted_solutions = sorted(
            solutions,
            key=lambda s: (s.get("status", "") != "prod", s.get("name", ""))
        )

        row, col = 0, 0
        for sol in sorted_solutions:
            card = self._create_card(sol)
            self.grid.addWidget(card, row, col)
            col += 1
            if col >= MAX_COLS:
                col = 0
                row += 1

    def _on_solutions_error(self, msg):
        self._clear_grid()
        lbl = QLabel(f"Failed to load solutions: {msg}")
        lbl.setAlignment(Qt_AlignCenter)
        lbl.setWordWrap(True)
        self.grid.addWidget(lbl, 0, 0)

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _create_card(self, sol):
        card = QFrame()
        card.setFixedWidth(CARD_WIDTH)
        card.setFrameShape(QFrame_StyledPanel)
        card_bg = theme_utils.get_card_bg()
        card_border = theme_utils.get_card_border()
        card.setStyleSheet(f"""
            QFrame {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        thumb.setAlignment(Qt_AlignCenter)
        thumb_bg = theme_utils.get_sidebar_bg()
        thumb.setStyleSheet(f"background: {thumb_bg}; border-radius: 4px; border: none;")
        load_image(self.client, sol.get("image_url"), thumb, self._threads,
                   size=(THUMB_SIZE, THUMB_SIZE))
        layout.addWidget(thumb, alignment=Qt_AlignCenter)

        # Name
        name = QLabel(sol.get("name", "Unnamed"))
        name.setAlignment(Qt_AlignCenter)
        name.setWordWrap(True)
        text_color = theme_utils.get_text_color()
        name.setStyleSheet(f"font-weight: bold; font-size: 13px; border: none; color: {text_color};")
        layout.addWidget(name)

        # Description
        desc_text = strip_html(sol.get("description_html", ""))
        if desc_text:
            desc = QLabel(desc_text)
            desc.setTextFormat(Qt_PlainText)
            desc.setWordWrap(True)
            desc.setMaximumHeight(60)
            secondary_color = theme_utils.get_secondary_text_color()
            desc.setStyleSheet(
                f"color: {secondary_color}; font-size: 11px; border: none;"
                f"padding: 6px 2px; margin-top: 4px; margin-bottom: 4px;"
            )
            layout.addWidget(desc)

        # Price per km²
        price = sol.get("euro_per_km2")
        if price is not None:
            price_lbl = QLabel(f"€{price} / km²")
            price_lbl.setAlignment(Qt_AlignCenter)
            price_lbl.setStyleSheet(
                f"color: {theme_utils.BRAND_HOVER}; font-weight: bold; font-size: 12px; border: none;"
            )
            layout.addWidget(price_lbl)

        # Check if solution is available (status == "prod")
        status = sol.get("status", "")
        if status == "prod":
            btn = QPushButton("Create Project")
            btn.setCursor(Qt_PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme_utils.BRAND_PRIMARY}; color: white;
                    border: none; border-radius: 4px; padding: 6px;
                }}
                QPushButton:hover {{ background: {theme_utils.BRAND_HOVER}; }}
            """)
            btn.clicked.connect(lambda _, s=sol: self._on_create_project(s))
            layout.addWidget(btn)
        else:
            badge = QLabel("Coming Soon")
            badge.setAlignment(Qt_AlignCenter)
            badge.setStyleSheet(
                "background: #F59E0B; color: white; border-radius: 4px;"
                "padding: 6px; font-weight: bold; font-size: 12px; border: none;"
            )
            layout.addWidget(badge)

        layout.addStretch()
        return card

    def _on_create_project(self, solution):
        slug = solution.get("slug", "")
        sol_name = solution.get("name", "Solution")

        # Minimal modern dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Create Project")
        dlg.setMinimumWidth(420)
        dialog_bg = theme_utils.get_card_bg()
        dlg.setStyleSheet(f"background: {dialog_bg};")
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(24, 24, 24, 24)
        dlg_layout.setSpacing(18)

        # Solution label
        sol_label = QLabel(f"Solution: {sol_name}")
        text_color = theme_utils.get_text_color()
        sol_label.setStyleSheet(f"font-weight: bold; color: {text_color}; font-size: 13px;")
        dlg_layout.addWidget(sol_label)

        # Project title
        dlg_layout.addWidget(QLabel("Project Title:"))
        title_input = QLineEdit()
        title_input.setPlaceholderText("Enter project title...")
        input_border = theme_utils.get_card_border()
        title_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                border: 2px solid {input_border};
                border-radius: 6px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {theme_utils.BRAND_PRIMARY};
            }}
        """)
        dlg_layout.addWidget(title_input)

        # Tags
        dlg_layout.addWidget(QLabel("Tags (separated by spaces):"))
        tags_input = QLineEdit()
        tags_input.setPlaceholderText("e.g. cloud detection urban")
        tags_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                border: 2px solid {input_border};
                border-radius: 6px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {theme_utils.BRAND_PRIMARY};
            }}
        """)
        dlg_layout.addWidget(tags_input)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt_PointingHandCursor)
        cancel_bg = theme_utils.get_sidebar_bg()
        cancel_hover = theme_utils.get_hover_bg()
        cancel_text = theme_utils.get_text_color()
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {cancel_bg};
                color: {cancel_text};
                border: 2px solid {input_border};
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {cancel_hover};
            }}
        """)
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)

        create_btn = QPushButton("Create")
        create_btn.setCursor(Qt_PointingHandCursor)
        create_btn.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.BRAND_PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {theme_utils.BRAND_HOVER};
            }}
        """)
        create_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(create_btn)

        dlg_layout.addLayout(btn_layout)

        if exec_dialog(dlg) != QDialog_Accepted:
            return

        title = title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please enter a project title.")
            return

        tags = [t.strip() for t in tags_input.text().split() if t.strip()] or None

        self._create_thread = CreateProjectThread(self.client, slug, title, tags)
        self._create_thread.finished.connect(self._on_project_created)
        self._create_thread.error.connect(self._on_create_error)
        self._create_thread.start()

    def _on_project_created(self, result):
        QMessageBox.information(
            self, "Project Created",
            f"Project '{result.get('title', '')}' created successfully!"
        )
        self.project_created.emit(result)

    def _on_create_error(self, msg):
        QMessageBox.critical(self, "Error", f"Failed to create project:\n{msg}")
