"""HTTP API for the accounting module (FastAPI). Auth is out of scope."""

from accounting.api.app import create_app

__all__ = ["create_app"]
