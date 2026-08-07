"""
Vercel serverless entry point.

Vercel's Python runtime imports this module and looks for a WSGI/ASGI callable
named ``app``. Everything else - routing, static files, sessions - is handled by
Django exactly as it is when running locally.

The parent directory is put on ``sys.path`` explicitly because the function is
not necessarily invoked with the project root as the working directory.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.vercel")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()

# Vercel's Python builder looks for this name.
app = application
