from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.config import LLMConfig, load_llm_config, save_llm_config
from one_person_dnd.llm import ChatMessage, LLMClientError, create_llm_client
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import templates

router = APIRouter()


@router.get("/setup", response_class=HTMLResponse)
def setup_get(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_llm_config(paths.config_path)
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={
            "existing": llm_cfg,
        },
    )


@router.post("/setup")
def setup_post(
    base_url: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(...),
    timeout_seconds: float = Form(60.0),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    save_llm_config(
        paths.config_path,
        LLMConfig(
            base_url=base_url.strip(),
            api_key=api_key.strip(),
            model=model.strip(),
            timeout_seconds=timeout_seconds,
        ),
    )
    return RedirectResponse(url="/", status_code=303)


@router.post("/setup/test", response_class=HTMLResponse)
def setup_test(
    request: Request,
    base_url: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(...),
    timeout_seconds: float = Form(60.0),
) -> HTMLResponse:
    cfg = LLMConfig(
        base_url=base_url.strip(),
        api_key=api_key.strip(),
        model=model.strip(),
        timeout_seconds=timeout_seconds,
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

