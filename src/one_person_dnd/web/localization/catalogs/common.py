"""Shared application chrome messages.

Each value is ``(zh-CN, en)``.  Keeping both translations beside the stable
semantic key makes placeholder parity reviewable in one place.
"""

MESSAGES: dict[str, tuple[str, str]] = {
    "app.skip_to_main": ("跳到主要内容", "Skip to main content"),
    "nav.primary": ("主要导航", "Primary navigation"),
    "nav.play": ("游玩", "Play"),
    "nav.new_adventure": ("新冒险", "New Adventure"),
    "nav.adventures": ("冒险", "Adventures"),
    "nav.world": ("世界", "World"),
    "nav.plot_threads": ("剧情线", "Plot Threads"),
    "nav.models": ("模型", "Models"),
    "locale.switch_to_english": ("English", "English"),
    "locale.switch_to_chinese": ("中文", "中文"),
    "locale.switch_aria": ("切换界面语言为 {language}", "Switch interface language to {language}"),
    "common.pending_changes_count": ("{count} 条待确认变更", "{count} pending changes"),
    "errors.unsupported_locale": ("不支持该界面语言。", "That interface language is not supported."),
    "errors.cross_site_write": ("已拒绝跨站写入请求。", "Cross-site write request rejected."),
    "errors.missing_dependency_title": ("依赖缺失：python-multipart", "Missing dependency: python-multipart"),
    "errors.missing_dependency_body": (
        "本项目使用 FastAPI 表单（Form），需要安装 python-multipart。",
        "This app uses FastAPI forms and requires python-multipart.",
    ),
    "errors.missing_dependency_install": ("安装", "Install"),
    "errors.missing_dependency_restart": ("安装完成后请重新启动", "Restart the app after installation"),
}
