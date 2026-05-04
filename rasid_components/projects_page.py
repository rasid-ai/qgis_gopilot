from qgis.PyQt.QtWidgets import (
    QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QScrollArea, QFrame, QMessageBox,
)
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from .compat import (
    Qt_AlignTop, Qt_AlignCenter, Qt_AlignLeft, Qt_PointingHandCursor,
    Qt_RichText, Qt_TextBrowserInteraction, Qt_transparent,
    QFrame_NoFrame, QFrame_StyledPanel, exec_dialog, QPainter_Antialiasing,
    QMessageBox_Question, QMessageBox_Yes, QMessageBox_No
)
from .image_loader import load_image

LIST_THUMB = 40


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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame_NoFrame)
        outer.addWidget(self.scroll)

        self._inner = QWidget()
        self._list_layout = QVBoxLayout(self._inner)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(40, 6, 40, 6)
        self._list_layout.setAlignment(Qt_AlignTop)
        self.scroll.setWidget(self._inner)

    def load_projects(self):
        self._clear_list()
        loading = QLabel("Loading projects...")
        loading.setAlignment(Qt_AlignCenter)
        self._list_layout.addWidget(loading)

        self._fetch_thread = FetchProjectsThread(self.client)
        self._fetch_thread.finished.connect(self._on_projects_loaded)
        self._fetch_thread.error.connect(self._on_projects_error)
        self._fetch_thread.start()

    def _on_projects_loaded(self, projects):
        self._clear_list()
        if not projects:
            lbl = QLabel("No projects found.")
            lbl.setAlignment(Qt_AlignCenter)
            lbl.setStyleSheet("color: #888; font-size: 13px;")
            self._list_layout.addWidget(lbl)
            return

        for proj in projects:
            row = self._create_row(proj)
            self._list_layout.addWidget(row)

    def _on_projects_error(self, msg):
        self._clear_list()
        lbl = QLabel(f"Failed to load projects: {msg}")
        lbl.setAlignment(Qt_AlignCenter)
        lbl.setWordWrap(True)
        self._list_layout.addWidget(lbl)

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _create_row(self, proj):
        row = QFrame()
        row.setFrameShape(QFrame_StyledPanel)
        row.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 4px; }"
            "QFrame:hover { background: #e8f5f3; }"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(LIST_THUMB, LIST_THUMB)
        thumb.setAlignment(Qt_AlignCenter)
        thumb.setStyleSheet("background: #f0f0f0; border-radius: 4px; border: none;")
        load_image(self.client, proj.get("thumbnail"), thumb, self._threads,
                   size=(LIST_THUMB, LIST_THUMB))
        layout.addWidget(thumb)

        # Middle: name + tags + open button
        info = QVBoxLayout()
        info.setSpacing(3)

        name = QLabel(proj.get("title", "Untitled"))
        name.setStyleSheet("font-weight: bold; font-size: 12px; border: none;")
        info.addWidget(name)

        # Tags row
        tags = proj.get("tags", [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(4)
            tag_row.setAlignment(Qt_AlignLeft)
            for tag in tags[:5]:
                tag_name = tag.get("name", str(tag)) if isinstance(tag, dict) else str(tag)
                t = QLabel(tag_name)
                t.setStyleSheet(
                    "background: #009980; color: white; border-radius: 3px;"
                    "padding: 1px 6px; font-size: 9px; border: none;"
                )
                tag_row.addWidget(t)
            info.addLayout(tag_row)

        # Open button below tags
        open_btn = QPushButton("Open Project")
        
        open_btn.setFixedSize(120, 17)
        
        open_btn.setCursor(Qt_PointingHandCursor)
        open_btn.setStyleSheet(
            "QPushButton { background: #00856F; color: white; border: none;"
            "border-radius: 4px; padding: 4px 8px; font-size: 11px;}"
            "QPushButton:hover { background: #009980; }"
        )
        open_btn.clicked.connect(lambda _, p=proj: self.project_opened.emit(p))
        info.addWidget(open_btn, alignment=Qt_AlignLeft)

        layout.addLayout(info, stretch=1)

        # Right: hide button
        del_btn = QPushButton()
        del_btn.setIcon(create_trash_icon(20, "#e74c3c"))
        del_btn.setCursor(Qt_PointingHandCursor)
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            "QPushButton { background: white; border: 1px solid #ddd;"
            "border-radius: 4px; padding: 4px; }"
            "QPushButton:hover { background: #fee; border-color: #e74c3c; }"
        )
        del_btn.clicked.connect(lambda _, p=proj: self._on_hide(p))
        layout.addWidget(del_btn)

        return row

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
            '<a href="https://app.rasid.ai/hidden-items">https://app.rasid.ai/hidden-items</a>'
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
