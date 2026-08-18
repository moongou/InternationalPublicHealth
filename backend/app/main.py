"""Internet platform ASGI entrypoint.

Run with: uvicorn app.main:app --port 8000
"""

from .app_factory import create_internet_app

app = create_internet_app()
