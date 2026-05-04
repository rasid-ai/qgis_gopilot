from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame
from qgis.PyQt.QtCore import Qt


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # FIX
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)

        # Single white card
        content_card = QFrame()
        content_card.setObjectName("contentCard")  # FIX (better styling in QGIS)
        content_card.setStyleSheet("""
            QFrame#contentCard {
                background: white;
                border: 1px solid #dce0e3;
                border-radius: 8px;
            }
        """)
        content_card.setMaximumWidth(16777215)

        card_layout = QVBoxLayout(content_card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)

        # Title
        title = QLabel("About RASID")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #2c3e50;")
        card_layout.addWidget(title)

        subtitle = QLabel("AI-Powered Earth Observation Platform")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 15px; color: #00856F; font-weight: bold; margin-bottom: 16px;")
        card_layout.addWidget(subtitle)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #dce0e3; border: none;")
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
        desc1.setStyleSheet("font-size: 14px; color: #2c3e50;")
        card_layout.addWidget(desc1)

        desc2 = QLabel(
            "RASID goes beyond a one-size-fits-all model, offering customized geospatial "
            "analysis projects that align with the unique requirements of your industry. "
            "Our team is prepared to act on innovative solutions."
        )
        desc2.setWordWrap(True)
        desc2.setStyleSheet("font-size: 14px; color: #2c3e50;")
        card_layout.addWidget(desc2)

        desc3 = QLabel(
            "Our expertise is designed to provide actionable insights that can be directly "
            "applied to the most pressing challenges in your sector."
        )
        desc3.setWordWrap(True)
        desc3.setStyleSheet("font-size: 14px; color: #2c3e50;")
        card_layout.addWidget(desc3)

        card_layout.addSpacing(12)

        # Website link
        link = QLabel(
            'Learn more at <a href="https://rasid.ai" style="color: #00856F; font-weight: bold; text-decoration: none;">rasid.ai</a>'
        )
        link.setAlignment(Qt.AlignCenter)
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextBrowserInteraction)  # FIX
        link.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        card_layout.addWidget(link)

        card_layout.addSpacing(16)

        # Footer separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background: #dce0e3; border: none;")
        sep2.setFixedHeight(1)
        card_layout.addWidget(sep2)

        card_layout.addSpacing(16)

        # Version
        version = QLabel("RASID SaaS 2.0.0")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50;")
        card_layout.addWidget(version)

        # Terms link
        tos = QLabel(
            '<a href="https://app.rasid.ai/terms" style="color: #00856F; text-decoration: none;">Terms of Service</a>'
        )
        tos.setAlignment(Qt.AlignCenter)
        tos.setOpenExternalLinks(True)
        tos.setTextInteractionFlags(Qt.TextBrowserInteraction)  # FIX
        tos.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        card_layout.addWidget(tos)

        # Copyright
        copy_lbl = QLabel("\u00a9 2026 RASID SaaS. All rights reserved.")
        copy_lbl.setAlignment(Qt.AlignCenter)
        copy_lbl.setStyleSheet("font-size: 11px; color: #7f8c8d;")
        card_layout.addWidget(copy_lbl)

        layout.addWidget(content_card)
        layout.addStretch()