# -*- coding: utf-8 -*-
"""
Dependency installer for external Python packages.
Handles checking and installing required libraries like keyring.
"""

import sys
import subprocess
import importlib.util
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont
from .compat import Qt_RichText, Qt_PointingHandCursor, exec_dialog, QDialog_Accepted
from . import theme_utils


class InstallWorker(QThread):
    """Worker thread for installing packages without blocking UI."""

    finished = pyqtSignal(bool, str)  # success, message
    progress = pyqtSignal(str)  # progress text

    def __init__(self, packages):
        super().__init__()
        self.packages = packages

    def run(self):
        """Install packages using pip."""
        try:
            # Get Python executable - QGIS specific handling
            import os

            # sys.executable points to QGIS, not Python
            # We need to find the actual Python executable
            qgis_path = sys.executable

            # On Windows, QGIS Python is typically in the same directory or in bin/
            if os.name == 'nt':  # Windows
                qgis_dir = os.path.dirname(qgis_path)
                # Try python3.exe first, then python.exe
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
                    # Fallback: try to use python3 from PATH
                    python_exe = "python3"
            else:  # Linux/Mac
                python_exe = "python3"

            # Build pip install command
            cmd = [python_exe, "-m", "pip", "install", "--user"] + self.packages

            self.progress.emit(f"Running: {' '.join(cmd)}\n")

            # Run installation (hide console window on Windows)
            startupinfo = None
            if os.name == 'nt':  # Windows
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo
            )

            # Stream output
            for line in process.stdout:
                self.progress.emit(line)

            process.wait()

            if process.returncode == 0:
                self.finished.emit(True, "Installation completed successfully!")
            else:
                self.finished.emit(False, f"Installation failed with return code {process.returncode}")

        except Exception as e:
            self.finished.emit(False, f"Installation error: {str(e)}")


class DependencyInstallerDialog(QDialog):
    """Dialog for installing required dependencies."""

    def __init__(self, packages, parent=None):
        super().__init__(parent)
        self.packages = packages
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
        packages_str = ', '.join(self.packages)
        desc = QLabel(
            f"The RASID plugin needs to install <b>{packages_str}</b> for secure credential storage.\n\n"
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
        self.worker = InstallWorker(self.packages)
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
                "Libraries installed successfully!\n\nThe plugin will now load."
            )
            self.accept()
        else:
            self.output_text.append(f"\n✗ {message}")
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"{message}\n\n"
                "Please try installing manually:\n"
                f"pip install {' '.join(self.packages)}"
            )
            self.install_button.setEnabled(True)


class DependencyManager:
    """Manages checking and installing dependencies."""

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

        try:
            # Try to actually import the module
            __import__(package_name)
            return True
        except (ImportError, ModuleNotFoundError, ValueError, Exception):
            return False

    @staticmethod
    def check_dependencies():
        """
        Check if all required dependencies are installed.

        Returns:
            tuple: (all_installed: bool, missing_packages: list)
        """
        required_packages = ["keyring"]
        missing = []

        for package in required_packages:
            if not DependencyManager.check_package(package):
                missing.append(package)

        return len(missing) == 0, missing

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
        all_installed, missing = DependencyManager.check_dependencies()

        if all_installed:
            return True

        # Show installation dialog
        dialog = DependencyInstallerDialog(missing, parent)
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
