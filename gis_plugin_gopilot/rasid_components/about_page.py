from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame
from .compat import Qt_ScrollBarAlwaysOff, Qt_AlignTop, Qt_AlignCenter, Qt_TextBrowserInteraction, QFrame_NoFrame, QFrame_HLine
from . import theme_utils
from .config import APP_BASE_URL


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame_NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt_ScrollBarAlwaysOff)  # FIX
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt_AlignTop)
        scroll.setWidget(inner)

        # Single white card
        content_card = QFrame()
        content_card.setObjectName("contentCard")  # FIX (better styling in QGIS)
        card_bg = theme_utils.get_card_bg()
        card_border = theme_utils.get_card_border()
        content_card.setStyleSheet(f"""
            QFrame#contentCard {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 8px;
            }}
        """)
        content_card.setMaximumWidth(16777215)

        card_layout = QVBoxLayout(content_card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)

        # Title
        title = QLabel("About RASID")
        title.setAlignment(Qt_AlignCenter)
        text_color = theme_utils.get_text_color()
        title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {text_color};")
        card_layout.addWidget(title)

        subtitle = QLabel("AI-Powered Earth Observation Platform")
        subtitle.setAlignment(Qt_AlignCenter)
        subtitle.setStyleSheet(f"font-size: 15px; color: {theme_utils.BRAND_PRIMARY}; font-weight: bold; margin-bottom: 16px;")
        card_layout.addWidget(subtitle)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame_HLine)
        sep_color = theme_utils.get_separator_color()
        sep.setStyleSheet(f"background: {sep_color}; border: none;")
        sep.setFixedHeight(1)
        card_layout.addWidget(sep)

        card_layout.addSpacing(12)

        # Description
        desc1 = QLabel(
            "RASID specializes in AI-driven analysis of satellite imagery to provide "
            "critical insights for better decision-making. Our team of experts combines "
            "deep knowledge in AI, geospatial data, and industry-specific solutions."
        )
        desc1.setWordWrap(True)
        desc1.setStyleSheet(f"font-size: 14px; color: {text_color};")
        card_layout.addWidget(desc1)

        desc2 = QLabel(
            "RASID goes beyond a one-size-fits-all model, offering customized geospatial "
            "analysis projects that align with the unique requirements of your industry. "
            "Our team is prepared to act on innovative solutions."
        )
        desc2.setWordWrap(True)
        desc2.setStyleSheet(f"font-size: 14px; color: {text_color};")
        card_layout.addWidget(desc2)

        desc3 = QLabel(
            "Our expertise is designed to provide actionable insights that can be directly "
            "applied to the most pressing challenges in your sector."
        )
        desc3.setWordWrap(True)
        desc3.setStyleSheet(f"font-size: 14px; color: {text_color};")
        card_layout.addWidget(desc3)

        card_layout.addSpacing(12)

        # Website link
        secondary_color = theme_utils.get_secondary_text_color()
        link = QLabel(
            f'Learn more at <a href="https://rasid.ai" style="color: {theme_utils.BRAND_PRIMARY}; font-weight: bold; text-decoration: none;">rasid.ai</a>'
        )
        link.setAlignment(Qt_AlignCenter)
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt_TextBrowserInteraction)  # FIX
        link.setStyleSheet(f"font-size: 14px; color: {secondary_color};")
        card_layout.addWidget(link)

        card_layout.addSpacing(16)

        # Footer separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame_HLine)
        sep2.setStyleSheet(f"background: {sep_color}; border: none;")
        sep2.setFixedHeight(1)
        card_layout.addWidget(sep2)

        card_layout.addSpacing(16)

        # Version
        version = QLabel("RASID SaaS 2.0.0")
        version.setAlignment(Qt_AlignCenter)
        version.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {text_color};")
        card_layout.addWidget(version)

        # Terms link
        tos = QLabel(
            f'<a href="{APP_BASE_URL}/terms" style="color: {theme_utils.BRAND_PRIMARY}; text-decoration: none;">Terms of Service</a>'
        )
        tos.setAlignment(Qt_AlignCenter)
        tos.setOpenExternalLinks(True)
        tos.setTextInteractionFlags(Qt_TextBrowserInteraction)  # FIX
        tos.setStyleSheet(f"font-size: 12px; color: {secondary_color};")
        card_layout.addWidget(tos)

        # Copyright
        copy_lbl = QLabel("\u00a9 2026 RASID SaaS. All rights reserved.")
        copy_lbl.setAlignment(Qt_AlignCenter)
        copy_lbl.setStyleSheet(f"font-size: 11px; color: {secondary_color};")
        card_layout.addWidget(copy_lbl)

        layout.addWidget(content_card)
        layout.addStretch()