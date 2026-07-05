# -*- coding: utf-8 -*-
"""
GoPilot AI Chat Page

Architecture
------------
Widget-per-message (like the QScrollArea version), but each message body is a
word-wrapped QLabel instead of a QTextBrowser.

Why this is the right call for a distributable QGIS plugin:

  * QLabel is *built* to size-to-content. Give it a max width and word wrap,
    and it computes its own height via heightForWidth(). That deletes the
    entire `_MessageBody` height-chasing apparatus from the QTextBrowser
    version (documentSizeChanged, DOC_MARGIN, SLACK, scrollbar suppression,
    wheelEvent overrides) — none of it is needed here.

  * Because each bubble reports an honest sizeHint, the layout settles on its
    own. So the takeWidget()/setWidget() + processEvents() "refresh hack" is
    gone too. Scrolling to bottom is a single deferred call.

  * It does NOT depend on QWebEngineView. That widget would give nicer CSS
    (true rounded corners, max-width), but it is frequently absent from QGIS
    installs (notably Windows OSGeo4W), so importing it crashes those users.
    QLabel rich text renders everywhere QGIS runs.

  * All messages are rendered as Markdown using the markdown library, which is
    required and bundled with the plugin.

Streaming is fully wired: begin_ai_stream() -> update_ai_stream(full_text) ->
finish_ai_stream(). The current SendMessageThread uses the simple
"replace the thinking bubble" path; the streaming hooks are ready if/when your
transport can emit partial chunks.
"""

import re
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
    QLabel, QFrame, QListWidget, QSplitter, QListWidgetItem, QMessageBox,
    QSizePolicy,
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QDateTime, QTimer, QUrl
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkRequest

from .compat import (
    Qt_AlignTop, Qt_AlignRight, Qt_AlignLeft, Qt_AlignCenter, Qt_UserRole,
    Qt_PointingHandCursor, Qt_Horizontal, QFrame_NoFrame, QFrame_StyledPanel,
    Qt_transparent, QPainter_Antialiasing, Qt_SmoothTransformation,
    QMessageBox_Question, QMessageBox_Yes, QMessageBox_No, exec_dialog,
    QSizePolicy_Expanding,
)
from . import theme_utils
from .geometry import GeometryInputManager
import markdown
import json
from .logger import debug_print

# ── Layer download and loading helpers ────────────────────────────────────────
class DownloadLayerThread(QThread):
    """Thread for downloading layer files from URLs"""
    finished = pyqtSignal(str)  # file path
    error = pyqtSignal(str)

    def __init__(self, client, url):
        super().__init__()
        self.client = client
        self.url = url

    def run(self):
        try:
            path = self.client.download_file(self.url)
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


def _add_layer_to_qgis(filepath, layer_name):
    """Add a downloaded layer to QGIS under the RASID group"""
    from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

    root = QgsProject.instance().layerTreeRoot()
    rasid_group = root.findGroup("RASID")
    if rasid_group is None:
        rasid_group = root.insertGroup(0, "RASID")

    ext = filepath.rsplit(".", 1)[-1].lower()
    if ext in ("tif", "tiff", "png", "jpg", "jpeg"):
        layer = QgsRasterLayer(filepath, layer_name)
    else:
        layer = QgsVectorLayer(filepath, layer_name, "ogr")

    if not layer.isValid():
        raise Exception(f"Could not load layer from {filepath}")

    QgsProject.instance().addMapLayer(layer, False)
    rasid_group.addLayer(layer)


def _extract_file_urls(text):
    """Extract downloadable file URLs from text (including markdown links).

    Returns list of tuples: (url, filename, extension, is_image)
    """
    # Match markdown links: [text](url) and extract the URL part
    # This handles: [filename.tif](https://...?query=params)
    markdown_pattern = r'\[([^\]]+)\]\((https?://[^\s\)]+\.(?:tif|tiff|png|jpg|jpeg|shp|geojson|gpkg|zip)[^\)]*)\)'
    markdown_matches = re.findall(markdown_pattern, text, re.IGNORECASE)

    result = []
    for _, url in markdown_matches:
        # Extract filename from URL path (before query params)
        filename = url.split('/')[-1].split('?')[0]
        ext = filename.rsplit('.', 1)[-1].lower()
        is_image = ext in ('png', 'jpg', 'jpeg')
        result.append((url, filename, ext, is_image))  # url includes full query params

    # Also match plain URLs (not in markdown) for backward compatibility
    plain_pattern = r'(?<!\]\()https?://[^\s<>"]+\.(?:tif|tiff|png|jpg|jpeg|shp|geojson|gpkg|zip)(?:\?[^\s<>"]*)?'
    plain_matches = re.findall(plain_pattern, text, re.IGNORECASE)

    for url in plain_matches:
        filename = url.split('/')[-1].split('?')[0]
        ext = filename.rsplit('.', 1)[-1].lower()
        is_image = ext in ('png', 'jpg', 'jpeg')
        # Avoid duplicates from markdown matches
        if not any(existing_url == url for existing_url, _, _, _ in result):
            result.append((url, filename, ext, is_image))

    return result


# ── Qt enum resolution that works on both PyQt5 and PyQt6 ─────────────────────
def _flag(*candidates):
    """Return the first Qt flag/enum that resolves, across PyQt5/PyQt6."""
    for path in candidates:
        obj = Qt
        ok = True
        for part in path.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                ok = False
                break
        if ok:
            return obj
    return None


_RICH_TEXT = _flag("TextFormat.RichText", "RichText") or 1
_SELECTABLE = _flag(
    "TextInteractionFlag.TextSelectableByMouse", "TextSelectableByMouse"
)
_LINKS = _flag(
    "TextInteractionFlag.LinksAccessibleByMouse", "LinksAccessibleByMouse"
)

# HttpStatusCodeAttribute, resolved across PyQt5 (enum on the class) and
# PyQt6 (nested under QNetworkRequest.Attribute).
_HTTP_STATUS_ATTR = getattr(
    QNetworkRequest, "HttpStatusCodeAttribute",
    getattr(getattr(QNetworkRequest, "Attribute", None),
            "HttpStatusCodeAttribute", None),
)


# ── Markdown -> HTML ──────────────────────────────────────────────────────────


def _style_code_blocks(html_text, dark_text=True):
    """Inline-style <pre>/<code> so QLabel rich text renders them nicely.

    QLabel doesn't apply an external stylesheet to inner HTML tags, so the
    only reliable way to style code is inline attributes on the generated HTML.
    """
    pre_bg = "rgba(0,0,0,0.06)" if dark_text else "rgba(255,255,255,0.18)"
    pre = (f'<pre style="background:{pre_bg}; padding:8px 10px; '
           f'border-radius:6px; font-family:Menlo,Consolas,monospace; '
           f'font-size:12px; white-space:pre-wrap;">')
    code = ('<code style="font-family:Menlo,Consolas,monospace; '
            'font-size:12px;">')
    return html_text.replace("<pre>", pre).replace("<code>", code)


def _style_tables(html_text):
    """Inline-style tables with theme-aware colors so they read in both modes.

    QLabel rich text does not apply an external stylesheet to inner HTML, and it
    honors ``background-color`` (not the ``background`` shorthand) on cells — so
    colors must be set inline, per cell. Previously these were hardcoded to dark
    text on a light background, which made table text unreadable in dark mode
    (dark text on the dark bubble). Colors now come from theme_utils.
    """
    text_color = theme_utils.get_text_color()
    border_color = theme_utils.get_card_border()
    cell_bg = theme_utils.get_sidebar_bg()
    header_bg = theme_utils.get_hover_bg()

    # Style the table element
    table = (f'<table style="border-collapse:collapse; width:100%; margin:10px 0; '
             f'border:1px solid {border_color}; background-color:{cell_bg}; '
             f'font-size:12px;">')

    # Style table headers
    th = (f'<th style="background-color:{header_bg}; color:{text_color}; '
          f'font-weight:bold; text-align:left; padding:8px 10px; '
          f'border:1px solid {border_color};">')

    # Style table cells (set background-color per cell so they are never
    # transparent over a dark bubble)
    td = (f'<td style="background-color:{cell_bg}; color:{text_color}; '
          f'padding:6px 10px; border:1px solid {border_color};">')

    html_text = html_text.replace("<table>", table)
    html_text = html_text.replace("<th>", th)
    html_text = html_text.replace("<td>", td)

    return html_text


def _render_body_html(text, dark_text=True):
    """Produce the HTML string a QLabel will display for a message body."""
    text = str(text or "")
    body = markdown.markdown(
        text, extensions=["fenced_code", "tables", "nl2br"]
    )
    # Apply inline styles for code blocks and tables
    body = _style_code_blocks(body, dark_text=dark_text)
    body = _style_tables(body)
    return body


# ── Trash icon (unchanged) ────────────────────────────────────────────────────
def create_trash_icon(size=24, color="#e74c3c"):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt_transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter_Antialiasing)
    pen = QPen(QColor(color)); pen.setWidth(2); p.setPen(pen)
    bt, bb = int(size * 0.35), int(size * 0.85)
    bl, br = int(size * 0.25), int(size * 0.75)
    p.drawRect(bl, bt, br - bl, bb - bt)
    lid = int(size * 0.3)
    p.drawLine(int(size * 0.2), lid, int(size * 0.8), lid)
    hy = int(size * 0.2)
    p.drawLine(int(size * 0.4), lid, int(size * 0.4), hy)
    p.drawLine(int(size * 0.6), lid, int(size * 0.6), hy)
    p.drawLine(int(size * 0.4), hy, int(size * 0.6), hy)
    p.drawLine(int(size * 0.5), int(size * 0.45), int(size * 0.5), int(size * 0.75))
    p.end()
    return QIcon(pixmap)


# ══════════════════════════════ Threads (unchanged logic) ════════════════════
class SendMessageThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, client, message, session_id=None, input_metadata=None, geojson_data=None):
        super().__init__()
        self.client = client
        self.message = message
        self.session_id = session_id
        self.input_metadata = input_metadata
        self.geojson_data = geojson_data

    def run(self):
        import time
        try:
            if not self.client.gopilot:
                raise Exception("GoPilot client not initialized. Check your API key.")

            if not self.session_id:
                self.progress.emit("Creating new chat session...")
                session = self.client.gopilot.create_session(title="New Chat")
                if isinstance(session, dict):
                    self.session_id = session.get("id")
                else:
                    raise Exception(f"Invalid session response: {type(session)}")

            self.progress.emit("Sending message to AI...")
            from .logger import debug_print
            debug_print(f"[GoPilot] Sending message: {self.message[:100]}...")
            debug_print(f"[GoPilot] Session ID: {self.session_id}")

            # If GeoJSON is attached, save it to a temporary file
            files_to_upload = None
            if self.geojson_data:
                import tempfile
                import os

                # Create temp GeoJSON file
                temp_dir = tempfile.gettempdir()
                geojson_path = os.path.join(temp_dir, "attached_geometry.geojson")

                with open(geojson_path, 'w', encoding='utf-8') as f:
                    json.dump(self.geojson_data, f, indent=2)

                files_to_upload = [geojson_path]
                debug_print(f"[GoPilot] Attaching GeoJSON file: {geojson_path}")

            result = self.client.gopilot.send_message(
                session_id=self.session_id,
                content=self.message,
                input_metadata=self.input_metadata,
                files=files_to_upload
            )

            debug_print(f"[GoPilot] Send message result: {result}")

            if not isinstance(result, dict):
                raise Exception(f"Unexpected response type: {type(result)}")

            task_info = result.get("task", {})
            task_id = task_info.get("task_id") if isinstance(task_info, dict) else None
            if not task_id:
                raise Exception("No task_id in response")

            message_content = None
            self.progress.emit("AI is thinking...")
            max_attempts, poll_interval = 60, 2

            for attempt in range(max_attempts):
                time.sleep(poll_interval)
                try:
                    status = self.client.gopilot.get_task_status(task_id)
                    task_status = status.get("status", "unknown")
                    pct = status.get("progress", 0)
                    if pct > 0:
                        self.progress.emit(f"AI is thinking... {pct}%")
                    if task_status == "completed":
                        llm = status.get("llm_message", {})
                        if isinstance(llm, dict):
                            message_content = llm.get("content", "")
                        break
                    elif task_status == "failed":
                        raise Exception(
                            f"AI processing failed: {status.get('error', 'Task failed')}"
                        )
                except Exception as poll_error:
                    debug_print(f"[GoPilot] Polling error: {poll_error}")
                    continue

            if not message_content:
                messages = self.client.gopilot.get_messages(self.session_id)
                if messages:
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant":
                            message_content = msg.get("content", "")
                            break
                if not message_content:
                    raise Exception("AI response timeout. Check the chat history.")

            self.finished.emit({
                "session_id": self.session_id,
                "task_id": task_id,
                "message": message_content,
            })
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            debug_print(f"[GoPilot] Error in SendMessageThread: {error_trace}")

            # Extract more details from HTTP errors
            error_msg = str(e)
            if hasattr(e, 'response'):
                try:
                    error_details = e.response.json()
                    error_msg = f"{error_msg}\nDetails: {error_details}"
                except:
                    try:
                        error_msg = f"{error_msg}\nResponse: {e.response.text[:200]}"
                    except:
                        pass

            self.error.emit(error_msg)


class FetchChatsThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            if not self.client.gopilot:
                raise Exception("GoPilot client not initialized")
            history = self.client.gopilot.get_session_history()
            chats = []
            for s in history.get("results", []):
                chats.append({
                    "id": s.get("id"),
                    "title": s.get("title", "Untitled Chat"),
                    "timestamp": s.get("created_at", "")[:16].replace("T", " "),
                })
            self.finished.emit(chats)
        except Exception as e:
            self.error.emit(str(e))


class FetchMessagesThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, client, session_id):
        super().__init__()
        self.client = client
        self.session_id = session_id

    def run(self):
        try:
            if not self.client.gopilot:
                raise Exception("GoPilot client not initialized")
            self.finished.emit(self.client.gopilot.get_messages(self.session_id))
        except Exception as e:
            self.error.emit(str(e))


class DeleteChatThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, client, session_id):
        super().__init__()
        self.client = client
        self.session_id = session_id

    def run(self):
        try:
            if not self.client.gopilot:
                raise Exception("GoPilot client not initialized")
            self.client.gopilot.delete_session(self.session_id)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════ Message bubble ═══════════════════════════════
class MessageBubble(QFrame):
    """A single chat bubble.

    Body is a word-wrapped QLabel that sizes its own height — no manual
    height syncing, no internal scrollbar, no refresh hacks.
    """

    BUBBLE_MAX_WIDTH = 560
    _BODY_PAD = 28  # horizontal padding inside the bubble (14 + 14)

    def __init__(self, text, role="ai", with_time=True, timestamp=None, client=None, has_attachment=False, parent=None):
        super().__init__(parent)
        self.role = role
        self.client = client
        self._download_threads = []
        self._has_attachment = has_attachment

        if role == "user":
            bg, fg, border = theme_utils.BRAND_PRIMARY, "#ffffff", theme_utils.BRAND_PRIMARY
            self._dark_text = False
        elif role == "system":
            bg = theme_utils.get_hover_bg()
            fg = theme_utils.get_secondary_text_color()
            border = "transparent"
            self._dark_text = True
        else:  # ai
            bg = theme_utils.get_card_bg()
            fg = theme_utils.get_text_color()
            border = theme_utils.get_card_border()
            self._dark_text = True

        self.setObjectName("bubble")
        self.setFrameShape(QFrame_StyledPanel)
        self.setMaximumWidth(self.BUBBLE_MAX_WIDTH)
        self.setStyleSheet(f"""
            QFrame#bubble {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(_RICH_TEXT)
        self._body.setOpenExternalLinks(True)
        self._body.setMaximumWidth(self.BUBBLE_MAX_WIDTH - self._BODY_PAD)
        if _SELECTABLE is not None and _LINKS is not None:
            self._body.setTextInteractionFlags(_SELECTABLE | _LINKS)
        self._body.setStyleSheet(
            f"color:{fg}; font-size:13px; background:transparent; border:none;"
        )
        lay.addWidget(self._body)

        # Show attachment indicator for user messages with files
        if role == "user" and has_attachment:
            attachment_label = QLabel("📎 GeoJSON attached")
            attachment_label.setStyleSheet(
                f"color:{fg}; font-size:11px; background:transparent; "
                f"border:none; font-style:italic; margin-top:4px;"
            )
            attachment_label.setAlignment(Qt_AlignRight)
            lay.addWidget(attachment_label)

        # Container for download buttons (will be populated when content is set)
        self._download_layout = QVBoxLayout()
        self._download_layout.setSpacing(4)
        self._download_layout.setContentsMargins(0, 8, 0, 0)  # Add top padding
        lay.addLayout(self._download_layout)

        if with_time and role != "system":
            # Use provided timestamp or current time
            time_str = timestamp if timestamp else QDateTime.currentDateTime().toString("hh:mm")
            t = QLabel(time_str)
            t.setStyleSheet(
                f"color:{fg}; font-size:10px; background:transparent; border:none;"
            )
            t.setAlignment(Qt_AlignRight if role == "user" else Qt_AlignLeft)
            # Slightly dim the timestamp without a second color lookup.
            t.setProperty("class", "ts")
            lay.addWidget(t)

        self.set_content(text)

    def set_content(self, text):
        """Replace the body text. Safe to call repeatedly while streaming.

        The full message is rendered as-is, so any file links stay visible and
        clickable in the text. Then one control per detected file link is
        appended to ``_download_layout``, which sits at the very end of the
        bubble (just above the timestamp). Because the controls always go into
        that trailing container — regardless of where the link appears in the
        text — the download/install buttons are always grouped at the end of
        the message.
        """
        # Clear existing download buttons / inline images
        while self._download_layout.count():
            item = self._download_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Render the full text WITH links intact (do not strip them out).
        self._body.setText(
            _render_body_html(text, dark_text=self._dark_text)
        )

        # Append one control per detected file link, at the end of the bubble.
        # (Only for AI messages that have a client capable of downloading.)
        if self.role == "ai" and self.client:
            for url, filename, ext, is_image in _extract_file_urls(text):
                # Images render as an inline preview (with a save button);
                # every other file type gets a download/install button.
                if is_image:
                    self._add_inline_image(url, filename)
                else:
                    self._add_download_button(url, filename, ext)

    def _add_download_button(self, url, filename, ext):
        """Add a download button for a file URL"""
        btn = QPushButton(f"📥 Download {filename}")
        btn.setCursor(Qt_PointingHandCursor)
        btn.setMaximumWidth(self.BUBBLE_MAX_WIDTH - self._BODY_PAD)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {theme_utils.BRAND_PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {theme_utils.BRAND_HOVER};
            }}
            QPushButton:disabled {{
                background: {theme_utils.get_hover_bg()};
                color: {theme_utils.get_secondary_text_color()};
            }}
        """)
        btn.clicked.connect(lambda: self._download_and_load(url, filename, btn))
        self._download_layout.addWidget(btn)

    def _download_and_load(self, url, filename, button):
        """Download file and load it into QGIS"""
        if not self.client:
            QMessageBox.warning(self, "Error", "Cannot download: client not available")
            return

        button.setText("⏳ Downloading...")
        button.setEnabled(False)

        thread = DownloadLayerThread(self.client, url)
        thread.finished.connect(lambda path: self._on_download_complete(path, filename, button))
        thread.error.connect(lambda msg: self._on_download_error(msg, button))
        self._download_threads.append(thread)
        thread.start()

    def _on_download_complete(self, filepath, filename, button):
        """Handle successful download"""
        try:
            layer_name = filename.rsplit('.', 1)[0]  # Remove extension for layer name
            _add_layer_to_qgis(filepath, layer_name)
            button.setText(f"✅ Loaded: {filename}")
            button.setEnabled(False)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Downloaded but failed to load:\n{e}")
            button.setText(f"⚠️ Load failed: {filename}")
            button.setEnabled(True)

    def _on_download_error(self, error_msg, button):
        """Handle download error"""
        QMessageBox.warning(self, "Download Error", f"Failed to download:\n{error_msg}")
        button.setText("🔄 Retry Download")
        button.setEnabled(True)

    def _add_inline_image(self, url, filename):
        """Add an inline image preview plus an always-present save button.

        The save button is added immediately — not only after a successful
        load — so every image link always ends up with a working control at
        the end of the bubble, even if the preview itself fails to load (for
        example an expired or signature-sensitive presigned URL).
        """
        # Image preview placeholder
        img_label = QLabel()
        img_label.setAlignment(Qt_AlignCenter)
        img_label.setMaximumWidth(self.BUBBLE_MAX_WIDTH - self._BODY_PAD)
        img_label.setText("🖼️ Loading image...")
        img_label.setStyleSheet(
            f"background:{theme_utils.get_hover_bg()}; "
            f"padding:8px; border-radius:6px; color:{theme_utils.get_secondary_text_color()};"
        )
        self._download_layout.addWidget(img_label)

        # Always add the save button up front so it is present regardless of
        # whether the preview loads.
        from functools import partial
        download_btn = QPushButton(f"💾 Save {filename}")
        download_btn.setCursor(Qt_PointingHandCursor)
        download_btn.setMaximumWidth(self.BUBBLE_MAX_WIDTH - self._BODY_PAD)
        download_btn.setStyleSheet(f"""
            QPushButton {{
                background:{theme_utils.get_card_bg()};
                color:{theme_utils.get_text_color()};
                border:1px solid {theme_utils.get_card_border()};
                border-radius:6px;
                padding:6px 10px;
                font-size:11px;
                text-align:center;
            }}
            QPushButton:hover {{
                background:{theme_utils.get_hover_bg()};
                border-color:{theme_utils.BRAND_PRIMARY};
            }}
        """)
        download_btn.clicked.connect(partial(self._save_image_locally, url, filename))
        self._download_layout.addWidget(download_btn)

        # Download the preview. Use QUrl.fromEncoded so an already
        # percent-encoded presigned URL (e.g. AWS S3 with %2F in the
        # credential) is NOT re-encoded — re-encoding would corrupt the
        # signature and return 403.
        if not hasattr(self, '_network_managers'):
            self._network_managers = []
        network_manager = QNetworkAccessManager(self)
        self._network_managers.append(network_manager)
        request = QNetworkRequest(QUrl.fromEncoded(url.encode('utf-8')))

        def on_image_loaded():
            # Get reply from sender
            reply = network_manager.sender()
            if not reply:
                img_label.setText(f"❌ Preview unavailable: {filename}")
                return

            # Check for errors. A 403 on a presigned S3 URL almost always
            # means the link's validity window (e.g. "valid 7 days") has
            # elapsed, so call that out specifically instead of a generic
            # failure.
            if reply.error():
                status = (
                    reply.attribute(_HTTP_STATUS_ATTR)
                    if _HTTP_STATUS_ATTR is not None else None
                )
                if status == 403:
                    img_label.setText(f"⚠️ Link expired: {filename}")
                else:
                    img_label.setText(f"❌ Preview unavailable: {filename}")
                reply.deleteLater()
                return

            try:
                # Load image data
                image_data = reply.readAll()
                pixmap = QPixmap()
                if pixmap.loadFromData(image_data):
                    # Scale to fit bubble width
                    max_width = self.BUBBLE_MAX_WIDTH - self._BODY_PAD - 16
                    if pixmap.width() > max_width:
                        pixmap = pixmap.scaledToWidth(max_width, Qt_SmoothTransformation)

                    # Limit height to 400px
                    if pixmap.height() > 400:
                        pixmap = pixmap.scaledToHeight(400, Qt_SmoothTransformation)

                    img_label.setPixmap(pixmap)
                    img_label.setText("")
                    img_label.setStyleSheet(
                        "background:transparent; padding:4px; border-radius:6px;"
                    )
                else:
                    img_label.setText(f"❌ Failed to decode image: {filename}")
            except Exception as e:
                img_label.setText(f"❌ Error loading image: {str(e)}")
            finally:
                # Clean up reply
                reply.deleteLater()

        reply = network_manager.get(request)
        reply.finished.connect(on_image_loaded)

    def _save_image_locally(self, url, filename):
        """Save image to local disk"""
        from qgis.PyQt.QtWidgets import QFileDialog
        import os

        # Ask user where to save
        default_path = os.path.join(os.path.expanduser("~"), "Downloads", filename)
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image",
            default_path,
            "Images (*.png *.jpg *.jpeg)"
        )

        if not save_path:
            return

        # Download and save
        try:
            thread = DownloadLayerThread(self.client, url)
            thread.finished.connect(
                lambda temp_path: self._on_image_saved(temp_path, save_path, filename)
            )
            thread.error.connect(
                lambda msg: QMessageBox.warning(self, "Save Error", f"Failed to save image:\n{msg}")
            )
            self._download_threads.append(thread)
            thread.start()
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save image:\n{str(e)}")

    def _on_image_saved(self, temp_path, save_path, filename):
        """Handle image saved to disk"""
        import shutil
        try:
            shutil.move(temp_path, save_path)
            # Note: Can't access parent page's status_label, so just show message box on error
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to move image:\n{str(e)}")


# ══════════════════════════════ Main page ════════════════════════════════════
class GoPilotPage(QWidget):
    """GoPilot AI Chat interface (Option 3: QLabel-per-message)."""

    def __init__(self, client, iface=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.iface = iface
        self.current_chat_id = None
        self._threads = []
        self._welcome_widget = None
        self._thinking_row = None
        self._streaming_bubble = None
        self._attached_geojson = None  # Store drawn/selected geometry

        # Initialize geometry input manager
        self.geo_manager = GeometryInputManager(iface, parent_widget=self)
        self.geo_manager.geometry_ready.connect(self._on_geometry_ready)

        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        splitter = QSplitter(Qt_Horizontal)
        splitter.addWidget(self._create_history_panel())
        splitter.addWidget(self._create_chat_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        main.addWidget(splitter)

        self.load_chat_history()
        self._show_greeting()

    # ── left sidebar ──────────────────────────────────────────────────────────
    def _create_history_panel(self):
        panel = QFrame()
        panel.setMinimumWidth(200)
        pbg = theme_utils.get_sidebar_bg()
        pborder = theme_utils.get_sidebar_border()
        panel.setStyleSheet(
            f"QFrame {{ background:{pbg}; border-right:1px solid {pborder}; }}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(12)

        header = QLabel("Chat History")
        header.setStyleSheet(
            f"font-size:16px; font-weight:bold; color:{theme_utils.get_text_color()}; "
            f"border:none; background:transparent;"
        )
        lay.addWidget(header)

        self.btn_new_chat = QPushButton("+ New Chat")
        self.btn_new_chat.setCursor(Qt_PointingHandCursor)
        self.btn_new_chat.setAutoDefault(False)  # Prevent Enter key capture
        self.btn_new_chat.setStyleSheet(f"""
            QPushButton {{
                background:{theme_utils.BRAND_PRIMARY}; color:white; border:none;
                border-radius:6px; padding:10px; font-size:13px; font-weight:bold;
            }}
            QPushButton:hover {{ background:{theme_utils.BRAND_HOVER}; }}
        """)
        self.btn_new_chat.clicked.connect(self.start_new_chat)
        lay.addWidget(self.btn_new_chat)

        self.chat_list = QListWidget()
        self.chat_list.setFrameShape(QFrame_NoFrame)
        self.chat_list.setStyleSheet(f"""
            QListWidget {{
                background:{theme_utils.get_card_bg()};
                border:1px solid {pborder}; border-radius:6px;
                color:{theme_utils.get_text_color()}; font-size:12px; padding:4px;
            }}
            QListWidget::item {{ padding:2px; border-radius:4px; margin:2px 0; }}
            QListWidget::item:hover {{ background:{theme_utils.get_hover_bg()}; }}
            QListWidget::item:selected {{
                background:{theme_utils.BRAND_PRIMARY}; color:white;
            }}
        """)
        lay.addWidget(self.chat_list)
        return panel

    # ── right chat panel ──────────────────────────────────────────────────────
    def _create_chat_panel(self):
        panel = QFrame()
        panel.setStyleSheet(f"background:{theme_utils.get_card_bg()};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        title = QLabel("GoPilot")
        title.setStyleSheet(
            f"font-size:20px; font-weight:bold; color:{theme_utils.get_text_color()}; "
            f"border:none; background:transparent;"
        )
        head.addWidget(title)
        head.addStretch()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            f"font-size:12px; color:{theme_utils.get_secondary_text_color()}; "
            f"border:none; background:transparent;"
        )
        head.addWidget(self.status_label)
        lay.addLayout(head)

        desc = QLabel("Ask me anything about geospatial analysis and earth "
                      "observation I can automate anything for you!")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size:13px; color:{theme_utils.get_secondary_text_color()}; "
            f"border:none; background:transparent; margin-bottom:8px;"
        )
        lay.addWidget(desc)

        # Scrollable message area.
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame_NoFrame)
        self.chat_scroll.setStyleSheet(f"""
            QScrollArea {{
                background:{theme_utils.get_sidebar_bg()};
                border:1px solid {theme_utils.get_card_border()};
                border-radius:8px;
            }}
        """)
        self.messages_widget = QWidget()
        self.messages_widget.setStyleSheet("background:transparent;")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(14, 14, 14, 14)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()  # trailing stretch keeps msgs top-aligned
        self.chat_scroll.setWidget(self.messages_widget)
        lay.addWidget(self.chat_scroll)

        # Input row.
        row = QHBoxLayout()
        row.setSpacing(8)

        # Draw button (only if iface available)
        if self.iface:
            self.btn_draw = QPushButton("🖊️")
            self.btn_draw.setCursor(Qt_PointingHandCursor)
            self.btn_draw.setFixedSize(44, 44)
            self.btn_draw.setToolTip("Draw geometry on map")
            self.btn_draw.setAutoDefault(False)  # Prevent Enter key capture
            self.btn_draw.setStyleSheet(f"""
                QPushButton {{
                    background:{theme_utils.get_card_bg()};
                    border:2px solid {theme_utils.get_card_border()};
                    border-radius:8px; font-size:18px;
                }}
                QPushButton:hover {{
                    background:{theme_utils.get_hover_bg()};
                    border-color:{theme_utils.BRAND_PRIMARY};
                }}
            """)
            self.btn_draw.clicked.connect(self._start_draw_geometry)
            row.addWidget(self.btn_draw)

            # Layer picker button
            self.btn_layer = QPushButton("📐")
            self.btn_layer.setCursor(Qt_PointingHandCursor)
            self.btn_layer.setFixedSize(44, 44)
            self.btn_layer.setToolTip("Select layer from QGIS")
            self.btn_layer.setAutoDefault(False)  # Prevent Enter key capture
            self.btn_layer.setStyleSheet(f"""
                QPushButton {{
                    background:{theme_utils.get_card_bg()};
                    border:2px solid {theme_utils.get_card_border()};
                    border-radius:8px; font-size:18px;
                }}
                QPushButton:hover {{
                    background:{theme_utils.get_hover_bg()};
                    border-color:{theme_utils.BRAND_PRIMARY};
                }}
            """)
            self.btn_layer.clicked.connect(self._pick_layer)
            row.addWidget(self.btn_layer)

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setStyleSheet(f"""
            QLineEdit {{
                background:{theme_utils.get_card_bg()};
                color:{theme_utils.get_text_color()};
                border:2px solid {theme_utils.get_card_border()};
                border-radius:8px; padding:12px 16px; font-size:13px;
            }}
            QLineEdit:focus {{ border:2px solid {theme_utils.BRAND_PRIMARY}; }}
        """)
        self.message_input.returnPressed.connect(self.send_message)
        row.addWidget(self.message_input)

        self.btn_send = QPushButton("Send")
        self.btn_send.setCursor(Qt_PointingHandCursor)
        self.btn_send.setFixedWidth(100)
        self.btn_send.setDefault(True)  # Make this the default button for Enter key
        self.btn_send.setAutoDefault(True)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background:{theme_utils.BRAND_PRIMARY}; color:white; border:none;
                border-radius:8px; padding:12px 20px; font-size:13px; font-weight:bold;
            }}
            QPushButton:hover {{ background:{theme_utils.BRAND_HOVER}; }}
            QPushButton:disabled {{
                background:{theme_utils.get_sidebar_bg()};
                color:{theme_utils.get_secondary_text_color()};
            }}
        """)
        self.btn_send.clicked.connect(self.send_message)
        row.addWidget(self.btn_send)
        lay.addLayout(row)
        return panel

    # ── message-area helpers ──────────────────────────────────────────────────
    def _clear_messages(self):
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._welcome_widget = None
        self._thinking_row = None
        self._streaming_bubble = None

    def _add_bubble(self, bubble, side):
        """Insert a bubble in an alignment row, before the trailing stretch.

        `side` is "left", "right", or "center". Wrapping the bubble in an
        HBox with a stretch on the opposite side is the most reliable way to
        pin alignment AND let the bubble hug its content width.
        """
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        hb = QHBoxLayout(row)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(0)
        if side == "right":
            hb.addStretch()
            hb.addWidget(bubble)
        elif side == "center":
            hb.addStretch()
            hb.addWidget(bubble)
            hb.addStretch()
        else:  # left
            hb.addWidget(bubble)
            hb.addStretch()

        insert_at = max(0, self.messages_layout.count() - 1)  # before stretch
        self.messages_layout.insertWidget(insert_at, row)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return row

    def add_message(self, text, is_user=True, timestamp=None, has_attachment=False):
        role = "user" if is_user else "ai"
        bubble = MessageBubble(text, role=role, timestamp=timestamp, client=self.client, has_attachment=has_attachment)
        return self._add_bubble(bubble, "right" if is_user else "left")

    def _add_system_message(self, text):
        bubble = MessageBubble(text, role="system", with_time=False, client=self.client)
        return self._add_bubble(bubble, "center")

    def _show_greeting(self):
        self._clear_messages()
        self.messages_layout.addStretch()  # re-establish trailing stretch

        greeting = QWidget()
        greeting.setStyleSheet("background:transparent;")
        outer = QVBoxLayout(greeting)
        outer.addStretch()
        rowc = QHBoxLayout()
        rowc.addStretch()
        col = QVBoxLayout()
        col.setSpacing(10)

        t = QLabel("\U0001F44B  Welcome to GoPilot")
        t.setAlignment(Qt_AlignCenter)
        t.setStyleSheet(
            f"font-size:22px; font-weight:bold; color:{theme_utils.get_text_color()}; "
            f"border:none; background:transparent;"
        )
        sub = QLabel("Your geospatial intelligence co-pilot.\n"
                     "Ask me about satellite imagery, Earth observation, "
                     "or QGIS operations.")
        sub.setAlignment(Qt_AlignCenter)
        sub.setWordWrap(True)
        sub.setMaximumWidth(420)
        sub.setStyleSheet(
            f"font-size:13px; color:{theme_utils.get_secondary_text_color()}; "
            f"border:none; background:transparent;"
        )
        col.addWidget(t)
        col.addWidget(sub)
        rowc.addLayout(col)
        rowc.addStretch()
        outer.addLayout(rowc)
        outer.addStretch()

        # Greeting fills the area, so insert it before the stretch.
        greeting.setSizePolicy(QSizePolicy_Expanding, QSizePolicy_Expanding)
        self.messages_layout.insertWidget(0, greeting)
        self._welcome_widget = greeting

    def _remove_greeting(self):
        if self._welcome_widget is not None:
            self._welcome_widget.deleteLater()
            self._welcome_widget = None

    # ── thinking indicator ────────────────────────────────────────────────────
    def _show_thinking(self):
        self._thinking_row = self.add_message("\U0001F914 Thinking...", is_user=False)

    def _hide_thinking(self):
        if self._thinking_row is not None:
            self._thinking_row.deleteLater()
            self._thinking_row = None

    # ── streaming hooks (ready to wire to a chunked transport) ────────────────
    def begin_ai_stream(self):
        self._hide_thinking()
        bubble = MessageBubble("", role="ai", client=self.client)
        self._add_bubble(bubble, "left")
        self._streaming_bubble = bubble
        return bubble

    def update_ai_stream(self, full_text):
        if self._streaming_bubble is not None:
            self._streaming_bubble.set_content(full_text)
            self._scroll_to_bottom()

    def finish_ai_stream(self, full_text=None):
        if self._streaming_bubble is not None and full_text is not None:
            self._streaming_bubble.set_content(full_text)
        self._streaming_bubble = None
        self._enable_input(True)
        self.status_label.setText("Ready")
        self._scroll_to_bottom()

    # ── scrolling / input state ───────────────────────────────────────────────
    def _scroll_to_bottom(self):
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _enable_input(self, enabled):
        self.message_input.setEnabled(enabled)
        self.btn_send.setEnabled(enabled)
        if enabled:
            self.message_input.setFocus()

    # ── send flow ─────────────────────────────────────────────────────────────
    def send_message(self):
        message = self.message_input.text().strip()
        if not message:
            return
        self._remove_greeting()

        # Check if file is attached
        has_file = self._attached_geojson is not None

        # Add user message with file indicator
        self.add_message(message, is_user=True, has_attachment=has_file)
        self.message_input.clear()
        self._show_thinking()
        self._enable_input(False)
        self.status_label.setText("Sending message...")

        # Prepare input_metadata and geojson_data if geometry is attached
        input_metadata = None
        geojson_data = None

        if self._attached_geojson:
            input_metadata = {
                "type": "vector_upload",
                "format": "geojson"
            }
            geojson_data = self._attached_geojson

        thread = SendMessageThread(
            self.client,
            message,
            self.current_chat_id,
            input_metadata=input_metadata,
            geojson_data=geojson_data
        )
        thread.finished.connect(self._on_message_received)
        thread.error.connect(self._on_message_error)
        thread.progress.connect(self._on_message_progress)
        self._threads.append(thread)
        thread.start()

        # Clear attached geometry after sending
        self._clear_attached_geometry()

    def _on_message_progress(self, status_text):
        self.status_label.setText(status_text)

    def _on_message_received(self, response_data):
        if not self.current_chat_id and response_data.get("session_id"):
            self.current_chat_id = response_data["session_id"]
            self.load_chat_history()
        self._hide_thinking()
        msg = response_data.get("message", "")
        if msg:
            self.add_message(msg, is_user=False)
        self._enable_input(True)
        self.status_label.setText("Ready")

    def _on_message_error(self, error_msg):
        self._hide_thinking()
        self._add_system_message(f"\u26A0\uFE0F Error: {error_msg}")
        self._enable_input(True)
        self.status_label.setText("Error occurred")

    # ── chat history (left list) ──────────────────────────────────────────────
    def load_chat_history(self):
        self.chat_list.clear()
        thread = FetchChatsThread(self.client)
        thread.finished.connect(self._on_chats_loaded)
        thread.error.connect(self._on_chats_error)
        self._threads.append(thread)
        thread.start()

    def _on_chats_loaded(self, chats):
        for chat in chats:
            item_widget = QWidget()
            il = QHBoxLayout(item_widget)
            il.setContentsMargins(8, 6, 8, 6)
            il.setSpacing(8)

            info = QVBoxLayout()
            info.setSpacing(2)
            tl = QLabel(chat["title"])
            tl.setObjectName("chat_title")
            tl.setStyleSheet("font-weight:bold; font-size:12px; border:none; background:transparent;")
            info.addWidget(tl)
            tm = QLabel(chat["timestamp"])
            tm.setObjectName("chat_time")
            tm.setStyleSheet("font-size:10px; color:#888; border:none; background:transparent;")
            info.addWidget(tm)
            il.addLayout(info, stretch=1)

            del_btn = QPushButton()
            del_btn.setIcon(create_trash_icon(16, theme_utils.BRAND_DANGER))
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt_PointingHandCursor)
            del_btn.setToolTip("Delete chat")
            del_btn.setAutoDefault(False)  # Prevent Enter key from triggering delete
            del_btn.setDefault(False)
            del_btn.setStyleSheet(
                f"QPushButton {{ background:{theme_utils.get_card_bg()}; "
                f"border:1px solid {theme_utils.get_card_border()}; "
                f"border-radius:4px; padding:4px; }}"
                f"QPushButton:hover {{ background:{theme_utils.get_danger_hover_bg()}; "
                f"border-color:{theme_utils.BRAND_DANGER}; }}"
            )
            del_btn.clicked.connect(lambda _, c=chat: self._on_delete_chat(c))
            il.addWidget(del_btn, alignment=Qt_AlignTop)

            item = QListWidgetItem(self.chat_list)
            item.setData(Qt_UserRole, chat["id"])
            item.setSizeHint(item_widget.sizeHint())
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, item_widget)
            item_widget.mousePressEvent = lambda e, itm=item: self._on_chat_item_clicked(itm)

        self.chat_list.itemSelectionChanged.connect(self._update_chat_list_colors)

    def _on_chats_error(self, error_msg):
        debug_print(f"[GoPilot] Failed to load chat history: {error_msg}")

    def _on_chat_item_clicked(self, item):
        self.chat_list.setCurrentItem(item)
        self.load_chat(item)

    def _update_chat_list_colors(self):
        text_color = theme_utils.get_text_color()
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            widget = self.chat_list.itemWidget(item)
            if not widget:
                continue
            tl = widget.findChild(QLabel, "chat_title")
            tm = widget.findChild(QLabel, "chat_time")
            if item.isSelected():
                if tl:
                    tl.setStyleSheet("font-weight:bold; font-size:12px; border:none; background:transparent; color:white;")
                if tm:
                    tm.setStyleSheet("font-size:10px; border:none; background:transparent; color:rgba(255,255,255,0.8);")
            else:
                if tl:
                    tl.setStyleSheet(f"font-weight:bold; font-size:12px; border:none; background:transparent; color:{text_color};")
                if tm:
                    tm.setStyleSheet("font-size:10px; color:#888; border:none; background:transparent;")

    def _on_delete_chat(self, chat):
        chat_title = chat.get("title", "this chat")
        chat_id = chat.get("id")
        box = QMessageBox(self)
        box.setWindowTitle("Delete Chat")
        box.setIcon(QMessageBox_Question)
        box.setText(f'Are you sure you want to delete "{chat_title}"?')
        box.setInformativeText("This action cannot be undone.")
        box.setStandardButtons(QMessageBox_Yes | QMessageBox_No)
        box.setDefaultButton(QMessageBox_No)
        if exec_dialog(box) != QMessageBox_Yes:
            return
        thread = DeleteChatThread(self.client, chat_id)
        thread.finished.connect(lambda: self._on_chat_deleted(chat_id))
        thread.error.connect(
            lambda msg: QMessageBox.warning(self, "Error", f"Failed to delete chat:\n{msg}")
        )
        self._threads.append(thread)
        thread.start()

    def _on_chat_deleted(self, deleted_chat_id):
        if self.current_chat_id == deleted_chat_id:
            self.start_new_chat()
        self.load_chat_history()

    # ── load a conversation ───────────────────────────────────────────────────
    def load_chat(self, item):
        chat_id = item.data(Qt_UserRole)
        self.current_chat_id = chat_id
        self._clear_messages()
        self.messages_layout.addStretch()
        self._add_system_message(
            f"\U0001F4C2 Loading chat: {item.text().split(chr(10))[0]}..."
        )
        self.status_label.setText(f"Loading chat {chat_id}...")
        thread = FetchMessagesThread(self.client, chat_id)
        thread.finished.connect(self._on_messages_loaded)
        thread.error.connect(self._on_messages_error)
        self._threads.append(thread)
        thread.start()

    def _on_messages_loaded(self, messages):
        self._clear_messages()
        self.messages_layout.addStretch()

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            is_user_flag = msg.get("is_user", None)

            # DEBUG: Print LLM message content to Python console
            if role == "assistant" or (is_user_flag is not None and not is_user_flag):
                debug_print("="*80)
                debug_print("[GoPilot] LLM Message Content:")
                debug_print("="*80)
                debug_print(content)
                debug_print("="*80)

            # Extract and format timestamp from system_registration_date
            # Format: "2026-06-27T21:33:58.818829Z" -> "Jun 27 21:33"
            timestamp = None
            system_date = msg.get("system_registration_date", "")
            if system_date:
                try:
                    # Parse ISO timestamp with QDateTime
                    dt = QDateTime.fromString(system_date[:19], "yyyy-MM-ddTHH:mm:ss")
                    if dt.isValid():
                        # Format as "MMM d HH:mm" (e.g., "Jun 18 18:40")
                        timestamp = dt.toString("MMM d HH:mm")
                except Exception:
                    timestamp = None

            if is_user_flag is not None:
                self.add_message(content, is_user=is_user_flag, timestamp=timestamp)
            elif role == "assistant":
                self.add_message(content, is_user=False, timestamp=timestamp)
            else:
                self.add_message(content, is_user=True, timestamp=timestamp)
        self.status_label.setText(
            f"This chat contains {len(messages)} messages"
        )

    def _on_messages_error(self, error_msg):
        self._add_system_message(f"\u26A0\uFE0F Failed to load messages: {error_msg}")
        self.status_label.setText("Error loading chat")

    def start_new_chat(self):
        self.current_chat_id = None
        self.chat_list.clearSelection()
        self._show_greeting()
        self.status_label.setText("New Chat")
        self.message_input.setFocus()
    # ── geometry input (draw & layer picker) ──────────────────────────────────
    def _start_draw_geometry(self):
        """Start drawing geometry on the map"""
        if not self.iface:
            return

        # Update button style to indicate active state
        self.btn_draw.setStyleSheet(f"""
            QPushButton {{
                background:{theme_utils.BRAND_PRIMARY};
                border:2px solid {theme_utils.BRAND_PRIMARY};
                border-radius:8px; font-size:18px; color:white;
            }}
        """)
        self.status_label.setText("Draw on map (right-click to finish)")

        # Start draw mode using geometry manager with help dialog
        self.geo_manager.start_draw_mode(
            minimize_parent=True,
            show_help=True,
            help_context="gopilot"
        )

    def _pick_layer(self):
        """Show layer picker dialog"""
        if not self.iface:
            return

        # Show layer picker using geometry manager
        self.geo_manager.show_layer_picker(
            title="Select Layer",
            message="Select a vector layer to attach to your message:"
        )

    def _on_geometry_ready(self, geometry_data):
        """Handle geometry input completion from drawing or layer selection.

        Args:
            geometry_data: Dict with 'geojson', 'source', and 'name' keys
        """
        # Store the GeoJSON data
        self._attached_geojson = geometry_data['geojson']

        # Update UI based on source
        source = geometry_data['source']
        name = geometry_data['name']

        if source == 'draw':
            # Reset draw button style
            self.btn_draw.setStyleSheet(f"""
                QPushButton {{
                    background:{theme_utils.get_card_bg()};
                    border:2px solid {theme_utils.BRAND_PRIMARY};
                    border-radius:8px; font-size:18px;
                }}
            """)
            self.status_label.setText("Geometry attached ✓")
            self.message_input.setPlaceholderText("Geometry attached - Type your message...")
        elif source == 'layer':
            # Highlight layer button
            self.btn_layer.setStyleSheet(f"""
                QPushButton {{
                    background:{theme_utils.get_card_bg()};
                    border:2px solid {theme_utils.BRAND_PRIMARY};
                    border-radius:8px; font-size:18px;
                }}
            """)
            self.status_label.setText(f"Layer '{name}' attached ✓")
            self.message_input.setPlaceholderText(f"Layer '{name}' attached - Type your message...")

    def _clear_attached_geometry(self):
        """Clear attached geometry and reset UI"""
        self._attached_geojson = None
        self.message_input.setPlaceholderText("Type your message here...")
        self.status_label.setText("Ready")

        # Reset button styles if iface is available
        if self.iface:
            self.btn_draw.setStyleSheet(f"""
                QPushButton {{
                    background:{theme_utils.get_card_bg()};
                    border:2px solid {theme_utils.get_card_border()};
                    border-radius:8px; font-size:18px;
                }}
                QPushButton:hover {{
                    background:{theme_utils.get_hover_bg()};
                    border-color:{theme_utils.BRAND_PRIMARY};
                }}
            """)
            self.btn_layer.setStyleSheet(f"""
                QPushButton {{
                    background:{theme_utils.get_card_bg()};
                    border:2px solid {theme_utils.get_card_border()};
                    border-radius:8px; font-size:18px;
                }}
                QPushButton:hover {{
                    background:{theme_utils.get_hover_bg()};
                    border-color:{theme_utils.BRAND_PRIMARY};
                }}
            """)


    def closeEvent(self, event):
        """Handle widget close event - clean up resources"""
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self):
        """Clean up resources to prevent crashes"""
        # Stop all running threads
        for thread in self._threads:
            if thread and thread.isRunning():
                try:
                    thread.quit()
                    thread.wait(1000)  # Wait max 1 second
                except:
                    pass

        # Clean up geometry manager
        if hasattr(self, "geo_manager") and self.geo_manager:
            try:
                self.geo_manager.cleanup()
            except:
                pass

        # Clear thread list
        self._threads.clear()

