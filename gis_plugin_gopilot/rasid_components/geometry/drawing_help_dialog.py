# -*- coding: utf-8 -*-
"""
Drawing Help Dialog

Shows instructions to users on how to use the drawing tool.
Supports "Don't show again" preference.
"""

from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
from qgis.PyQt.QtCore import Qt, QSettings, QPoint
from qgis.PyQt.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QPolygon
from ..compat import (
    Qt_AlignCenter, Qt_PointingHandCursor,
    Qt_transparent, QPainter_Antialiasing, QDialog_Accepted, exec_dialog,
)
from .. import theme_utils


def create_drawing_icon(size=64):
    """Create a drawing/pencil icon"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt_transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter_Antialiasing)

    # Draw a simple polygon shape with a cursor
    painter.setPen(QColor(theme_utils.BRAND_PRIMARY))
    painter.setBrush(QColor(theme_utils.BRAND_PRIMARY + "40"))  # Semi-transparent

    # Draw polygon points
    points = [
        (size * 0.3, size * 0.5),
        (size * 0.5, size * 0.2),
        (size * 0.7, size * 0.4),
        (size * 0.6, size * 0.7),
    ]

    polygon = QPolygon([QPoint(int(x), int(y)) for x, y in points])
    painter.drawPolygon(polygon)

    # Draw cursor/click indicator
    painter.setPen(QColor("#e74c3c"))
    painter.setBrush(QColor("#e74c3c"))
    painter.drawEllipse(int(size * 0.3 - 4), int(size * 0.5 - 4), 8, 8)

    painter.end()
    return QIcon(pixmap)


class DrawingHelpDialog(QDialog):
    """Dialog showing instructions for using the drawing tool."""

    SETTINGS_KEY = "qgis_gopilot/show_drawing_help"

    def __init__(self, parent=None, title="How to Draw", context="general"):
        """Initialize the help dialog.

        Args:
            parent: Parent widget
            title: Dialog title
            context: Context for customized instructions ('gopilot', 'wizard', 'general')
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setMinimumHeight(300)
        self.dont_show_again = False

        # Build UI
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Icon and title
        header_layout = QHBoxLayout()

        icon_label = QLabel()
        icon_label.setPixmap(create_drawing_icon(64).pixmap(64, 64))
        header_layout.addWidget(icon_label)

        title_label = QLabel("Drawing on the Map")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color:{theme_utils.get_text_color()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Instructions
        instructions = self._get_instructions(context)

        for instruction in instructions:
            if instruction.startswith("---"):
                # Separator
                separator = QLabel()
                separator.setFixedHeight(1)
                separator.setStyleSheet(f"background:{theme_utils.get_card_border()};")
                layout.addWidget(separator)
            else:
                # Instruction line
                instr_label = QLabel(instruction)
                instr_label.setWordWrap(True)
                instr_label.setStyleSheet(f"""
                    color:{theme_utils.get_text_color()};
                    font-size:13px;
                    padding:4px 0;
                """)
                layout.addWidget(instr_label)

        layout.addSpacing(8)

        # Tips section
        tips_label = QLabel("💡 <b>Tips:</b>")
        tips_label.setStyleSheet(f"""
            color:{theme_utils.get_text_color()};
            font-size:12px;
            padding:4px 0;
        """)
        layout.addWidget(tips_label)

        tips = [
            "• You need at least 3 points to create a polygon",
            "• The dialog will automatically minimize to show the map",
            "• Click accurately - each click adds a point to your polygon",
        ]

        for tip in tips:
            tip_label = QLabel(tip)
            tip_label.setStyleSheet(f"""
                color:{theme_utils.get_secondary_text_color()};
                font-size:11px;
                padding:2px 0 2px 16px;
            """)
            layout.addWidget(tip_label)

        layout.addStretch()

        # Don't show again checkbox
        self.checkbox = QCheckBox("Don't show this again")
        self.checkbox.setStyleSheet(f"""
            QCheckBox {{
                color:{theme_utils.get_text_color()};
                font-size:12px;
            }}
        """)
        layout.addWidget(self.checkbox)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt_PointingHandCursor)
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background:{theme_utils.get_card_bg()};
                color:{theme_utils.get_text_color()};
                border:1px solid {theme_utils.get_card_border()};
                border-radius:6px;
                padding:8px 16px;
                font-size:13px;
            }}
            QPushButton:hover {{
                background:{theme_utils.get_hover_bg()};
                border-color:{theme_utils.BRAND_PRIMARY};
            }}
        """)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("Got it, let's draw!")
        self.ok_btn.setCursor(Qt_PointingHandCursor)
        self.ok_btn.setFixedWidth(150)
        self.ok_btn.setDefault(True)
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background:{theme_utils.BRAND_PRIMARY};
                color:white;
                border:none;
                border-radius:6px;
                padding:8px 16px;
                font-size:13px;
                font-weight:bold;
            }}
            QPushButton:hover {{
                background:{theme_utils.BRAND_HOVER};
            }}
        """)
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)

        layout.addLayout(button_layout)

        # Style the dialog
        self.setStyleSheet(f"""
            QDialog {{
                background:{theme_utils.get_card_bg()};
            }}
        """)

    def _get_instructions(self, context):
        """Get context-specific instructions.

        Args:
            context: 'gopilot', 'wizard', or 'general'

        Returns:
            List of instruction strings
        """
        base_instructions = [
            "<b>How to draw a polygon on the map:</b>",
            "",
            "🖱️ <b>Left-click</b> on the map to add points to your polygon",
            "",
            "🖱️ <b>Right-click</b> to finish drawing and close the polygon",
            "",
        ]

        if context == "gopilot":
            base_instructions.append("Your drawn geometry will be attached to your message and sent to the AI.")
        elif context == "wizard":
            base_instructions.append("Your drawn polygon will be used as the Area of Interest (AOI) for processing.")
        else:
            base_instructions.append("Your drawn polygon will be used as the geometry input.")

        return base_instructions

    def accept(self):
        """Handle OK button click."""
        if self.checkbox.isChecked():
            self.dont_show_again = True
            self._save_preference(False)
        super().accept()

    def _save_preference(self, show_again):
        """Save user preference to not show dialog again.

        Args:
            show_again: Whether to show the dialog in the future
        """
        settings = QSettings()
        settings.setValue(self.SETTINGS_KEY, show_again)

    @classmethod
    def should_show(cls):
        """Check if dialog should be shown based on user preference.

        Returns:
            bool: True if dialog should be shown
        """
        settings = QSettings()
        # Default to True (show help) if not set
        return settings.value(cls.SETTINGS_KEY, True, type=bool)

    @classmethod
    def reset_preference(cls):
        """Reset the preference to show the dialog again."""
        settings = QSettings()
        settings.setValue(cls.SETTINGS_KEY, True)

    @classmethod
    def show_help(cls, parent=None, title="How to Draw", context="general"):
        """Show the help dialog if user hasn't disabled it.

        Args:
            parent: Parent widget
            title: Dialog title
            context: Context for instructions ('gopilot', 'wizard', 'general')

        Returns:
            bool: True if user clicked OK to continue, False if cancelled
        """
        if not cls.should_show():
            return True  # Don't show, but continue

        dialog = cls(parent, title, context)
        result = exec_dialog(dialog)
        return result == QDialog_Accepted
