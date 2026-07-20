"""
Theme-aware color utilities

PROBLEM
=======
If a user uses dark theme option in QGIS -> since the plugin was using hardcoded colors 
(white backgrounds, dark text) became invisible in dark mode. 

SOLUTION
========
This module detects the active QGIS theme at runtime and provides theme-aware colors:
- Automatically adapts text colors: light text for dark themes, dark text for light themes
- Adjusts backgrounds: dark backgrounds for dark themes, light backgrounds for light themes
- Maintains brand colors (green, red) consistently across themes
- Ensures proper contrast ratios for readability

HOW IT WORKS
============
1. is_dark_theme() checks the palette background luminance (< 128 = dark)
2. get_*_color() functions return appropriate colors based on current theme
3. All UI components import from this module instead of hardcoding colors
4. Colors automatically update if user switches themes (requires plugin restart)

USAGE
=====
In your UI code:
    from . import theme_utils

    text_color = theme_utils.get_text_color()
    label.setStyleSheet(f"color: {text_color};")

    card_bg = theme_utils.get_card_bg()
    frame.setStyleSheet(f"background: {card_bg};")

PyQt5/PyQt6 COMPATIBILITY
=========================
The color detection uses QPalette.ColorRole which differs between PyQt5 and PyQt6.
We try PyQt6 style first (ColorRole.Window), with fallback to PyQt5 (Window).
"""

from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtGui import QPalette


def is_dark_theme():
    """
    Detect if QGIS is using a dark theme.

    Checks the background color's luminance. If luminance < 128 (on 0-255 scale),
    the theme is considered dark. This threshold provides reliable detection
    across different dark theme implementations.

    Returns:
        bool: True if dark theme is active, False otherwise
    """
    palette = QApplication.palette()
    # Scoped enum (QPalette.ColorRole.Window) works on both PyQt5 5.15+ and PyQt6.
    bg_color = palette.color(QPalette.ColorRole.Window)
    # Check if background is dark (luminance < 128)
    luminance = (0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue())
    return luminance < 128


def get_text_color():
    """
    Get appropriate primary text color based on theme.

    Returns:
        str: Light gray (#e0e0e0) for dark theme, dark gray (#2c3e50) for light theme
    """
    return "#e0e0e0" if is_dark_theme() else "#2c3e50"


def get_secondary_text_color():
    """
    Get secondary/muted text color based on theme.
    Used for labels, descriptions, and less important text.

    Returns:
        str: Medium gray (#b0b0b0) for dark theme, darker gray (#666666) for light theme
    """
    return "#b0b0b0" if is_dark_theme() else "#666666"


def get_sidebar_bg():
    """
    Get sidebar and header background color based on theme.
    Used for navigation panels and section headers.

    Returns:
        str: Dark gray (#2b2b2b) for dark theme, light gray (#f7f8fa) for light theme
    """
    return "#2b2b2b" if is_dark_theme() else "#f7f8fa"


def get_sidebar_border():
    """
    Get sidebar border color based on theme.

    Returns:
        str: Medium dark gray (#444444) for dark theme, light gray (#ddd) for light theme
    """
    return "#444444" if is_dark_theme() else "#ddd"


def get_hover_bg():
    """
    Get button/item hover background color based on theme.
    Used for interactive elements on hover state.

    Returns:
        str: Slightly lighter dark (#3a3a3a) for dark theme, light green (#e8f5f3) for light theme
    """
    return "#3a3a3a" if is_dark_theme() else "#e8f5f3"


def get_separator_color():
    """
    Get separator/divider line color based on theme.
    Used for horizontal rules and borders between sections.

    Returns:
        str: Medium dark gray (#444444) for dark theme, light gray (#ddd) for light theme
    """
    return "#444444" if is_dark_theme() else "#ddd"


def get_card_bg():
    """
    Get card/panel background color based on theme.
    Used for content cards, dialogs, and main content areas.

    Returns:
        str: Dark gray (#333333) for dark theme, white (#ffffff) for light theme
    """
    return "#333333" if is_dark_theme() else "#ffffff"


def get_card_border():
    """
    Get card/input border color based on theme.
    Used for outlining cards, input fields, and containers.

    Returns:
        str: Medium gray (#444444) for dark theme, light gray (#e0e0e0) for light theme
    """
    return "#444444" if is_dark_theme() else "#e0e0e0"


# Brand colors (remain constant across themes for consistency)
# These colors are part of the Rasid brand identity and should not change
BRAND_PRIMARY = "#00856F"  # Rasid teal/green - primary action color
BRAND_HOVER = "#009980"    # Lighter teal - hover state for primary buttons
BRAND_DANGER = "#e74c3c"   # Red - destructive actions (delete, cancel)


# Theme-aware brand color variations
BRAND_DANGER_HOVER = "#fdeaea"  # Light red tint - for light theme hover
BRAND_DANGER_HOVER_DARK = "#3d1f1f"  # Dark red tint - for dark theme hover


def get_danger_hover_bg():
    """
    Get danger button hover background color based on theme.
    Used for delete/cancel button hover states.

    Returns:
        str: Dark red (#3d1f1f) for dark theme, light red (#fdeaea) for light theme
    """
    return BRAND_DANGER_HOVER_DARK if is_dark_theme() else BRAND_DANGER_HOVER
