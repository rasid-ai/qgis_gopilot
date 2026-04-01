"""Shared async image loader that uses the authenticated session."""
import hashlib
import os

from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QThread, pyqtSignal

BASE_URL = "https://api.rasid.ai"

# Disk cache directory inside the plugin folder
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".image_cache")


def _cache_path(url):
    """Return a filesystem path for the cached version of *url*."""
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    ext = os.path.splitext(url.split("?")[0])[1] or ".img"
    return os.path.join(_CACHE_DIR, url_hash + ext)


def _read_cache(url):
    """Return cached bytes or None."""
    path = _cache_path(url)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def _write_cache(url, data):
    """Persist *data* to disk for *url*."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    with open(path, "wb") as f:
        f.write(data)


def resolve_url(url):
    """Turn a relative /media/... path into a full URL."""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    # Relative path — prepend base
    if url.startswith("/"):
        return BASE_URL + url
    return BASE_URL + "/" + url


class FetchImageThread(QThread):
    finished = pyqtSignal(QLabel, bytes)

    def __init__(self, session, url, label):
        super().__init__()
        self.session = session
        self.url = resolve_url(url)
        self.label = label

    def run(self):
        if not self.url:
            return
        try:
            # Check disk cache first
            cached = _read_cache(self.url)
            if cached:
                self.finished.emit(self.label, cached)
                return
            # Download and cache
            r = self.session.get(self.url, timeout=15)
            if r.status_code == 200 and r.content:
                _write_cache(self.url, r.content)
                self.finished.emit(self.label, r.content)
        except Exception:
            pass


def load_image(client, url, label, threads_list, size=None):
    """Start an async image load into a QLabel.

    Args:
        client: RasidClient with authenticated session
        url: image URL (absolute or relative)
        label: target QLabel
        threads_list: list to keep thread references alive
        size: optional (w, h) tuple to scale the result
    """
    resolved = resolve_url(url)
    if not resolved:
        return

    def on_loaded(lbl, data):
        pm = QPixmap()
        pm.loadFromData(data)
        if size:
            pm = pm.scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pm = pm.scaled(lbl.width(), lbl.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lbl.setPixmap(pm)

    t = FetchImageThread(client.session, url, label)
    t.finished.connect(on_loaded)
    threads_list.append(t)
    t.start()
