"""Same-origin SPA static serving (T11.1).

Serves the built web bundle from FastAPI so one origin serves both the app and the
API — which is why the deployment needs no CORS. ``SpaStaticFiles`` falls back to
``index.html`` on a 404 so client-side routes (e.g. ``/finance``) work on refresh.
Mounted at ``/`` **after** all API routers, so API routes always win. See
``specs/domain/platform/deployment.md``.
"""

from typing import Any

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class SpaStaticFiles(StaticFiles):
    """Static files with single-page-app history fallback to ``index.html``."""

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
