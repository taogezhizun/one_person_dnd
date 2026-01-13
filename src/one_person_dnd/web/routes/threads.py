from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import plot_threads
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()


@router.get("/threads", response_class=HTMLResponse)
def threads_page(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        open_threads = plot_threads.list_threads(conn, session_id=session_id, status="open", limit=200)
        closed_threads = plot_threads.list_threads(conn, session_id=session_id, status="closed", limit=200)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="threads.html",
        context={"session_id": session_id, "open_threads": open_threads, "closed_threads": closed_threads},
    )


@router.post("/threads/new")
def thread_create(
    title: str = Form(...),
    priority: int = Form(0),
    summary: str = Form(""),
    next_step: str = Form(""),
    tags: str = Form(""),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        plot_threads.create_thread(
            conn,
            session_id=session_id,
            title=title.strip(),
            priority=int(priority),
            summary=(summary or "").strip(),
            next_step=(next_step or "").strip(),
            tags=(tags or "").strip(),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/threads", status_code=303)


@router.post("/threads/update")
def thread_update(
    thread_id: int = Form(...),
    title: str = Form(...),
    priority: int = Form(0),
    summary: str = Form(""),
    next_step: str = Form(""),
    tags: str = Form(""),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        plot_threads.update_thread(
            conn,
            thread_id=int(thread_id),
            session_id=session_id,
            title=title.strip(),
            priority=int(priority),
            summary=(summary or "").strip(),
            next_step=(next_step or "").strip(),
            tags=(tags or "").strip(),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/threads", status_code=303)


@router.post("/threads/close")
def thread_close(thread_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        plot_threads.set_status(conn, thread_id=int(thread_id), session_id=session_id, status="closed")
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/threads", status_code=303)


@router.post("/threads/reopen")
def thread_reopen(thread_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        plot_threads.set_status(conn, thread_id=int(thread_id), session_id=session_id, status="open")
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/threads", status_code=303)

