from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

from one_person_dnd.config import (
    interactive_ensure_llm_config,
    interactive_ensure_server_config,
    load_server_config,
)
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.app import create_app


def _open_browser_later(url: str, delay_seconds: float = 0.8) -> None:
    def _run() -> None:
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception:
            # best-effort only
            pass

    threading.Thread(target=_run, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="one_person_dnd", description="One Person DND Web App")
    # CLI 参数仅作为“覆盖配置文件”的手段；默认以 api_config.ini 为准
    parser.add_argument("--host", default=None, help="覆盖配置文件中的 server.host")
    parser.add_argument("--port", default=None, type=int, help="覆盖配置文件中的 server.port")
    parser.add_argument("--no-browser", action="store_true", help="覆盖配置文件：不自动打开浏览器")
    args = parser.parse_args(argv)

    paths = ensure_app_dirs()
    # 1) server 配置：缺失则提示输入并写回配置文件
    interactive_ensure_server_config(paths.config_path)
    server_cfg = load_server_config(paths.config_path)

    host = (args.host or server_cfg.host).strip()
    port = int(args.port) if args.port is not None else int(server_cfg.port)
    open_browser = server_cfg.open_browser and (not args.no_browser)

    # 2) llm 配置：缺失则提示输入（允许跳过）
    interactive_ensure_llm_config(paths.config_path)

    app = create_app()
    url = f"http://{host}:{port}"
    if open_browser:
        _open_browser_later(url)

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

