# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtWidgets import (
    QDialog,
    QStackedWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame,
)
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from .rasid_components.solutions_page import SolutionsPage
from .rasid_components.projects_page import ProjectsPage
from .rasid_components.processes_page import ProcessesPage
from .rasid_components.feedback_dialog import FeedbackDialog
from .rasid_components.about_page import AboutPage


SIDEBAR_WIDTH = 190

NAV_BTN_STYLE = """
    QPushButton {{
        background: {bg}; color: {fg}; border: none;
        border-radius: 6px; padding: 10px 0; font-size: 13px;
        font-weight: bold; text-align: center;
    }}
    QPushButton:hover {{ background: {hover}; }}
"""

ACTIVE_BG = "#00856F"
ACTIVE_HOVER = "#009980"
NORMAL_BG = "transparent"
NORMAL_HOVER = "#e8f5f3"


class FetchProfileThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            data = self.client.get_profile()
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class RasidPluginDialog(QDialog):
    def __init__(self, client=None, iface=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RASID")
        self.resize(1087, 500)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.client = client
        self.iface = iface

        # ── Main horizontal layout ──
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(
            "QFrame#sidebar { background: #f7f8fa; border-right: 1px solid #ddd; }"
        )
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(6)

        # Logo
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setFixedHeight(90)
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(logo_path):
            pm = QPixmap(logo_path)
            logo_label.setPixmap(pm.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo_label.setText("RASID")
            logo_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        sidebar_layout.addWidget(logo_label)

        # Welcome + balance (compact)
        self._welcome_label = QLabel("")
        self._welcome_label.setWordWrap(True)
        self._welcome_label.setAlignment(Qt.AlignCenter)
        self._welcome_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50; margin: 0; padding: 0;")
        self._welcome_label.setTextFormat(Qt.RichText)
        self._welcome_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._welcome_label.setOpenExternalLinks(True)
        self._welcome_label.setCursor(Qt.PointingHandCursor)
        sidebar_layout.addWidget(self._welcome_label)

        self._balance_label = QLabel("")
        self._balance_label.setAlignment(Qt.AlignCenter)
        self._balance_label.setStyleSheet(
            "font-size: 11px; color: #00856F; font-weight: bold; margin: 0; padding: 0 0 4px 0;"
        )
        self._balance_label.setTextFormat(Qt.RichText)
        self._balance_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._balance_label.setOpenExternalLinks(True)
        self._balance_label.setCursor(Qt.PointingHandCursor)
        sidebar_layout.addWidget(self._balance_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        sep.setFixedHeight(2)
        sidebar_layout.addWidget(sep)

        # Navigation buttons
        self._nav_buttons = []
        self.btn_solutions = self._make_nav_btn("Solutions", sidebar_layout)
        self.btn_projects = self._make_nav_btn("Projects", sidebar_layout)

        # Feedback button (opens dialog, not navigation)
        self.btn_feedback = QPushButton("Feedback")
        self.btn_feedback.setCursor(Qt.PointingHandCursor)
        self.btn_feedback.setStyleSheet(NAV_BTN_STYLE.format(
            bg=NORMAL_BG, fg="#2c3e50", hover=NORMAL_HOVER
        ))
        sidebar_layout.addWidget(self.btn_feedback)

        self.btn_about = self._make_nav_btn("About Us", sidebar_layout)

        sidebar_layout.addStretch()

        # Logout at bottom
        self.btn_logout = QPushButton("Log Out")
        self.btn_logout.setCursor(Qt.PointingHandCursor)
        self.btn_logout.setStyleSheet(
            "QPushButton { background: transparent; color: #e74c3c; border: 1px solid #e74c3c;"
            "border-radius: 6px; padding: 8px 0; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #fdeaea; }"
        )
        sidebar_layout.addWidget(self.btn_logout)

        main_layout.addWidget(sidebar)

        # ── Content area ──
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, stretch=1)

        # Create pages
        self.solutions_page = SolutionsPage(self.client)
        self.projects_page = ProjectsPage(self.client)
        self.processes_page = ProcessesPage(self.client, self.iface)
        self.about_page = AboutPage()

        self.stacked_widget.addWidget(self.solutions_page)
        self.stacked_widget.addWidget(self.projects_page)
        self.stacked_widget.addWidget(self.processes_page)
        self.stacked_widget.addWidget(self.about_page)

        # Connect sidebar buttons
        self.btn_solutions.clicked.connect(self.show_solutions)
        self.btn_projects.clicked.connect(self.show_projects)
        self.btn_feedback.clicked.connect(self.show_feedback)
        self.btn_about.clicked.connect(self.show_about)
        self.btn_logout.clicked.connect(self.do_logout)

        # Connect page navigation signals
        self.projects_page.project_opened.connect(self.show_processes)
        self.solutions_page.project_created.connect(lambda _: self.show_projects())

        # Fetch profile
        self._profile_thread = None
        if self.client:
            self._fetch_profile()

    def _make_nav_btn(self, text, layout):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(NAV_BTN_STYLE.format(
            bg=NORMAL_BG, fg="#2c3e50", hover=NORMAL_HOVER
        ))
        layout.addWidget(btn)
        self._nav_buttons.append(btn)
        return btn

    def _set_active_btn(self, active_btn):
        for btn in self._nav_buttons:
            if btn is active_btn:
                btn.setStyleSheet(NAV_BTN_STYLE.format(
                    bg=ACTIVE_BG, fg="white", hover=ACTIVE_HOVER
                ))
            else:
                btn.setStyleSheet(NAV_BTN_STYLE.format(
                    bg=NORMAL_BG, fg="#2c3e50", hover=NORMAL_HOVER
                ))

    def show_solutions(self):
        self.solutions_page.load_solutions()
        self.stacked_widget.setCurrentWidget(self.solutions_page)
        self._set_active_btn(self.btn_solutions)

    def show_projects(self):
        self.projects_page.load_projects()
        self.stacked_widget.setCurrentWidget(self.projects_page)
        self._set_active_btn(self.btn_projects)

    def show_processes(self, project):
        self.processes_page.load_processes(project)
        self.stacked_widget.setCurrentWidget(self.processes_page)
        self._set_active_btn(self.btn_projects)

    def show_feedback(self):
        """Open feedback dialog as a popup."""
        # Detect current page
        current_widget = self.stacked_widget.currentWidget()
        page_name = "unknown"
        if current_widget == self.solutions_page:
            page_name = "solutions"
        elif current_widget == self.projects_page:
            page_name = "projects"
        elif current_widget == self.processes_page:
            page_name = "processes"
        elif current_widget == self.about_page:
            page_name = "about"

        dialog = FeedbackDialog(self.client, current_page=page_name, parent=self)
        dialog.exec_()

    def show_about(self):
        self.stacked_widget.setCurrentWidget(self.about_page)
        self._set_active_btn(self.btn_about)

    def do_logout(self):
        from qgis.PyQt.QtCore import QSettings
        import keyring
        
        # Logout from API and invalidate server-side session
        if self.client:
            self.client.logout()
        # Clear saved credentials
        settings = QSettings()
        email = settings.value("rasid_plugin/email", "")
        if email:
            try:
                keyring.delete_password("rasid_plugin", email)
            except:
                pass
        settings.remove("rasid_plugin/email")
        self.reject()

    def _fetch_profile(self):
        self._profile_thread = FetchProfileThread(self.client)
        self._profile_thread.finished.connect(self._on_profile_loaded)
        self._profile_thread.error.connect(lambda msg: print(f"[RASID] Profile fetch failed: {msg}"))
        self._profile_thread.start()

    def _on_profile_loaded(self, data):
        profile = data.get("profile", {})
        first = profile.get("first_name", "")
        last = profile.get("last_name", "")
        name = f"{first} {last}".strip() or profile.get("email", "User")
        self._welcome_label.setText(f'<a href="https://app.rasid.ai/profile" style="color: #2c3e50; font-weight: bold; text-decoration: underline;">Welcome, {name}</a>')

        balance = data.get("balance", {})
        amount = balance.get("amount", 0)
        self._balance_label.setText(f'<a href="https://app.rasid.ai/payment/refill" style="color: #00856F; font-weight: bold; text-decoration: underline;">Credits: €{amount}</a>')
