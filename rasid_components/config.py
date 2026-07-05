# RASID Configuration
# Centralized configuration for API and app URLs

# API Base URL (with /api/ suffix)
API_BASE_URL = "https://api.rasid.ai/api/"

# App Base URL (without trailing slash)
APP_BASE_URL = "https://app.rasid.ai"

# API Host (for image loader and other direct API calls)
API_HOST = "https://api.rasid.ai"

# GoPilot LLM Base URL
GOPILOT_LLM_BASE_URL = "https://api.rasid.ai/api/llm/"

# Request timeout in seconds
REQUEST_TIMEOUT = 15

# Debug mode (keep False for released/deployed builds — when True, debug_print
# logs LLM message content, session IDs, URLs and request payloads to the log)
DEBUG = True