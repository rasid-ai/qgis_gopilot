import logging
from .config import DEBUG 

# Create logger for the plugin
logger = logging.getLogger('qgis_gopilot')
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(name)s] %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

def debug_print(*args, **kwargs):
    """Write debug messages to QGIS' Log Messages panel when enabled."""
    if DEBUG:
        message = ' '.join(str(arg) for arg in args)
        try:
            from qgis.core import QgsMessageLog, Qgis

            # QGIS 3 exposes Info directly; newer scoped-enum builds expose it
            # through MessageLevel. Support both while the plugin targets QGIS
            # 3.x and 4.x.
            info_level = getattr(Qgis, 'Info', None)
            if info_level is None:
                info_level = Qgis.MessageLevel.Info

            QgsMessageLog.logMessage(message, 'GoPilot', level=info_level)
        except Exception:
            # Keep debug output usable in tests and command-line environments
            # where the QGIS logging API is unavailable.
            print(f"[qgis_gopilot] DEBUG: {message}")
