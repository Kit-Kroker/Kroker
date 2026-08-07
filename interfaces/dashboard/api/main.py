# interfaces/dashboard/api/main.py
"""uvicorn entrypoint. All logic is in sdlc.board.api — this file exists so
the service can be started without the package layout mattering.

    uvicorn interfaces.dashboard.api.main:app --port 8500
"""
from sdlc.board.api import app

__all__ = ["app"]
