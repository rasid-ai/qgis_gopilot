from qgis.PyQt.QtWidgets import (
    QLabel, QPushButton, QHBoxLayout, QGridLayout,
    QVBoxLayout, QWidget, QScrollArea, QFrame, QMessageBox,
)
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from .compat import (
    Qt_AlignTop, Qt_AlignCenter, Qt_AlignHCenter, Qt_AlignLeft, Qt_AlignRight, Qt_PointingHandCursor,
    Qt_RichText, Qt_TextBrowserInteraction, Qt_transparent,
    QFrame_NoFrame, QFrame_StyledPanel, exec_dialog, QPainter_Antialiasing,
    QMessageBox_Question, QMessageBox_Yes, QMessageBox_No
)
from .image_loader import load_image
from . import theme_utils
from .config import APP_BASE_URL

CARD_WIDTH = 260
CARD_MIN_MARGIN = 40  # Minimum margin on each side


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


class FetchProjectsThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            projects = self.client.get_user_projects()
            self.finished.emit(projects)
        except Exception as e:
            self.error.emit(str(e))


class HideProjectThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, client, project_slug):
        super().__init__()
        self.client = client
        self.project_slug = project_slug

    def run(self):
        try:
            self.client.hide_project(self.project_slug)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class ProjectsPage(QWidget):
    project_opened = pyqtSignal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self._threads = []
        self._projects = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame_NoFrame)
        outer.addWidget(self.scroll)

        self._inner = QWidget()
        self.grid = QGridLayout(self._inner)
        self.grid.setSpacing(16)
        self.grid.setContentsMargins(20, 20, 20, 20)
        self.grid.setAlignment(Qt_AlignTop | Qt_AlignHCenter)
        self.scroll.setWidget(self._inner)

    def resizeEvent(self, event):
        """Recalculate grid layout when window is resized."""
        super().resizeEvent(event)
        if self._projects:
            self._layout_cards()

    def _calculate_columns(self):
        """Calculate how many columns can fit based on current width."""
        available_width = self.scroll.viewport().width() - (CARD_MIN_MARGIN * 2)
        spacing = self.grid.spacing()
        cols = max(1, int((available_width + spacing) / (CARD_WIDTH + spacing)))
        return cols

    def load_projects(self):
        self._clear_grid()
        loading = QLabel("Loading projects...")
        loading.setAlignment(Qt_AlignCenter)
        self.grid.addWidget(loading, 0, 0)

        self._fetch_thread = FetchProjectsThread(self.client)
        self._fetch_thread.finished.connect(self._on_projects_loaded)
        self._fetch_thread.error.connect(self._on_projects_error)
        self._fetch_thread.start()

    def _on_projects_loaded(self, projects):
        self._clear_grid()
        self._projects = projects

        if not projects:
            lbl = QLabel("No projects found.")
            lbl.setAlignment(Qt_AlignCenter)
            secondary_color = theme_utils.get_secondary_text_color()
            lbl.setStyleSheet(f"color: {secondary_color}; font-size: 13px;")
            self.grid.addWidget(lbl, 0, 0)
            return

        self._layout_cards()

    def _layout_cards(self):
        """Layout cards in grid based on current width."""
        self._clear_grid()
        if not self._projects:
            return

        cols = self._calculate_columns()
        row, col = 0, 0

        for proj in self._projects:
            card = self._create_card(proj)
            self.grid.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _on_projects_error(self, msg):
        self._clear_grid()
        lbl = QLabel(f"Failed to load projects: {msg}")
        lbl.setAlignment(Qt_AlignCenter)
        lbl.setWordWrap(True)
        self.grid.addWidget(lbl, 0, 0)

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _create_card(self, proj):
        card = QFrame()
        card.setFixedWidth(CARD_WIDTH)
        card.setFrameShape(QFrame_StyledPanel)
        card_bg = theme_utils.get_card_bg()
        card_border = theme_utils.get_card_border()
        hover_bg = theme_utils.get_hover_bg()
        card.setStyleSheet(f"""
            QFrame {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 6px;
            }}
            QFrame:hover {{
                background: {hover_bg};
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Thumbnail
        thumb = QLabel()
        thumb_height = int(CARD_WIDTH * 0.6)
        thumb.setFixedSize(CARD_WIDTH, thumb_height)
        thumb.setAlignment(Qt_AlignCenter)
        thumb_bg = theme_utils.get_sidebar_bg()
        thumb.setStyleSheet(f"background: {thumb_bg}; border-radius: 6px 6px 0 0; border: none;")
        load_image(self.client, proj.get("thumbnail"), thumb, self._threads,
                   size=(CARD_WIDTH, thumb_height))
        layout.addWidget(thumb)

        # Content section
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(8)

        # Project title
        title = QLabel(proj.get("title", "Untitled"))
        title.setWordWrap(True)
        title.setMaximumHeight(50)
        text_color = theme_utils.get_text_color()
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {text_color}; border: none;")
        content_layout.addWidget(title)

        # Solution type badge
        solution = proj.get("solution", {})
        solution_name = solution.get("name", "") if isinstance(solution, dict) else str(solution) if solution else "Unknown"
        solution_badge = QLabel(solution_name)
        solution_badge.setStyleSheet(
            f"background: {theme_utils.BRAND_PRIMARY}; color: white; border-radius: 4px;"
            f"padding: 4px 8px; font-size: 11px; border: none; font-weight: 600;"
        )
        content_layout.addWidget(solution_badge, alignment=Qt_AlignLeft)

        # Date and process count row
        info_row = QHBoxLayout()
        info_row.setSpacing(4)
        secondary_color = theme_utils.get_secondary_text_color()

        # Modified date
        modified_at = proj.get("system_modification_date", "")
        if modified_at:
            try:
                from datetime import datetime
                date_obj = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))
                date_str = date_obj.strftime("%m/%d/%Y")
            except ValueError:
                date_str = modified_at.split('T')[0] if 'T' in modified_at else modified_at

            date_lbl = QLabel(date_str)
            date_lbl.setStyleSheet(f"color: {secondary_color}; font-size: 11px; border: none;")
            info_row.addWidget(date_lbl)

        # Separator
        if modified_at:
            sep = QLabel("•")
            sep.setStyleSheet(f"color: {secondary_color}; font-size: 11px; border: none;")
            info_row.addWidget(sep)

        # Process count
        process_count = proj.get("processes_number", 0)
        process_lbl = QLabel(f"Processes: {process_count}")
        process_lbl.setStyleSheet(f"color: {secondary_color}; font-size: 11px; border: none;")
        info_row.addWidget(process_lbl)
        info_row.addStretch()

        content_layout.addLayout(info_row)

        # Tags
        tags = proj.get("tags", [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(4)
            tag_row.setAlignment(Qt_AlignLeft)

            for tag in tags[:3]:
                tag_name = tag.get("name", str(tag)) if isinstance(tag, dict) else str(tag)
                t = QLabel(f"#{tag_name}")
                t.setStyleSheet(
                    f"color: {theme_utils.BRAND_PRIMARY}; font-size: 10px; border: none;"
                )
                tag_row.addWidget(t)

            if len(tags) > 3:
                more = QLabel(f"+{len(tags) - 3}")
                more.setStyleSheet(f"color: {secondary_color}; font-size: 10px; border: none;")
                tag_row.addWidget(more)

            content_layout.addLayout(tag_row)

        layout.addWidget(content)

        # Button row
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(12, 0, 12, 12)
        btn_layout.setSpacing(8)

        # Open button
        open_btn = QPushButton("Open Project")
        open_btn.setCursor(Qt_PointingHandCursor)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.BRAND_PRIMARY};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {theme_utils.BRAND_HOVER};
            }}
        """)
        open_btn.clicked.connect(lambda _, p=proj: self.project_opened.emit(p))
        btn_layout.addWidget(open_btn, stretch=1)

        # Delete button
        del_btn = QPushButton()
        del_btn.setIcon(create_trash_icon(18, theme_utils.BRAND_DANGER))
        del_btn.setCursor(Qt_PointingHandCursor)
        del_btn.setFixedSize(36, 36)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {card_border};"
            f"border-radius: 4px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {theme_utils.get_danger_hover_bg()}; "
            f"border-color: {theme_utils.BRAND_DANGER}; }}"
        )
        del_btn.clicked.connect(lambda _, p=proj: self._on_hide(p))
        btn_layout.addWidget(del_btn)

        layout.addWidget(btn_container)

        return card

    def _on_hide(self, proj):
        title = proj.get("title", "this project")

        # Create message box with clickable link
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Hide Project")
        msg_box.setIcon(QMessageBox_Question)
        msg_box.setText(
            f"Are you sure you want to hide '{title}'?<br><br>"
            "This will move the project to your hidden items. "
            "To permanently delete it, visit:<br>"
            f'<a href="{APP_BASE_URL}/hidden-items">{APP_BASE_URL}/hidden-items</a>'
        )
        msg_box.setTextFormat(Qt_RichText)
        msg_box.setTextInteractionFlags(Qt_TextBrowserInteraction)
        msg_box.setStandardButtons(QMessageBox_Yes | QMessageBox_No)
        msg_box.setDefaultButton(QMessageBox_No)

        reply = exec_dialog(msg_box)
        if reply != QMessageBox_Yes:
            return

        slug = proj.get("slug", "")
        t = HideProjectThread(self.client, slug)
        t.finished.connect(self.load_projects)
        t.error.connect(lambda msg: QMessageBox.critical(
            self, "Hide Failed", f"Could not hide project:\n{msg}"
        ))
        self._threads.append(t)
        t.start()
