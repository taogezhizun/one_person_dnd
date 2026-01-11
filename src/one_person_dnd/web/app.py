from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from one_person_dnd.db import init_db
from one_person_dnd.paths import ensure_app_dirs


def create_app() -> FastAPI:
    # FastAPI Form(...) depends on python-multipart (import name: multipart).
    # If missing, routes registration will crash at import time; so we fail gracefully.
    if importlib.util.find_spec("multipart") is None:
        app = FastAPI(title="one_person_dnd")

        @app.get("/", response_class=HTMLResponse)
        def _missing_multipart() -> HTMLResponse:
            return HTMLResponse(
                """
                <html><head><meta charset="utf-8"><title>one_person_dnd</title></head>
                <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; padding: 24px;">
                  <h2>依赖缺失：python-multipart</h2>
                  <p>本项目使用 FastAPI 表单（Form），需要安装 <code>python-multipart</code>。</p>
                  <pre>pip install -r requirements.txt</pre>
                  <p>安装完成后请重新启动：<code>python -m one_person_dnd</code></p>
                </body></html>
                """.strip()
            )

        return app

    paths = ensure_app_dirs()
    init_db(paths.db_path)
    app = FastAPI(title="one_person_dnd")
    # Delay import to avoid crashing when optional deps are missing.
    from one_person_dnd.web.routes import router

    app.include_router(router)
    web_dir = Path(__file__).resolve().parent
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")
    return app

