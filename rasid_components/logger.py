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
    """Print debug messages only if DEBUG is True"""
    if DEBUG:
        message = ' '.join(str(arg) for arg in args)
        print(f"[qgis_gopilot] DEBUG: {message}")