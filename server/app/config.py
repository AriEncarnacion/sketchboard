"""Runtime config. Everything comes from the environment so the systemd unit
and local dev can differ without code changes."""

import os

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:26b")

# Draft + up to this many critique/revise passes.
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "2"))

# Render drafts with headless Chromium and feed the screenshot back to Gemma.
# Off = single-shot draft, no visual critique. Useful when Chromium isn't installed.
RENDER_ENABLED = os.environ.get("RENDER_ENABLED", "1") == "1"

# iPad Pro 11" landscape, in CSS px. The app renders the HTML at this size.
VIEWPORT_W = int(os.environ.get("VIEWPORT_W", "1180"))
VIEWPORT_H = int(os.environ.get("VIEWPORT_H", "820"))

MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "6000"))

# Gemma 4 reasoning: "none" (default, fast) or "low"/"medium"/"high". Thinking tokens
# count against MAX_TOKENS, so anything but "none" needs a much bigger budget.
REASONING = os.environ.get("REASONING", "none")
REQUEST_TIMEOUT_S = float(os.environ.get("REQUEST_TIMEOUT_S", "600"))

# Sessions persist as JSON files here so they survive restarts. Empty = memory only.
SESSIONS_DIR = os.environ.get("SESSIONS_DIR", "./sessions")

# Public viewer links (/m/{id}?t=sig) for sharing a mockup, e.g. from the Slack bot.
# PUBLIC_BASE_URL is what a browser can reach, e.g. http://1.2.3.4:8080. Empty = no links.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
VIEWER_SECRET = os.environ.get("VIEWER_SECRET", "dev-only-not-secret")

# Nango (nango.dev) brokers "Sign in with GitHub". Empty key = auth endpoints return 503.
NANGO_SECRET_KEY = os.environ.get("NANGO_SECRET_KEY", "")
NANGO_INTEGRATION_ID = os.environ.get("NANGO_INTEGRATION_ID", "github")
