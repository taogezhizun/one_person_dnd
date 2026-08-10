from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from one_person_dnd.db import init_db
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.localization import LocaleMiddleware, locale_for
from one_person_dnd.web.security import UnsafeWriteProtectionMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="one_person_dnd")
    app.add_middleware(UnsafeWriteProtectionMiddleware)
    app.add_middleware(LocaleMiddleware)
    # FastAPI Form(...) depends on python-multipart (import name: multipart).
    # If missing, routes registration will crash at import time; so we fail gracefully.
    if importlib.util.find_spec("multipart") is None:
        @app.get("/", response_class=HTMLResponse)
        def _missing_multipart(request: Request) -> HTMLResponse:
            ui = locale_for(request)
            return HTMLResponse(
                f"""
                <html><head><meta charset="utf-8"><title>one_person_dnd</title></head>
                <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; padding: 24px;">
                  <h2>{ui("errors.missing_dependency_title")}</h2>
                  <p>{ui("errors.missing_dependency_body")}</p>
                  <p>{ui("errors.missing_dependency_install")}:</p>
                  <pre>pip install -r requirements.txt</pre>
                  <p>{ui("errors.missing_dependency_restart")}: <code>python -m one_person_dnd</code></p>
                </body></html>
                """.strip()
            )

        return app

    paths = ensure_app_dirs()
    init_db(paths.db_path)
    # Delay import to avoid crashing when optional deps are missing.
    from one_person_dnd.web.routes import router

    app.include_router(router)
    web_dir = Path(__file__).resolve().parent
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")
    return app
