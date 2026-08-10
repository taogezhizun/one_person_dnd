from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.config import LLMConfig
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import app_settings, llm_profiles
from one_person_dnd.llm import ChatMessage, LLMClientError, create_llm_client
from one_person_dnd.llm.providers import apply_provider_defaults, list_provider_presets
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.localization import locale_for
from one_person_dnd.web.routes.common import ACTIVE_LLM_PROFILE_KEY, ensure_default_llm_profile_from_ini, templates

router = APIRouter()


@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request, created: int = 0) -> HTMLResponse:
    ui = locale_for(request)
    ensure_default_llm_profile_from_ini()
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        profiles = llm_profiles.list_profiles(conn)
        active_id = app_settings.get(conn, ACTIVE_LLM_PROFILE_KEY)
    finally:
        conn.close()

    preset_label_keys = {
        "openai_compat": "models.provider.openai_compat",
        "deepseek": "models.provider.deepseek",
    }
    provider_presets = []
    for preset in list_provider_presets():
        label_key = preset_label_keys.get(preset.id)
        provider_presets.append(
            replace(preset, label=ui(label_key) if label_key else preset.label)
        )

    return templates.TemplateResponse(
        request=request,
        name="models.html",
        context={
            "profiles": profiles,
            "active_id": int(active_id) if active_id and active_id.isdigit() else None,
            "provider_presets": provider_presets,
            "created": int(created) == 1,
        },
    )


@router.post("/models/set_active")
def models_set_active(profile_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        row = llm_profiles.get_profile(conn, int(profile_id))
        if row:
            app_settings.set(conn, ACTIVE_LLM_PROFILE_KEY, str(int(profile_id)))
            conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/models", status_code=303)


@router.post("/models/create")
def models_create(
    name: str = Form(...),
    provider: str = Form("openai_compat"),
    base_url: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(...),
    timeout_seconds: float = Form(60.0),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        cfg = apply_provider_defaults(
            LLMConfig(
                provider=(provider or "openai_compat").strip(),
                base_url=base_url.strip(),
                api_key=(api_key or "").strip(),
                model=model.strip(),
                timeout_seconds=float(timeout_seconds),
            )
        )
        pid = llm_profiles.create_profile(
            conn,
            name=name.strip(),
            provider=cfg.provider,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            timeout_seconds=cfg.timeout_seconds,
        )
        # if no active yet, set this
        if not app_settings.get(conn, ACTIVE_LLM_PROFILE_KEY):
            app_settings.set(conn, ACTIVE_LLM_PROFILE_KEY, str(pid))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/models?created=1", status_code=303)


@router.post("/models/update")
def models_update(
    profile_id: int = Form(...),
    name: str = Form(...),
    provider: str = Form("openai_compat"),
    base_url: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(...),
    timeout_seconds: float = Form(60.0),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        existing = llm_profiles.get_profile(conn, int(profile_id)) or {}
        next_api_key = (api_key or "").strip() or (existing.get("api_key") or "")
        cfg = apply_provider_defaults(
            LLMConfig(
                provider=(provider or "openai_compat").strip(),
                base_url=base_url.strip(),
                api_key=next_api_key,
                model=model.strip(),
                timeout_seconds=float(timeout_seconds),
            )
        )
        llm_profiles.update_profile(
            conn,
            profile_id=int(profile_id),
            name=name.strip(),
            provider=cfg.provider,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            timeout_seconds=cfg.timeout_seconds,
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/models", status_code=303)


@router.post("/models/delete")
def models_delete(profile_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        active_id = app_settings.get(conn, ACTIVE_LLM_PROFILE_KEY)
        llm_profiles.delete_profile(conn, int(profile_id))
        if active_id and active_id.isdigit() and int(active_id) == int(profile_id):
            app_settings.set(conn, ACTIVE_LLM_PROFILE_KEY, "")
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/models", status_code=303)


@router.post("/models/test", response_class=HTMLResponse)
def models_test(
    request: Request,
    profile_id: int = Form(...),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        row = llm_profiles.get_profile(conn, int(profile_id))
    finally:
        conn.close()

    if not row:
        ui = locale_for(request)
        return templates.TemplateResponse(
            request=request,
            name="partials/test_result.html",
            context={"ok": False, "message": ui("models.error.profile_not_found")},
        )

    cfg = LLMConfig(
        provider=(row.get("provider") or "openai_compat"),
        base_url=(row.get("base_url") or ""),
        api_key=(row.get("api_key") or ""),
        model=(row.get("model") or ""),
        timeout_seconds=float(row.get("timeout_seconds") or 60.0),
    )
    try:
        client = create_llm_client(cfg)
        resp = client.chat(
            [
                ChatMessage(role="system", content="你是一个连通性测试助手。只回答 OK。"),
                ChatMessage(role="user", content="test"),
            ]
        )
        ok = True
        message = (resp or "").strip() or "OK"
    except LLMClientError as e:
        ok = False
        message = str(e)

    return templates.TemplateResponse(
        request=request,
        name="partials/test_result.html",
        context={"ok": ok, "message": message},
    )
