"""Vercel Flask entrypoint.

Vercel's current Python/Flask runtime auto-detects a top-level WSGI
application named ``app`` in supported files such as ``app.py``.  Keep the
serverless deployment pointed at the same hosted GreenIndex dashboard used by
``api/index.py`` while avoiding custom catch-all routing rules.
"""

from greenindex.web.app import create_app

# Hosted mode: no user filesystem access, inline CSS for a self-contained page.
app = create_app({"HOSTED": True, "INLINE_CSS": True})

# Alias for WSGI servers that look for ``application`` instead of ``app``.
application = app
