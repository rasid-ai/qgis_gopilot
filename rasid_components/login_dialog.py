# login dialog UI
import os
import sys
import subprocess
from qgis.PyQt.QtWidgets import (
    QDialog, QLineEdit, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFrame, QMessageBox
)
from qgis.PyQt.QtGui import QPixmap, QDesktopServices
from qgis.PyQt.QtCore import QUrl
from .compat import (
    Qt_AlignCenter, Qt_KeepAspectRatio, Qt_SmoothTransformation, Qt_PointingHandCursor,
    QLineEdit_Password, QLineEdit_Normal, QMessageBox_Yes, QMessageBox_No
)
from . import theme_utils
from .config import API_HOST, APP_BASE_URL


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RASID Login")
        self.setMinimumWidth(750)
        self.setMinimumHeight(500)

        # Theme-aware background
        bg_color = theme_utils.get_card_bg()
        self.setStyleSheet(f"background: {bg_color};")

        # Main layout (two columns)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ═══════════════════════════════════════════════════════════════
        # LEFT COLUMN - Branding
        # ═══════════════════════════════════════════════════════════════
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background: #1E293B;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(40, 60, 40, 60)
        left_layout.setSpacing(20)
        left_layout.setAlignment(Qt_AlignCenter)

        # Logo
        logo_label = QLabel()
        logo_label.setAlignment(Qt_AlignCenter)
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icon_nobg.png')
        if os.path.exists(logo_path):
            pm = QPixmap(logo_path)
            logo_label.setPixmap(pm.scaled(120, 120, Qt_KeepAspectRatio, Qt_SmoothTransformation))
        else:
            logo_label.setText("RASID")
            logo_label.setStyleSheet("font-size: 32px; font-weight: bold; color: white; background: transparent;")
        left_layout.addWidget(logo_label)

        # Welcome message
        welcome_title = QLabel("Welcome Back")
        welcome_title.setAlignment(Qt_AlignCenter)
        welcome_title.setStyleSheet("font-size: 28px; font-weight: bold; color: white; background: transparent;")
        left_layout.addWidget(welcome_title)

        welcome_subtitle = QLabel("Access your geospatial solutions\nand manage your projects")
        welcome_subtitle.setAlignment(Qt_AlignCenter)
        welcome_subtitle.setWordWrap(True)
        welcome_subtitle.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.9); background: transparent; line-height: 1.6;")
        left_layout.addWidget(welcome_subtitle)

        left_layout.addStretch()

        main_layout.addWidget(left_panel, stretch=2)

        # ═══════════════════════════════════════════════════════════════
        # RIGHT COLUMN - Login Form
        # ═══════════════════════════════════════════════════════════════
        right_panel = QFrame()
        panel_bg = theme_utils.get_card_bg()
        right_panel.setStyleSheet(f"background: {panel_bg};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(50, 60, 50, 60)
        right_layout.setSpacing(0)

        # Form title
        form_title = QLabel("Connect to RASID")
        text_color = theme_utils.get_text_color()
        form_title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {text_color}; margin-bottom: 10px;")
        right_layout.addWidget(form_title)

        form_subtitle = QLabel("Enter your API key to continue")
        secondary_color = theme_utils.get_secondary_text_color()
        form_subtitle.setStyleSheet(f"font-size: 13px; color: {secondary_color}; margin-bottom: 30px;")
        right_layout.addWidget(form_subtitle)

        right_layout.addSpacing(20)

        # API Key field
        self.api_key_label = QLabel("API Key")
        text_color = theme_utils.get_text_color()
        self.api_key_label.setStyleSheet(f"font-weight: bold; color: {text_color}; font-size: 12px; margin-bottom: 6px;")
        right_layout.addWidget(self.api_key_label)

        # API Key row with input + eye button
        api_key_row = QHBoxLayout()
        api_key_row.setSpacing(8)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit_Password)
        self.api_key_input.setPlaceholderText("rsd_...")
        input_bg = theme_utils.get_card_bg()
        border_color = theme_utils.get_card_border()
        self.api_key_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 12px 14px;
                border: 2px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                background: {input_bg};
                color: {text_color};
            }}
            QLineEdit:focus {{
                border: 2px solid {theme_utils.BRAND_PRIMARY};
            }}
        """)
        api_key_row.addWidget(self.api_key_input)

        self._eye_btn = QPushButton("👁")
        self._eye_btn.setFixedSize(48, 48)
        self._eye_btn.setCursor(Qt_PointingHandCursor)
        eye_bg = theme_utils.get_sidebar_bg()
        eye_hover = theme_utils.get_hover_bg()
        self._eye_btn.setStyleSheet(f"""
            QPushButton {{
                background: {eye_bg};
                color: {text_color};
                border: 2px solid {border_color};
                border-radius: 6px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background: {eye_hover};
            }}
        """)
        self._eye_btn.setToolTip("Show API key")
        self._eye_btn.clicked.connect(self._toggle_api_key_visibility)
        api_key_row.addWidget(self._eye_btn)

        right_layout.addLayout(api_key_row)

        right_layout.addSpacing(16)

        # Get API Key button
        self.get_key_btn = QPushButton("Get API Key")
        self.get_key_btn.setCursor(Qt_PointingHandCursor)
        button_bg = theme_utils.get_sidebar_bg()
        button_hover = theme_utils.get_hover_bg()
        self.get_key_btn.setStyleSheet(f"""
            QPushButton {{
                background: {button_bg};
                color: {text_color};
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 12px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {button_hover};
            }}
        """)
        self.get_key_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"{APP_BASE_URL}/api-keys"))
        )
        right_layout.addWidget(self.get_key_btn)

        right_layout.addSpacing(24)

        # Connect button
        self.login_button = QPushButton("Connect")
        self.login_button.setCursor(Qt_PointingHandCursor)
        self.login_button.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.BRAND_PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 14px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {theme_utils.BRAND_HOVER};
            }}
            QPushButton:pressed {{
                background: #006b5a;
            }}
        """)
        self.login_button.clicked.connect(self.accept)
        right_layout.addWidget(self.login_button)

        right_layout.addSpacing(20)

        # Sign up link
        secondary_color = theme_utils.get_secondary_text_color()
        signup_label = QLabel(
            'Don\'t have an account? '
            f'<a href="{APP_BASE_URL}/auth?active_form=register" style="color: {theme_utils.BRAND_PRIMARY}; font-weight: bold; text-decoration: none;">Sign up</a>'
        )
        signup_label.setOpenExternalLinks(True)
        signup_label.setAlignment(Qt_AlignCenter)
        signup_label.setStyleSheet(f"color: {secondary_color}; font-size: 12px;")
        right_layout.addWidget(signup_label)

        # TESTING: Uninstall keyring button (comment/uncomment for testing)
        # self._add_uninstall_button(right_layout)

        right_layout.addStretch()

        main_layout.addWidget(right_panel, stretch=3)

    def _add_uninstall_button(self, layout):
        """Add uninstall button for testing purposes."""
        layout.addSpacing(30)
        uninstall_btn = QPushButton("🗑 Uninstall Keyring (Testing)")
        uninstall_btn.setCursor(Qt_PointingHandCursor)
        uninstall_btn.setStyleSheet("""
            QPushButton {
                background: #7f1d1d;
                color: white;
                border: 2px solid #991b1b;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #991b1b;
            }
        """)
        uninstall_btn.clicked.connect(self._uninstall_keyring)
        layout.addWidget(uninstall_btn)

    def _toggle_api_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit_Password:
            self.api_key_input.setEchoMode(QLineEdit_Normal)
            self._eye_btn.setText("🙈")
            self._eye_btn.setToolTip("Hide API key")
        else:
            self.api_key_input.setEchoMode(QLineEdit_Password)
            self._eye_btn.setText("👁")
            self._eye_btn.setToolTip("Show API key")

    def _uninstall_keyring(self):
        """Uninstall keyring package for testing purposes."""
        reply = QMessageBox.question(
            self,
            "Uninstall Keyring",
            "This will uninstall the keyring package.\nAre you sure?",
            QMessageBox_Yes | QMessageBox_No
        )

        if reply != QMessageBox_Yes:
            return

        try:
            # Find Python executable (same logic as installer)
            qgis_path = sys.executable

            if os.name == 'nt':  # Windows
                qgis_dir = os.path.dirname(qgis_path)
                python_candidates = [
                    os.path.join(qgis_dir, "python3.exe"),
                    os.path.join(qgis_dir, "python.exe"),
                    os.path.join(qgis_dir, "..", "bin", "python3.exe"),
                    os.path.join(qgis_dir, "..", "bin", "python.exe"),
                ]
                python_exe = None
                for candidate in python_candidates:
                    if os.path.exists(candidate):
                        python_exe = candidate
                        break
                if not python_exe:
                    python_exe = "python3"
            else:  # Linux/Mac
                python_exe = "python3"

            # Build uninstall command
            cmd = [python_exe, "-m", "pip", "uninstall", "keyring", "-y"]

            # Run uninstall (hide console window on Windows)
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo
            )

            if result.returncode == 0:
                QMessageBox.information(
                    self,
                    "Success",
                    "Keyring uninstalled successfully!\n\nRestart QGIS to test the install dialog."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Uninstall Failed",
                    f"Failed to uninstall keyring:\n{result.stderr}"
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error uninstalling keyring:\n{str(e)}"
            )
