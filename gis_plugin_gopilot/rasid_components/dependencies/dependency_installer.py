# -*- coding: utf-8 -*-
"""
Dependency installer for external Python packages.
Handles checking and installing required libraries in an isolated virtual environment.

Uses venv_manager for proper dependency isolation from QGIS Python environment.
"""

import sys
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont
from ..compat import Qt_RichText, Qt_PointingHandCursor, exec_dialog, QDialog_Accepted
from .. import theme_utils
from . import venv_manager


class DependencyInstallerDialog(QDialog):
    """Dialog for installing required dependencies in an isolated virtual environment."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI."""
        self.setWindowTitle("Install Required Libraries")
        self.setMinimumWidth(450)
        self.setMinimumHeight(200)

        # Theme-aware styling
        bg_color = theme_utils.get_card_bg()
        text_color = theme_utils.get_text_color()
        border_color = theme_utils.get_card_border()
        button_hover = theme_utils.get_hover_bg()

        self.setStyleSheet(f"background: {bg_color}; color: {text_color};")

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Required Libraries Missing")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {text_color};")
        layout.addWidget(title)

        # Description
        missing_packages = venv_manager.get_missing_packages()
        packages_display = ', '.join([pkg.split('>=')[0] for pkg in missing_packages])
        desc = QLabel(
            f"The QGIS GoPilot plugin needs to install <b>{packages_display}</b> "
            f"in an isolated virtual environment.\n\n"
            f"This keeps your QGIS Python environment clean and avoids conflicts.\n\n"
            f"Click Install to continue (requires internet connection)."
        )
        desc.setTextFormat(Qt_RichText)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {text_color};")
        layout.addWidget(desc)

        # Progress/output text area
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setVisible(False)
        output_bg = theme_utils.get_sidebar_bg()
        self.output_text.setStyleSheet(f"""
            QTextEdit {{
                background: {output_bg};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.output_text)

        # Add stretch to push buttons to bottom when output is hidden
        layout.addStretch()

        # Buttons
        self.install_button = QPushButton("Install")
        self.install_button.setCursor(Qt_PointingHandCursor)
        self.install_button.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.BRAND_PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {theme_utils.BRAND_HOVER};
            }}
            QPushButton:disabled {{
                background: #666;
                color: #999;
            }}
        """)
        self.install_button.clicked.connect(self.start_installation)
        layout.addWidget(self.install_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setCursor(Qt_PointingHandCursor)
        self.cancel_button.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.get_sidebar_bg()};
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
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)

    def start_installation(self):
        """Start the installation process."""
        self.install_button.setEnabled(False)
        self.output_text.setVisible(True)
        self.output_text.clear()
        self.setMinimumHeight(400)  # Expand dialog when showing output

        # Create and start worker thread
        self.worker = venv_manager.DepsInstallWorker(self)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.installation_finished)
        self.worker.start()

    def update_progress(self, text):
        """Update progress text."""
        self.output_text.append(text.rstrip())
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )

    def installation_finished(self, success, message):
        """Handle installation completion."""
        self.worker = None

        if success:
            self.output_text.append(f"\n✓ {message}")
            QMessageBox.information(
                self,
                "Success",
                "Libraries installed successfully in isolated virtual environment!\n\n"
                "The plugin will now load."
            )
            self.accept()
        else:
            self.output_text.append(f"\n✗ {message}")
            missing = venv_manager.get_missing_packages()
            manual_install = ' '.join(missing)
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"{message}\n\n"
                "Please try installing manually:\n"
                f"pip install {manual_install}"
            )
            self.install_button.setEnabled(True)


class DependencyManager:
    """Manages checking and installing dependencies using isolated virtual environment."""

    @staticmethod
    def check_package(package_name):
        """
        Check if a package is installed and importable.

        Args:
            package_name: Name of the package to check

        Returns:
            bool: True if package is available, False otherwise
        """
        # TESTING MODE: Uncomment the line below to force install dialog
        # return False

        # Ensure venv packages are on sys.path
        venv_manager.ensure_venv_packages_available()

        discoverable, _ = venv_manager._dependency_discoverable(package_name)
        return discoverable

    @staticmethod
    def get_required_packages():
        """
        Get required packages from venv_manager.

        Returns:
            list: List of required package names (import names, not pip specs)
        """
        return [import_name for import_name, _ in venv_manager.get_required_packages()]

    @staticmethod
    def check_dependencies():
        """
        Check if all required dependencies are installed.

        Returns:
            tuple: (all_installed: bool, missing_packages: list)
        """
        all_installed = venv_manager.all_dependencies_met()
        missing_specs = venv_manager.get_missing_packages()
        # Extract just the package names for backwards compatibility
        missing = [pkg.split('>=')[0].split('==')[0].split('<')[0].strip()
                   for pkg in missing_specs]

        return all_installed, missing

    @staticmethod
    def prompt_install(parent=None):
        """
        Check dependencies and prompt user to install if needed.

        Args:
            parent: Parent widget for dialog

        Returns:
            bool: True if all dependencies are available (either were already
                  installed or successfully installed now), False otherwise
        """
        # Check if Python version is supported
        if not venv_manager.python_runtime_supported():
            QMessageBox.critical(
                parent,
                "Python Version Not Supported",
                venv_manager.python_runtime_error()
            )
            return False

        all_installed, missing = DependencyManager.check_dependencies()

        if all_installed:
            return True

        # Show installation dialog
        dialog = DependencyInstallerDialog(parent)
        result = exec_dialog(dialog)

        if result == QDialog_Accepted:
            # Verify installation was successful
            all_installed, still_missing = DependencyManager.check_dependencies()
            if not all_installed:
                QMessageBox.warning(
                    parent,
                    "Installation Issue",
                    f"Some packages are still missing: {', '.join(still_missing)}\n\n"
                    "Please restart QGIS and try again."
                )
                return False
            return True

        return False
