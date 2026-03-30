"""
Compatibility wrapper.

The app has been reorganized into the `backend/` package.
Keep this module so existing commands like `uvicorn app.main:app` keep working.
"""

from backend.main import app  # noqa: F401
