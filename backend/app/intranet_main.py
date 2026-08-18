"""Intranet platform ASGI entrypoint.

Run with: uvicorn app.intranet_main:app --port 8001
"""

from .app_factory import create_intranet_app

app = create_intranet_app()
