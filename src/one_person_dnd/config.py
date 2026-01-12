from __future__ import annotations

import configparser
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0
    provider: str = "openai_compat"


@dataclass(frozen=True)
class AppState:
    active_campaign_id: int | None = None
    active_session_id: int | None = None


@dataclass(frozen=True)
class MemoryConfig:
    """
    Optional memory-related knobs. If missing from api_config.ini, defaults are used.
    """

    history_turns_for_prompt: int = 6
    story_journal_for_prompt: int = 12


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True


def _read_config(config_path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    if config_path.exists():
        cp.read(config_path, encoding="utf-8")
    return cp


def load_llm_config(config_path: Path) -> LLMConfig | None:
    cp = _read_config(config_path)
    if "llm" not in cp:
        return None

    sec = cp["llm"]
    provider = (sec.get("provider") or "openai_compat").strip() or "openai_compat"
    base_url = (sec.get("base_url") or "").strip()
    api_key = (sec.get("api_key") or "").strip()
    model = (sec.get("model") or "").strip()
    timeout_seconds = float((sec.get("timeout_seconds") or "60").strip())

    # api_key may be empty for local/self-hosted OpenAI-compatible servers.
    if not base_url or not model:
        return None

    return LLMConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def save_llm_config(config_path: Path, cfg: LLMConfig) -> None:
    cp = _read_config(config_path)
    cp["llm"] = {
        "provider": (cfg.provider or "openai_compat").strip(),
        "base_url": cfg.base_url.strip(),
        "api_key": cfg.api_key.strip(),
        "model": cfg.model.strip(),
        "timeout_seconds": str(cfg.timeout_seconds),
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        cp.write(f)


def load_app_state(config_path: Path) -> AppState:
    cp = _read_config(config_path)
    if "app" not in cp:
        return AppState()
    sec = cp["app"]
    try:
        cid = sec.get("active_campaign_id")
        sid = sec.get("active_session_id")
        return AppState(
            active_campaign_id=int(cid) if cid else None,
            active_session_id=int(sid) if sid else None,
        )
    except Exception:
        return AppState()


def save_app_state(config_path: Path, state: AppState) -> None:
    cp = _read_config(config_path)
    cp["app"] = {
        "active_campaign_id": "" if state.active_campaign_id is None else str(state.active_campaign_id),
        "active_session_id": "" if state.active_session_id is None else str(state.active_session_id),
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        cp.write(f)


def load_memory_config(config_path: Path) -> MemoryConfig:
    cp = _read_config(config_path)
    if "memory" not in cp:
        return MemoryConfig()

    sec = cp["memory"]
    defaults = MemoryConfig()

    def _read_int(key: str, default: int) -> int:
        raw = (sec.get(key) or "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except Exception:
            return default

    return MemoryConfig(
        history_turns_for_prompt=_read_int("history_turns_for_prompt", defaults.history_turns_for_prompt),
        story_journal_for_prompt=_read_int("story_journal_for_prompt", defaults.story_journal_for_prompt),
    )


def load_server_config(config_path: Path) -> ServerConfig:
    cp = _read_config(config_path)
    if "server" not in cp:
        return ServerConfig()
    sec = cp["server"]
    host = (sec.get("host") or "").strip() or "127.0.0.1"
    try:
        port = int((sec.get("port") or "8000").strip())
    except Exception:
        port = 8000
    open_browser_raw = (sec.get("open_browser") or "true").strip().lower()
    open_browser = open_browser_raw not in ("0", "false", "no", "off")
    return ServerConfig(host=host, port=port, open_browser=open_browser)


def save_server_config(config_path: Path, cfg: ServerConfig) -> None:
    cp = _read_config(config_path)
    cp["server"] = {
        "host": cfg.host,
        "port": str(cfg.port),
        "open_browser": "true" if cfg.open_browser else "false",
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        cp.write(f)


def interactive_ensure_llm_config(config_path: Path) -> LLMConfig | None:
    """
    If LLM config is missing, prompt user in CLI and save to config file.
    Returns LLMConfig if available, else None.
    """
    existing = load_llm_config(config_path)
    if existing is not None:
        return existing

    print("检测到尚未配置 LLM（将写入 api_config.ini 的 [llm]）。")
    yn = input("现在配置 LLM 吗？[Y/n] ").strip().lower()
    if yn in ("n", "no"):
        print("已跳过 LLM 配置。你也可以稍后在网页 /setup 配置。")
        return None

    base_url = input("Base URL（例如 https://api.example.com/v1）：").strip()
    model = input("Model（例如 gpt-4o-mini / deepseek-chat）：").strip()
    api_key = getpass("API Key（输入不回显）：").strip()
    timeout_raw = input("Timeout Seconds（默认 60）：").strip()
    timeout_seconds = 60.0
    if timeout_raw:
        try:
            timeout_seconds = float(timeout_raw)
        except Exception:
            timeout_seconds = 60.0

    if not base_url or not model or not api_key:
        print("LLM 配置不完整，已跳过保存。你也可以稍后在网页 /setup 配置。")
        return None

    cfg = LLMConfig(
        provider="openai_compat",
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    save_llm_config(config_path, cfg)
    print("LLM 配置已保存。")
    return cfg


def interactive_ensure_server_config(config_path: Path) -> ServerConfig:
    """
    If server section missing, prompt user in CLI and save defaults/overrides.
    Always returns a ServerConfig.
    """
    cp = _read_config(config_path)
    if "server" in cp:
        return load_server_config(config_path)

    print("未找到 [server] 配置，将写入默认启动配置。")
    host = input("Host（默认 127.0.0.1）：").strip() or "127.0.0.1"
    port_raw = input("Port（默认 8000）：").strip()
    port = 8000
    if port_raw:
        try:
            port = int(port_raw)
        except Exception:
            port = 8000
    ob_raw = input("启动后自动打开浏览器？[Y/n] ").strip().lower()
    open_browser = ob_raw not in ("n", "no", "0", "false", "off")

    cfg = ServerConfig(host=host, port=port, open_browser=open_browser)
    save_server_config(config_path, cfg)
    print("server 配置已保存。")
    return cfg

