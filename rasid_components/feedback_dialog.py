from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QFrame, QMessageBox
)
from qgis.PyQt.QtCore import QThread, pyqtSignal
from .compat import (
    Qt_AlignCenter, Qt_AlignLeft, Qt_PointingHandCursor, Qt_RichText, Qt_TextBrowserInteraction,
    exec_dialog, QMessageBox_Information
)
from . import theme_utils
import platform


class SubmitFeedbackThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, feedback_data):
        super().__init__()
        self.client = client
        self.feedback_data = feedback_data

    def run(self):
        try:
            result = self.client.submit_feedback(self.feedback_data)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class FeedbackDialog(QDialog):
    """Modern feedback dialog matching web app design."""

    def __init__(self, client, current_page=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.current_page = current_page
        self._threads = []
        self._selected_rating = 0
        self._star_buttons = []

        self.setWindowTitle("Feedback")
        self.setMinimumWidth(450)
        self.setMinimumHeight(380)
        bg_color = theme_utils.get_card_bg()
        self.setStyleSheet(f"background: {bg_color};")

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header
        title = QLabel("Provide Feedback")
        title.setAlignment(Qt_AlignCenter)
        text_color = theme_utils.get_text_color()
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {text_color};")
        main_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("We value your input to improve the platform.")
        subtitle.setAlignment(Qt_AlignCenter)
        secondary_color = theme_utils.get_secondary_text_color()
        subtitle.setStyleSheet(f"font-size: 12px; color: {secondary_color}; margin-top: -4px;")
        main_layout.addWidget(subtitle)

        main_layout.addSpacing(8)

        # Star rating section
        rating_label = QLabel("How would you rate your experience?")
        rating_label.setStyleSheet(f"font-size: 13px; color: {text_color}; font-weight: 500;")
        main_layout.addWidget(rating_label)

        # Star buttons
        stars_layout = QHBoxLayout()
        stars_layout.setSpacing(6)
        stars_layout.setAlignment(Qt_AlignLeft)

        border_color = theme_utils.get_card_border()
        for i in range(1, 6):
            star_btn = QPushButton("☆")
            star_btn.setFixedSize(38, 38)
            star_btn.setCursor(Qt_PointingHandCursor)
            star_btn.setProperty("star_value", i)
            star_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 2px solid {border_color};
                    border-radius: 6px;
                    color: {secondary_color};
                    font-size: 24px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    border-color: #FFB800;
                    color: #FFB800;
                }}
            """)
            star_btn.clicked.connect(lambda checked, val=i: self._set_rating(val))
            stars_layout.addWidget(star_btn)
            self._star_buttons.append(star_btn)

        main_layout.addLayout(stars_layout)

        main_layout.addSpacing(8)

        # Message section
        message_label = QLabel("Your Message *")
        message_label.setStyleSheet(f"font-size: 13px; color: {text_color}; font-weight: 500;")
        main_layout.addWidget(message_label)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Tell us what you like or what we can improve...")
        self.message_input.setMinimumHeight(100)
        input_bg = theme_utils.get_card_bg()
        self.message_input.setStyleSheet(f"""
            QTextEdit {{
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
                color: {text_color};
                background: {input_bg};
            }}
            QTextEdit:focus {{
                border-color: {theme_utils.BRAND_PRIMARY};
            }}
        """)
        main_layout.addWidget(self.message_input)

        main_layout.addStretch()

        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt_PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {secondary_color};
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {text_color};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.submit_btn = QPushButton("Submit Feedback")
        self.submit_btn.setCursor(Qt_PointingHandCursor)
        self.submit_btn.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.BRAND_PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {theme_utils.BRAND_HOVER};
            }}
            QPushButton:disabled {{
                background: #bdc3c7;
            }}
        """)
        self.submit_btn.clicked.connect(self._submit_feedback)
        btn_layout.addWidget(self.submit_btn)

        main_layout.addLayout(btn_layout)

    def _set_rating(self, rating):
        """Update star selection."""
        self._selected_rating = rating
        border_color = theme_utils.get_card_border()
        secondary_color = theme_utils.get_secondary_text_color()
        for i, btn in enumerate(self._star_buttons, start=1):
            if i <= rating:
                # Filled star
                btn.setText("★")
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: 2px solid #FFB800;
                        border-radius: 6px;
                        color: #FFB800;
                        font-size: 24px;
                        padding: 0;
                    }
                    QPushButton:hover {
                        border-color: #FFB800;
                        color: #FFB800;
                    }
                """)
            else:
                # Empty star
                btn.setText("☆")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        border: 2px solid {border_color};
                        border-radius: 6px;
                        color: {secondary_color};
                        font-size: 24px;
                        padding: 0;
                    }}
                    QPushButton:hover {{
                        border-color: #FFB800;
                        color: #FFB800;
                    }}
                """)

    def _submit_feedback(self):
        """Submit feedback to API."""
        message = self.message_input.toPlainText().strip()
        if not message:
            QMessageBox.warning(
                self, "Missing Message",
                "Please enter your feedback message."
            )
            return

        # Build feedback data
        feedback_data = {
            "message": message,
            "rating": self._selected_rating,
            "feedback_infos": {
                "plugin_version": "2.0.0",
                "platform": platform.system(),
                "platform_version": platform.version(),
                "current_page": self.current_page or "unknown"
            }
        }

        # Disable during submission
        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("Submitting...")

        # Submit in background
        thread = SubmitFeedbackThread(self.client, feedback_data)
        thread.finished.connect(self._on_submit_success)
        thread.error.connect(self._on_submit_error)
        self._threads.append(thread)
        thread.start()

    def _on_submit_success(self, result):
        """Handle successful submission."""
        self.submit_btn.setEnabled(True)
        self.submit_btn.setText("Submit Feedback")

        # Create message box with clickable link
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Thank You!")
        msg_box.setIcon(QMessageBox_Information)
        msg_box.setText(
            "Your feedback has been submitted successfully.<br><br>"
            "We appreciate you taking the time to help us improve!<br><br>"
            "To view and manage all your feedbacks, visit:<br>"
            '<a href="https://app.rasid.ai/feedback">https://app.rasid.ai/feedback</a>'
        )
        msg_box.setTextFormat(Qt_RichText)
        msg_box.setTextInteractionFlags(Qt_TextBrowserInteraction)
        exec_dialog(msg_box)

        self.accept()  # Close dialog

    def _on_submit_error(self, error_msg):
        """Handle submission error."""
        self.submit_btn.setEnabled(True)
        self.submit_btn.setText("Submit Feedback")

        QMessageBox.critical(
            self, "Submission Failed",
            f"Failed to submit feedback:\n\n{error_msg}\n\n"
            f"Please try again."
        )
