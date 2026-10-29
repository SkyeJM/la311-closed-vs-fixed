"""Vercel entrypoint for the API service.

The app is api/app.py at the repo root. build.py copies it and the rest of the runtime code
into this directory during the Vercel build, because a service bundles only its own root.
"""

from api.app import app  # noqa: F401
