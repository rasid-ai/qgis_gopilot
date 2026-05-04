# login dialog UI
import os
from qgis.PyQt.QtWidgets import (
    QDialog, QLineEdit, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFrame
)
from qgis.PyQt.QtGui import QPixmap
from .compat import (
    Qt_AlignCenter, Qt_KeepAspectRatio, Qt_SmoothTransformation, Qt_PointingHandCursor,
    QLineEdit_Password, QLineEdit_Normal
)


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RASID Login")
        self.setMinimumWidth(750)
        self.setMinimumHeight(500)
        self.setStyleSheet("background: white;")

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
        right_panel.setStyleSheet("background: white;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(50, 60, 50, 60)
        right_layout.setSpacing(0)

        # Form title
        form_title = QLabel("Sign In")
        form_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        right_layout.addWidget(form_title)

        form_subtitle = QLabel("Enter your credentials to continue")
        form_subtitle.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 30px;")
        right_layout.addWidget(form_subtitle)

        right_layout.addSpacing(20)

        # Email field
        self.email_label = QLabel("Email Address")
        self.email_label.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 12px; margin-bottom: 6px;")
        right_layout.addWidget(self.email_label)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email")
        self.email_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 2px solid #dce0e3;
                border-radius: 6px;
                font-size: 13px;
                background: white;
            }
            QLineEdit:focus {
                border: 2px solid #00856F;
            }
        """)
        right_layout.addWidget(self.email_input)

        right_layout.addSpacing(16)

        # Password field
        self.password_label = QLabel("Password")
        self.password_label.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 12px; margin-bottom: 6px;")
        right_layout.addWidget(self.password_label)

        # Password row with input + eye button
        pass_row = QHBoxLayout()
        pass_row.setSpacing(8)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit_Password)
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 14px;
                border: 2px solid #dce0e3;
                border-radius: 6px;
                font-size: 13px;
                background: white;
            }
            QLineEdit:focus {
                border: 2px solid #00856F;
            }
        """)
        pass_row.addWidget(self.password_input)

        self._eye_btn = QPushButton("👁")
        self._eye_btn.setFixedSize(48, 48)
        self._eye_btn.setCursor(Qt_PointingHandCursor)
        self._eye_btn.setStyleSheet("""
            QPushButton {
                background: #f7f8fa;
                color: black;
                border: 2px solid #dce0e3;
                border-radius: 6px;
                font-size: 18px;
            }
            QPushButton:hover {
                background: #dce6f0;
            }
        """)
        self._eye_btn.setToolTip("Show password")
        self._eye_btn.clicked.connect(self._toggle_password)
        pass_row.addWidget(self._eye_btn)

        right_layout.addLayout(pass_row)

        right_layout.addSpacing(24)

        # Login button
        self.login_button = QPushButton("Sign In")
        self.login_button.setCursor(Qt_PointingHandCursor)
        self.login_button.setStyleSheet("""
            QPushButton {
                background: #00856F;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 14px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #009980;
            }
            QPushButton:pressed {
                background: #006b5a;
            }
        """)
        self.login_button.clicked.connect(self.accept)
        right_layout.addWidget(self.login_button)

        right_layout.addSpacing(20)

        # Sign up link
        signup_label = QLabel(
            'Don\'t have an account? '
            '<a href="https://app.rasid.ai/auth?active_form=register" style="color: #00856F; font-weight: bold; text-decoration: none;">Sign up</a>'
        )
        signup_label.setOpenExternalLinks(True)
        signup_label.setAlignment(Qt_AlignCenter)
        signup_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        right_layout.addWidget(signup_label)

        right_layout.addStretch()

        main_layout.addWidget(right_panel, stretch=3)

        self.session_id = None
        self.token = None

    def _toggle_password(self):
        if self.password_input.echoMode() == QLineEdit_Password:
            self.password_input.setEchoMode(QLineEdit_Normal)
            self._eye_btn.setText("🙈")
            self._eye_btn.setToolTip("Hide password")
        else:
            self.password_input.setEchoMode(QLineEdit_Password)
            self._eye_btn.setText("👁")
            self._eye_btn.setToolTip("Show password")
