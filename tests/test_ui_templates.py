from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from jinja2 import Environment, FileSystemLoader

from one_person_dnd.web.labels import localized_label_maps, register_jinja_globals
from one_person_dnd.web.localization import Localizer


def _template_environment(locale: str = "zh-CN") -> Environment:
    env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
    register_jinja_globals(env)
    if locale == "en":
        ui = Localizer("en")
        labels = localized_label_maps(ui)
        env.globals.update(
            t=ui,
            html_lang=ui.html_lang,
            other_locale="zh-CN",
            other_locale_label="中文",
            client_catalog=ui.client_catalog(),
            label_maps=labels,
            action_type_labels=labels["action_type"],
            action_signal_labels=labels["action_signal"],
            action_warning_labels=labels["action_warning"],
            critic_warning_labels=labels["critic_warning"],
            response_warning_labels=labels["response_warning"],
            adjudication_intent_labels=labels["adjudication_intent"],
        )
    return env


class TestUITemplates(unittest.TestCase):
    def test_primary_nav_is_play_first(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        for href, key in (
            ('href="/game"', "nav.play"),
            ('href="/new"', "nav.new_adventure"),
            ('href="/saves"', "nav.adventures"),
            ('href="/memory/world"', "nav.world"),
            ('href="/threads"', "nav.plot_threads"),
            ('href="/models"', "nav.models"),
        ):
            self.assertIn(href, base)
            self.assertIn(key, base)
        self.assertNotIn('href="/setup">配置', base)

        english = _template_environment("en").get_template("base.html").render()
        self.assertIn('<html lang="en">', english)
        for label in ("Play", "New Adventure", "Adventures", "World", "Plot Threads", "Models"):
            self.assertIn(f">{label}</a>", english)

    def test_header_distributes_brand_navigation_and_locale_across_viewport(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        header = base.split('<header class="header">', 1)[1].split("</header>", 1)[0]
        primary_nav = header.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("header__nav-row", header)
        self.assertNotIn("locale-switch", primary_nav)
        self.assertLess(header.index('class="brand"'), header.index('<nav class="nav"'))
        self.assertLess(header.index("</nav>"), header.index('<form class="locale-switch"'))

        def declarations(selector: str, source: str = css) -> str:
            match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", source)
            self.assertIsNotNone(match, f"missing CSS rule: {selector}")
            return match.group(1)

        header_rule = declarations(".header__inner")
        self.assertIn("display: grid;", header_rule)
        self.assertIn(
            "grid-template-columns: minmax(12rem, 1fr) minmax(0, max-content) minmax(12rem, 1fr);",
            header_rule,
        )
        self.assertIn("max-width: none;", header_rule)
        self.assertIn("width: 100%;", header_rule)

        nav_rule = declarations(".nav")
        self.assertIn("justify-self: center;", nav_rule)

        utility_rule = declarations(".locale-switch")
        self.assertIn("flex: 0 0 auto;", utility_rule)
        self.assertIn("justify-self: end;", utility_rule)

        nav_item_rule = declarations(".nav a,\n.nav__locale")
        self.assertIn("min-height: 40px;", nav_item_rule)
        self.assertIn("white-space: nowrap;", nav_item_rule)

        self.assertIn("@media (max-width: 1023px) {", css)
        transition_header = css.split("@media (max-width: 1023px) {", 1)[1].split(
            "@media (max-width: 980px) {", 1
        )[0]
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr) auto;",
            declarations(".header__inner", transition_header),
        )
        compact_nav = declarations(".nav", transition_header)
        self.assertIn("grid-column: 1 / -1;", compact_nav)
        self.assertIn("width: 100%;", compact_nav)
        self.assertIn("overflow-x: auto;", compact_nav)

    def test_base_uses_local_vendored_scripts(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        for src in (
            '<script src="/static/vendor/htmx.min.js"></script>',
            '<script src="/static/vendor/marked.min.js"></script>',
            '<script src="/static/vendor/purify.min.js"></script>',
        ):
            self.assertIn(src, base)
        self.assertNotIn("unpkg.com", base)
        self.assertIn('<script src="/static/js/turn_stream_state.js"></script>', base)
        self.assertLess(base.index("turn_stream_state.js"), base.index("/static/js/app.js"))

    def test_base_locks_htmx_to_same_origin_without_dynamic_code(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('name="htmx-config"', base)
        self.assertIn('"selfRequestsOnly":true', base)
        self.assertIn('"allowScriptTags":false', base)
        self.assertIn('"allowEval":false', base)

    def test_home_model_setup_cta_points_to_models(self) -> None:
        index = Path("src/one_person_dnd/web/templates/index.html").read_text(encoding="utf-8")

        self.assertIn('href="/models"', index)
        self.assertIn("home.configure_model", index)
        self.assertNotIn('href="/setup">去配置', index)

    def test_home_prioritizes_continuing_before_creating_new_adventure(self) -> None:
        index = Path("src/one_person_dnd/web/templates/index.html").read_text(encoding="utf-8")

        self.assertIn("home.create_new", index)
        self.assertIn("home.continue_adventure", index)
        self.assertLess(index.index('href="/game"'), index.index('href="/new"'))
        self.assertLess(index.index('href="/game"'), index.index('href="/saves"'))

        english = _template_environment("en").get_template("index.html").render(
            campaign_name="Player Save Name",
            session_title="Player Chapter",
            current_scene="Player Scene",
            latest_story="Player Story",
            last_played_at="",
            character=None,
            llm_configured=False,
        )
        self.assertIn("Continue this adventure", english)
        self.assertIn("Create a new adventure", english)
        self.assertIn("Player Save Name", english)

    def test_new_adventure_generation_shows_long_submit_state(self) -> None:
        new = Path("src/one_person_dnd/web/templates/new.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("new-adventure__notice-actions", new)
        self.assertIn("new.model_not_ready.cta", new)
        self.assertIn(".new-adventure__notice-actions", css)
        self.assertIn('data-long-submit', new)
        self.assertIn("new.action.generating", new)
        self.assertIn('formaction="/new/propose"', new)
        self.assertIn("new.action.propose", new)
        self.assertIn('data-long-submit-button', new)
        self.assertIn('data-long-submit-status', new)
        self.assertIn("new.action.waiting", new)
        self.assertIn("function initLongSubmitForms()", app_js)
        self.assertIn('querySelectorAll("[data-long-submit]")', app_js)
        self.assertIn('querySelector("[data-long-submit-button]")', app_js)
        self.assertIn('querySelector("[data-long-submit-status]")', app_js)
        self.assertIn("button.disabled = true;", app_js)
        self.assertIn("status.hidden = false;", app_js)
        self.assertIn("initLongSubmitForms();", app_js)
        self.assertIn(".form-status", css)

        english = _template_environment("en").get_template("new.html").render(
            form_values={
                "adventure_brief": "Player brief",
                "genre": "",
                "tone": "",
                "tech_level": "",
                "themes": "",
                "character_count": 1,
                "extra_constraints": "Player constraints",
            },
            llm_ready=False,
            error="",
        )
        self.assertIn("Create a new adventure", english)
        self.assertIn("The model is not ready", english)
        self.assertIn("Player brief", english)

    def test_turn_form_persists_attempt_identity_until_success(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('name="attempt_id"', game)
        self.assertIn("function ensureTurnAttempt(form)", app_js)
        self.assertIn("function initTurnAttemptPersistence()", app_js)
        self.assertIn("TURN_ATTEMPT_STORAGE_PREFIX", app_js)
        self.assertIn("ensureTurnAttempt(form);", app_js)
        self.assertIn("clearTurnAttempt(form);", app_js)
        self.assertIn('getResponseHeader("X-Turn-Accepted")', app_js)
        self.assertIn('turnAccepted === "0"', app_js)

    def test_new_adventure_preview_summarizes_generated_content(self) -> None:
        template = Path("src/one_person_dnd/web/templates/new_preview.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("new-preview-summary", template)
        self.assertIn("new-preview-summary__grid", template)
        self.assertIn("new.preview.world_settings", template)
        self.assertIn("new.preview.companions", template)
        self.assertIn("new.preview.opening", template)
        self.assertIn("new.preview.technical", template)
        self.assertIn("new.preview.return_to_edit", template)
        self.assertIn('name="source_form_json"', template)
        self.assertIn('formaction="/new/return"', template)
        self.assertIn('formmethod="post"', template)
        self.assertNotIn('href="/new">返回修改', template)
        self.assertNotIn(">放弃<", template)
        self.assertIn(".new-preview-summary", css)
        self.assertIn(".new-preview-summary__grid", css)
        self.assertIn(".lore-preview-grid", css)

    def test_new_adventure_preview_renders_counts_and_character_json(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("new_preview.html")

        html = template.render(
            preview_obj={
                "adventure_name": "雾港疑云",
                "chapter_title": "第一章·潮声",
                "opening_scene": "雾港码头",
                "world_bible_entries": [
                    {"type": "Location", "title": "雾港", "tags": "港口", "content": "潮湿的旧港。"},
                    {"type": "NPC", "title": "伊莲", "tags": "盟友", "content": "知道密道。"},
                ],
                "character_sheet": {
                    "party": [
                        {
                            "name": "阿洛",
                            "level": 3,
                            "abilities": {"STR": 12, "DEX": 15},
                            "skill_proficiencies": ["Perception", "Stealth"],
                        }
                    ],
                    "notes": "开局在码头",
                },
            },
            preview_json="{}",
            source_form_json='{"form_values":{},"proposal":{}}',
            character_sheet_json='{\n  "party": [\n    {"name": "阿洛"}\n  ]\n}',
        )

        self.assertIn("世界设定", html)
        self.assertIn('class="status-tile__value">2 条</div>', html)
        self.assertIn("你的队伍", html)
        self.assertIn('class="status-tile__value">1 名角色</div>', html)
        self.assertIn("阿洛", html)
        self.assertIn("雾港疑云", html)
        self.assertIn("等级 3", html)
        self.assertIn("STR 12", html)
        self.assertIn("熟练技能：Perception、Stealth", html)

    def test_home_uses_adventure_dashboard_visual_shell(self) -> None:
        index = Path("src/one_person_dnd/web/templates/index.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("home-dashboard", index)
        self.assertIn("home-panel home-panel--primary", index)
        self.assertIn("home.continue.kicker", index)
        self.assertIn("home.continue_adventure", index)
        self.assertIn("home.create_new", index)
        self.assertIn('href="/models"', index)
        self.assertIn("journey-status-card", index)
        self.assertIn(".home-dashboard", css)
        self.assertIn(".home-panel--primary", css)

    def test_base_declares_inline_favicon(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('rel="icon"', base)
        self.assertIn("data:image/svg+xml", base)

    def test_base_versions_css_asset_to_avoid_stale_ui_cache(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('href="/static/style.css?v=', base)
        self.assertNotIn('href="/static/style.css" />', base)

    def test_base_has_skip_link_to_main_content(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('class="skip-link"', base)
        self.assertIn('href="#main-content"', base)
        self.assertLess(base.index('class="skip-link"'), base.index("<header"))
        self.assertIn('<main id="main-content" class="container app-main" tabindex="-1">', base)
        self.assertIn(".skip-link {", css)
        self.assertIn("position: fixed;", css)
        self.assertIn("transform: translateY(-140%);", css)
        self.assertIn(".skip-link:focus-visible {", css)
        self.assertIn("transform: translateY(0);", css)
        self.assertIn(".app-main:focus-visible", css)

    def test_skip_link_explicitly_focuses_main_content(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('data-skip-link', app_js)
        self.assertIn("function initSkipLinks()", app_js)
        self.assertIn('querySelectorAll("[data-skip-link]")', app_js)
        self.assertIn('target.focus({ preventScroll: true });', app_js)
        self.assertIn('target.scrollIntoView({ block: "start" });', app_js)
        self.assertIn("initSkipLinks();", app_js)

    def test_game_sidebar_uses_adventure_panel_sections(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("game.sidebar.title", game)
        self.assertIn("game-status-strip", game)
        self.assertIn("panel-section", game)
        self.assertIn("game.character.title", game)
        self.assertIn("game.world.section", game)
        self.assertIn("game.threads.section", game)
        self.assertIn("game.system.tools", game)
        self.assertIn("game.diagnostics.title", game)

        self.assertLess(game.index('id="character-panel"'), game.index('id="sidebar-form"'))
        self.assertLess(game.index("game.character.title"), game.index("game.world.section"))
        self.assertIn('data-system-tools', game)

        english = _template_environment("en").get_template("game.html").render(
            campaign_id=1,
            session_id=2,
            campaign_name="Player Save Name",
            session_title="Player Chapter",
            current_scene="Player Scene",
            session_state="Player State",
            pinned_world_notes="Player Lore",
            sessions_list=[{"id": 2, "title": "Player Chapter"}],
            pending_count=0,
            cheat_enabled=False,
            cheat_prompt="",
            turns=[],
            open_threads=[],
            world_bible_entries=[],
            world_setup_prompt={"show": False},
            llm_configured=True,
        )
        self.assertIn("Adventure panel", english)
        self.assertIn("Scene and world", english)
        self.assertIn("Player Save Name", english)

    def test_game_sidebar_uses_tabbed_adventure_panel(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("panel-tabs", game)
        self.assertIn('role="tablist"', game)
        for tab_id, key, panel_class in (
            ("panel-tab-character", "game.tabs.character", "panel-tabs__panel--character"),
            ("panel-tab-world", "game.tabs.world", "panel-tabs__panel--world"),
            ("panel-tab-threads", "game.tabs.plot", "panel-tabs__panel--threads"),
            ("panel-tab-system", "game.tabs.system", "panel-tabs__panel--system"),
        ):
            self.assertIn(f'id="{tab_id}"', game)
            self.assertIn(f'for="{tab_id}"', game)
            self.assertIn(key, game)
            self.assertIn(panel_class, game)

        self.assertIn(".panel-tabs__panel {", css)
        self.assertIn("display: none", css)
        self.assertIn("#panel-tab-character:checked", css)
        self.assertIn(".panel-tabs__tab", css)

    def test_game_sidebar_tabs_are_keyboard_accessible(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('role="tablist"', game)
        self.assertIn('role="tab" tabindex="0" aria-selected="true"', game)
        self.assertIn('role="tab" tabindex="-1" aria-selected="false"', game)
        self.assertIn('data-panel-tab="panel-tab-character"', game)
        self.assertIn('aria-controls="panel-character"', game)
        self.assertIn('id="panel-character" role="tabpanel" aria-labelledby="panel-tab-label-character"', game)
        self.assertIn('id="panel-world" role="tabpanel" aria-labelledby="panel-tab-label-world"', game)
        self.assertIn("function initAdventurePanelTabs()", app_js)
        self.assertIn('querySelectorAll("[data-panel-tab]")', app_js)
        self.assertIn('tab.setAttribute("aria-selected", checked ? "true" : "false");', app_js)
        self.assertIn("ArrowRight", app_js)
        self.assertIn("ArrowLeft", app_js)
        self.assertIn("Home", app_js)
        self.assertIn("End", app_js)
        self.assertIn("targetTab.focus();", app_js)
        self.assertIn("initAdventurePanelTabs();", app_js)
        self.assertIn(".panel-tabs__tab:focus-visible", css)

    def test_game_threads_tab_renders_open_plot_threads(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("game.html")

        html = template.render(
            campaign_id=1,
            session_id=2,
            campaign_name="乌鸦港",
            session_title="第一章",
            current_scene="乌鸦酒馆",
            session_state="",
            pinned_world_notes="",
            sessions_list=[{"id": 2, "title": "第一章"}],
            pending_count=0,
            cheat_enabled=False,
            cheat_prompt="",
            turns=[],
            open_threads=[
                {
                    "id": 7,
                    "title": "追踪银钥匙",
                    "priority": 2,
                    "summary": "银钥匙来自旧码头。",
                    "next_step": "询问酒馆老板娘。",
                    "tags": "主线,钥匙",
                }
            ],
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("当前剧情线", html)
        self.assertIn("追踪银钥匙", html)
        self.assertIn("下一步：询问酒馆老板娘。", html)
        self.assertIn("thread-stack", html)
        self.assertIn(".thread-mini", css)

    def test_game_world_tab_renders_world_bible_entries(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("game.html")

        html = template.render(
            campaign_id=1,
            session_id=2,
            campaign_name="星陨边境",
            session_title="第一章",
            current_scene="沉暮酒馆",
            session_state="",
            pinned_world_notes="",
            sessions_list=[{"id": 2, "title": "第一章"}],
            pending_count=0,
            cheat_enabled=False,
            cheat_prompt="",
            turns=[],
            open_threads=[],
            world_bible_entries=[
                {
                    "id": 3,
                    "type": "Location",
                    "title": "灰烬森林",
                    "tags": "森林,危险",
                    "content_preview": "黑灰覆盖的枯死林，中央有一座藤蔓石塔。",
                }
            ],
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("世界设定", html)
        self.assertIn("灰烬森林", html)
        self.assertIn("森林,危险", html)
        self.assertIn("藤蔓石塔", html)
        self.assertIn('href="/memory/world"', html)
        self.assertIn("data-world-bible-summary", html)
        self.assertIn(".world-entry-stack", css)

    def test_game_page_uses_story_first_order_for_existing_turns(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("action-composer", game)
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("game.html")
        common = {
            "campaign_id": 1,
            "session_id": 2,
            "campaign_name": "乌鸦港",
            "session_title": "第一章",
            "current_scene": "乌鸦酒馆",
            "session_state": "",
            "pinned_world_notes": "",
            "sessions_list": [{"id": 2, "title": "第一章"}],
            "pending_count": 0,
            "cheat_enabled": False,
            "cheat_prompt": "",
        }
        existing_story = template.render(
            **common,
            turns=[
                {
                    "turn_index": 0,
                    "player_text": "我推开门",
                    "dm": {"narration": "门开了。", "choices": ["进入"], "dm_notes": "", "memory_suggestions": ""},
                    "dice_events": [],
                }
            ],
        )
        fresh_story = template.render(**common, turns=[])

        self.assertIn("mobile-action-jump", existing_story)
        self.assertIn("data-action-jump", existing_story)
        self.assertLess(existing_story.index("mobile-action-jump"), existing_story.index('id="chat-history"'))
        self.assertNotIn("mobile-action-jump", fresh_story)
        self.assertLess(existing_story.index('id="chat-history"'), existing_story.index('id="turn-form"'))
        self.assertLess(fresh_story.index('id="turn-form"'), fresh_story.index('id="chat-history"'))
        self.assertIn("chat-card--story-first", game)
        self.assertIn(".action-composer", css)
        self.assertIn("position: sticky", css)
        self.assertIn(".chat-card--story-first", css)
        self.assertIn("align-items: flex-start", css)

    def test_game_action_surface_uses_polished_composer_header(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("action-composer__header", game)
        self.assertIn("action-composer__kicker", game)
        self.assertIn("game.composer.title", game)
        self.assertIn("game.composer.action_placeholder", game)
        self.assertIn("game.advanced.context_placeholder", game)
        self.assertIn("game.world.state_placeholder", game)
        self.assertIn("game.world.pinned_placeholder", game)
        self.assertNotIn('placeholder="描述你的行动..."', game)
        self.assertNotIn("一个细节...", game)
        self.assertNotIn("NPC 正在同行", game)
        self.assertNotIn("禁忌...", game)
        self.assertNotIn("快捷键：Ctrl/Cmd + Enter", game)
        self.assertIn(".action-composer__header", css)
        self.assertIn(".action-composer__kicker", css)

    def test_game_action_surface_guides_player_when_dm_is_not_connected(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("game.html")
        common = {
            "campaign_id": 1,
            "session_id": 2,
            "campaign_name": "乌鸦港",
            "session_title": "第一章",
            "current_scene": "乌鸦酒馆",
            "session_state": "",
            "pinned_world_notes": "",
            "sessions_list": [{"id": 2, "title": "第一章"}],
            "pending_count": 0,
            "cheat_enabled": False,
            "cheat_prompt": "",
            "turns": [],
            "open_threads": [],
        }

        blocked = template.render(**common, llm_configured=False)
        ready = template.render(**common, llm_configured=True)
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('data-llm-ready="0"', blocked)
        self.assertIn("DM 尚未连接", blocked)
        self.assertIn('href="/models"', blocked)
        self.assertIn("去配置模型", blocked)
        self.assertIn("action-composer__notice-actions", blocked)
        self.assertIn(".action-composer__notice-actions", css)
        self.assertNotIn("starter-actions", blocked)
        self.assertIn('data-llm-ready="1"', ready)
        self.assertNotIn("DM 尚未连接", ready)
        self.assertIn("starter-actions", ready)
        blocked_submit = re.search(r"<button\b[^>]*data-turn-submit[^>]*>", blocked, re.S)
        ready_submit = re.search(r"<button\b[^>]*data-turn-submit[^>]*>", ready, re.S)
        self.assertIsNotNone(blocked_submit)
        self.assertIsNotNone(ready_submit)
        self.assertIn("disabled", blocked_submit.group(0))
        self.assertIn("disabled", ready_submit.group(0))
        self.assertIn("action-composer__notice", css)
        self.assertIn('dataset.llmReady === "0"', app_js)

    def test_turn_submit_starts_disabled_until_player_enters_action(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        submit_button = re.search(r"<button\b[^>]*data-turn-submit[^>]*>", game, re.S)
        self.assertIsNotNone(submit_button)
        self.assertIn("disabled", submit_button.group(0))
        self.assertIn("const hasText = Boolean(ta && ta.value.trim());", app_js)
        self.assertIn("submitBtn.disabled = loading || !hasText || !llmReady;", app_js)
        self.assertIn('ta.addEventListener("input"', app_js)
        self.assertIn("updateTurnSubmitState(form);", app_js)

    def test_fresh_game_page_offers_clickable_starter_actions(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("game.html")
        common = {
            "campaign_id": 1,
            "session_id": 2,
            "campaign_name": "乌鸦港",
            "session_title": "第一章",
            "current_scene": "乌鸦酒馆",
            "session_state": "",
            "pinned_world_notes": "",
            "sessions_list": [{"id": 2, "title": "第一章"}],
            "pending_count": 0,
            "cheat_enabled": False,
            "cheat_prompt": "",
            "open_threads": [],
            "llm_configured": True,
        }

        fresh_story = template.render(**common, turns=[])
        existing_story = template.render(
            **common,
            turns=[
                {
                    "turn_index": 0,
                    "player_text": "我推开门",
                    "dm": {"narration": "门开了。", "choices": ["进入"], "dm_notes": "", "memory_suggestions": ""},
                    "dice_events": [],
                }
            ],
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("starter-actions", fresh_story)
        self.assertIn("开场行动", fresh_story)
        for text in ("观察四周", "检查随身物品", "和最近的人交谈"):
            self.assertIn(f'data-choice-text="{text}"', fresh_story)
        self.assertIn("data-choice-action", fresh_story)
        self.assertLess(fresh_story.index("starter-actions"), fresh_story.index("quick-roll-panel"))
        self.assertNotIn("starter-actions", existing_story)
        self.assertIn(".starter-actions", css)

    def test_quick_roll_stays_next_to_action_composer(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("game.html")
        common = {
            "campaign_id": 1,
            "session_id": 2,
            "campaign_name": "乌鸦港",
            "session_title": "第一章",
            "current_scene": "乌鸦酒馆",
            "session_state": "",
            "pinned_world_notes": "",
            "sessions_list": [{"id": 2, "title": "第一章"}],
            "pending_count": 0,
            "cheat_enabled": False,
            "cheat_prompt": "",
            "open_threads": [],
        }

        fresh_story = template.render(**common, turns=[])
        existing_story = template.render(
            **common,
            turns=[
                {
                    "turn_index": 0,
                    "player_text": "我推开门",
                    "dm": {"narration": "门开了。", "choices": ["进入"], "dm_notes": "", "memory_suggestions": ""},
                    "dice_events": [],
                }
            ],
        )

        self.assertLess(fresh_story.index('id="turn-form"'), fresh_story.index("quick-roll-panel"))
        self.assertLess(fresh_story.index("quick-roll-panel"), fresh_story.index('id="chat-history"'))
        self.assertLess(existing_story.index('id="chat-history"'), existing_story.index('id="turn-form"'))
        self.assertLess(existing_story.index('id="turn-form"'), existing_story.index("quick-roll-panel"))

    def test_action_and_quick_roll_share_fixed_play_tools_group(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("play-tools", game)
        self.assertIn("play_tools", game)
        self.assertIn(".play-tools", css)
        self.assertIn(
            ".chat-card--story-first {\n"
            "  display: flex;\n"
            "  flex-direction: column;\n"
            "  height: 100%;",
            css,
        )
        self.assertIn("  min-height: 0;", css)
        self.assertIn("overflow: hidden;", css)
        self.assertIn(".chat-card--story-first .chat-history {\n  flex: 1 1 auto;\n  min-height: 0;\n  max-height: none;", css)
        self.assertIn(".chat-card--story-first .play-tools", css)
        self.assertIn(".chat-card--story-first .play-tools {\n  position: static;", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", css)
        self.assertIn(".chat-card--story-first .action-composer {\n  position: static;", css)
        self.assertIn(".chat-card--story-first .action-composer__controls {\n  grid-column: 2;", css)
        self.assertIn(".chat-card--story-first .quick-roll-panel {\n  align-items: center;", css)

    def test_mobile_game_chrome_prioritizes_action_loop_first_viewport(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 520px)", css)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", css)
        self.assertIn(".status-tile__label {\n    display: none;", css)
        self.assertIn(".status-tile__value {\n    font-size: 0.86rem;", css)
        self.assertIn("text-overflow: ellipsis", css)
        self.assertIn(".page-actions [data-sidebar-toggle] {\n    display: none;", css)
        self.assertIn(".action-composer .textarea {\n    min-height: 64px;", css)
        self.assertIn(".quick-roll-panel {\n    margin-top: 8px;", css)
        self.assertIn(".chat-card--story-first .chat-history {\n    min-height: clamp(130px, 18vh, 170px);\n    max-height: min(20vh, 180px);", css)
        self.assertIn(".chat-card--story-first .play-tools {\n    position: static;", css)
        self.assertIn(".chat-card--story-first {\n    padding-bottom: 12px;", css)
        self.assertIn(".chat-card--story-first .action-composer__kicker {\n    display: none;", css)
        self.assertIn(".chat-card--story-first .action-composer__header {\n    margin-bottom: 2px;", css)
        self.assertIn(".chat-card--story-first .action-composer .textarea {\n    min-height: 48px;", css)
        self.assertIn(".mobile-action-jump {\n    align-items: center;", css)
        self.assertIn(".mobile-action-jump__meta {\n    display: inline;", css)

    def test_mobile_action_jump_is_hidden_on_desktop(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn(".mobile-action-jump {\n  display: none;", css)

    def test_mobile_action_jump_focuses_main_action_input(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("data-action-jump", game)
        self.assertIn("initActionJump", app_js)
        self.assertIn("focusPlayerActionInput", app_js)
        self.assertIn('closest("[data-action-jump]")', app_js)
        self.assertIn('textarea[name=player_text]', app_js)
        self.assertIn("ta.focus()", app_js)
        self.assertIn("setSelectionRange", app_js)
        self.assertIn('scrollIntoView({ block: "center", behavior: "smooth" })', app_js)

    def test_turn_action_draft_is_persisted_per_session_until_success(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("TURN_DRAFT_STORAGE_PREFIX", app_js)
        self.assertIn("function turnDraftKey(form)", app_js)
        self.assertIn('querySelector("input[name=session_id]")', app_js)
        self.assertIn("function initTurnDraftPersistence()", app_js)
        self.assertIn('localStorage.getItem(turnDraftKey(form))', app_js)
        self.assertIn("function showTurnDraftFeedback()", app_js)
        self.assertIn('window.DndI18n.t("game.js.draft_restored")', app_js)
        self.assertIn(
            "if (saved && !ta.value.trim()) {\n"
            "              ta.value = saved;\n"
            "              resizeAutoGrowTextarea(ta);\n"
            "              showTurnDraftFeedback();\n"
            "            }",
            app_js,
        )
        self.assertIn('localStorage.setItem(turnDraftKey(form), ta.value)', app_js)
        self.assertIn('localStorage.removeItem(turnDraftKey(form))', app_js)
        self.assertIn("initTurnDraftPersistence();", app_js)
        self.assertIn("let turnSucceeded = false;", app_js)
        self.assertIn("turnSucceeded = true;", app_js)
        self.assertIn("if (ta && turnSucceeded)", app_js)
        self.assertIn("clearTurnDraft(form);", app_js)

    def test_htmx_turn_errors_are_rendered_without_clearing_the_draft(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('addEventListener("htmx:beforeSwap"', app_js)
        self.assertIn('getResponseHeader("X-Turn-Accepted")', app_js)
        self.assertIn("evt.detail.shouldSwap = true;", app_js)
        self.assertIn("evt.detail.isError = false;", app_js)

    def test_player_action_textarea_autogrows_without_overrunning_story(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('name="player_text" required data-turn-lockable data-autogrow', game)
        self.assertIn("function resizeAutoGrowTextarea(ta)", app_js)
        self.assertIn('ta.style.height = "auto";', app_js)
        self.assertIn("Math.min(ta.scrollHeight, maxHeight)", app_js)
        self.assertIn('document.querySelectorAll("textarea[data-autogrow]")', app_js)
        self.assertIn('ta.addEventListener("input", function () {', app_js)
        self.assertIn("resizeAutoGrowTextarea(ta);", app_js)
        self.assertIn("initAutoGrowTextareas();", app_js)
        self.assertIn(".textarea[data-autogrow]", css)
        self.assertIn("max-height: min(34vh, 260px);", css)
        self.assertIn("overflow-y: auto;", css)

    def test_turn_extra_context_draft_is_scoped_and_cleared_after_success(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("STATE_BLOCK_DRAFT_STORAGE_PREFIX", app_js)
        self.assertIn("function stateBlockDraftKey(form)", app_js)
        self.assertIn("function clearStateBlockDraft(form)", app_js)
        self.assertIn("function initStateBlockDraftPersistence()", app_js)
        self.assertIn('textarea[name=state_block]', app_js)
        self.assertIn('localStorage.getItem(stateBlockDraftKey(form))', app_js)
        self.assertIn(
            "if (saved && !stateBlock.value.trim()) {\n"
            "              stateBlock.value = saved;\n"
            "              showTurnContextFeedback(saved.trim());\n"
            "              revealTurnContextInput(stateBlock);\n"
            "            }",
            app_js,
        )
        self.assertIn('localStorage.setItem(stateBlockDraftKey(form), stateBlock.value)', app_js)
        self.assertIn('localStorage.removeItem(stateBlockDraftKey(form))', app_js)
        self.assertIn("initStateBlockDraftPersistence();", app_js)
        self.assertIn("if (stateBlock && turnSucceeded)", app_js)
        self.assertIn('stateBlock.value = "";', app_js)
        self.assertIn("clearStateBlockDraft(form);", app_js)

    def test_story_first_keeps_empty_advanced_inputs_collapsed_on_restore(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("function hasStateBlockDraft(form)", app_js)
        self.assertIn('localStorage.getItem(stateBlockDraftKey(form))', app_js)
        self.assertIn('const compactStory = Boolean(details.closest(".chat-card--story-first"));', app_js)
        self.assertIn(
            'if (saved === "1" && (!compactStory || hasStateBlockDraft(form))) details.open = true;',
            app_js,
        )

    def test_story_first_bounds_open_advanced_inputs_in_compact_action_rail(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn(
            ".chat-card--story-first .play-tools .action-composer details.advanced[open] {\n"
            "    max-height: min(24vh, 190px);\n"
            "    overflow: auto;",
            css,
        )
        self.assertIn(
            ".chat-card--story-first .play-tools .action-composer details.advanced .textarea {\n"
            "    min-height: 54px;",
            css,
        )

    def test_unsaved_turn_draft_warns_before_leaving(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("function hasUnsavedTurnDraft(form)", app_js)
        self.assertIn('form.dataset.turnInFlight === "1"', app_js)
        self.assertIn('form.querySelector("textarea[name=player_text]")', app_js)
        self.assertIn('form.querySelector("textarea[name=state_block]")', app_js)
        self.assertIn("Boolean(playerText && playerText.value.trim())", app_js)
        self.assertIn("Boolean(stateBlock && stateBlock.value.trim())", app_js)
        self.assertIn("function initUnsavedTurnWarning()", app_js)
        self.assertIn('window.addEventListener("beforeunload"', app_js)
        self.assertIn("if (!hasUnsavedTurnDraft(form)) return;", app_js)
        self.assertIn("evt.preventDefault();", app_js)
        self.assertIn('evt.returnValue = "";', app_js)
        self.assertIn("initUnsavedTurnWarning();", app_js)

    def test_turn_submit_button_reflects_input_and_loading_state(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("data-turn-submit", game)
        self.assertIn("game.composer.send", game)
        self.assertIn("game.composer.sending", game)
        self.assertIn("function updateTurnSubmitState(form)", app_js)
        self.assertIn("function initTurnSubmitState()", app_js)
        self.assertIn("form.dataset.turnInFlight", app_js)
        self.assertIn("submitBtn.textContent = loading ? loadingLabel : defaultLabel", app_js)
        self.assertIn("submitBtn.disabled = loading || !hasText || !llmReady;", app_js)
        self.assertIn("ta.addEventListener(\"input\"", app_js)
        self.assertIn("initTurnSubmitState();", app_js)
        self.assertIn("updateTurnSubmitState(form);", app_js)
        self.assertIn(".btn:disabled", css)
        self.assertIn("cursor: not-allowed", css)

    def test_turn_keyboard_shortcut_respects_submit_button_state(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("function submitTurnFormFromShortcut(form)", app_js)
        self.assertIn("updateTurnSubmitState(form);", app_js)
        self.assertIn('const submitBtn = form.querySelector("[data-turn-submit]");', app_js)
        self.assertIn("if (!submitBtn || submitBtn.disabled) return;", app_js)
        self.assertIn("form.requestSubmit(submitBtn);", app_js)
        self.assertIn("submitTurnFormFromShortcut(form);", app_js)
        self.assertNotIn("form.requestSubmit();", app_js)

    def test_turn_loading_state_is_announced(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('id="turn-loading" class="htmx-indicator spinner" role="status" aria-live="polite"', game)
        self.assertIn('asstContent.setAttribute("role", "status");', app_js)
        self.assertIn('asstContent.setAttribute("aria-live", "polite");', app_js)
        self.assertIn('window.DndI18n.t("game.js.dm_thinking")', app_js)

    def test_turn_request_locks_editable_fields_while_in_flight(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('name="player_text" required data-turn-lockable', game)
        self.assertIn('name="tags" data-turn-lockable', game)
        self.assertIn('name="state_block" data-turn-lockable', game)
        self.assertIn("function setTurnFieldsReadOnly(form, readOnly)", app_js)
        self.assertIn('querySelectorAll("[data-turn-lockable]")', app_js)
        self.assertIn("field.readOnly = readOnly;", app_js)
        self.assertIn('field.setAttribute("aria-readonly", readOnly ? "true" : "false");', app_js)
        self.assertIn("setTurnFieldsReadOnly(form, inFlight);", app_js)
        self.assertIn("function isTurnRequestInFlight()", app_js)
        self.assertIn("if (isTurnRequestInFlight()) return;", app_js)
        self.assertIn("[data-turn-lockable][readonly]", css)
        self.assertIn("cursor: wait", css)

    def test_streaming_turn_cancel_or_network_failure_replaces_waiting_state(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("function renderTurnRequestNotice(turnEl, title, message, warn)", app_js)
        self.assertIn('err && err.name === "AbortError"', app_js)
        self.assertIn('window.DndI18n.t("game.error.cancelled_title")', app_js)
        self.assertIn('window.DndI18n.t("game.error.cancelled_body")', app_js)
        self.assertIn('window.DndI18n.t("game.error.request_title")', app_js)
        self.assertIn('window.DndI18n.t("game.error.network")', app_js)
        self.assertIn('notice.className = warn ? "notice notice--err" : "notice"', app_js)
        self.assertIn('notice.setAttribute("role", "status");', app_js)
        self.assertIn('notice.setAttribute("aria-live", "polite");', app_js)
        self.assertIn("asstMsg.innerHTML = '';", app_js)

    def test_successful_turn_refreshes_character_review_panel(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("function refreshCharacterPanel()", app_js)
        self.assertIn('document.getElementById("character-panel")', app_js)
        self.assertIn('window.htmx.ajax("GET", "/character/panel"', app_js)
        self.assertIn('target: "#character-panel"', app_js)
        self.assertIn('swap: "innerHTML"', app_js)
        self.assertIn("refreshCharacterPanel();", app_js)
        self.assertLess(app_js.index("turnSucceeded = true;"), app_js.index("refreshCharacterPanel();"))
        self.assertIn("function surfacePendingReview(turn)", app_js)
        self.assertIn("turn && turn.has_pending_review", app_js)
        self.assertIn('document.querySelector("[data-pending-count]")', app_js)
        self.assertIn('window.DndI18n.t("game.js.pending_body", { count: next })', app_js)
        self.assertIn("data-review-callout", game)
        self.assertIn("data-review-callout-text", game)
        self.assertIn('surfacePendingReview(payload.turn);', app_js)
        self.assertLess(app_js.index("refreshCharacterPanel();"), app_js.index("surfacePendingReview(payload.turn);"))
        self.assertIn("evt.detail && evt.detail.successful === false", app_js)
        self.assertIn('turnAccepted === "0"', app_js)

    def test_desktop_game_chrome_keeps_action_loop_compact(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('class="page-title-row__title"', game)
        self.assertIn('class="muted quick-roll-panel__result"', game)
        self.assertNotIn('id="quick-roll-result" style=', game)
        self.assertIn(".inline-form .input--compact {\n  margin-top: 0;", css)
        self.assertIn("width: auto;", css)
        self.assertIn(".page-title-row__title {\n  font-size: 2rem;", css)
        self.assertIn(".action-composer .textarea {\n  min-height: 72px;", css)
        self.assertIn(".quick-roll-panel__result {\n  margin-top: 6px;", css)
        self.assertIn("game.advanced.title", game)
        self.assertNotIn("高级选项（标签 / 额外上下文，可选）", game)

    def test_quick_roll_result_can_be_applied_to_turn_context(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/roll_result.html")
        html = template.render(event={"expr": "1d20+5", "rolls": [13], "modifier": 5, "total": 18})
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('hx-post="/game/roll"', game)
        self.assertIn('hx-indicator="#quick-roll-loading"', game)
        quick_roll_input = re.search(r'<input\b[^>]*name="roll_expr_text"[^>]*>', game, re.S)
        self.assertIsNotNone(quick_roll_input)
        quick_roll_attrs = quick_roll_input.group(0)
        self.assertIn("required", quick_roll_attrs)
        self.assertIn("game.roll.input_aria", quick_roll_attrs)
        self.assertIn('autocomplete="off"', quick_roll_attrs)
        self.assertIn('id="quick-roll-loading"', game)
        self.assertIn('id="quick-roll-loading" class="htmx-indicator spinner" role="status" aria-live="polite"', game)
        self.assertIn("game.roll.loading", game)
        self.assertIn('class="htmx-indicator spinner"', game)
        self.assertIn('id="quick-roll-result" class="muted quick-roll-panel__result" role="status" aria-live="polite"', game)
        self.assertIn("data-roll-context", html)
        self.assertIn("带入本回合线索", html)
        self.assertIn("掷骰结果：1d20+5", html)
        self.assertIn("[13]", html)
        self.assertIn("= 18", html)
        self.assertIn("initRollContextActions", app_js)
        self.assertIn('closest("[data-roll-context]")', app_js)
        self.assertIn('textarea[name=state_block]', app_js)
        self.assertIn("data-turn-context-feedback", game)
        self.assertIn("function showTurnContextFeedback(context)", app_js)
        self.assertIn("function hideTurnContextFeedback()", app_js)
        self.assertIn('document.querySelector("[data-turn-context-feedback]")', app_js)
        self.assertIn('window.DndI18n.t("game.js.context_added", { context })', app_js)
        self.assertIn("function revealTurnContextInput(stateBlock)", app_js)
        self.assertIn('const advanced = stateBlock.closest("[data-advanced-inputs]");', app_js)
        self.assertIn("advanced.open = true;", app_js)
        self.assertIn('localStorage.setItem(ADVANCED_STORAGE_KEY, "1");', app_js)
        self.assertIn('stateBlock.focus({ preventScroll: true });', app_js)
        self.assertIn('stateBlock.scrollIntoView({ block: "center", behavior: "smooth" });', app_js)
        self.assertIn('const contextLines = current.split("\\n").map((line) => line.trim()).filter(Boolean);', app_js)
        self.assertIn("if (contextLines.includes(context)) {", app_js)
        self.assertIn('window.DndI18n.t("game.js.context_exists")', app_js)
        self.assertIn('window.DndI18n.t("game.js.context_used")', app_js)
        self.assertIn("hideTurnContextFeedback();", app_js)
        self.assertNotIn("turnContextFeedbackTimer", app_js)
        self.assertIn('window.DndI18n.t("game.js.context_use")', app_js)
        self.assertIn("window.setTimeout", app_js)
        self.assertIn("btn.disabled = true", app_js)
        self.assertIn(".action-composer__context-feedback", css)
        self.assertIn(".roll-result__actions", css)

    def test_quick_roll_submit_starts_disabled_until_expression_is_entered(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        quick_roll_input = re.search(r'<input\b[^>]*name="roll_expr_text"[^>]*>', game, re.S)
        quick_roll_button = re.search(r'<button\b[^>]*data-quick-roll-submit[^>]*>', game, re.S)
        self.assertIsNotNone(quick_roll_input)
        self.assertIsNotNone(quick_roll_button)
        self.assertIn("data-quick-roll-input", quick_roll_input.group(0))
        self.assertIn("disabled", quick_roll_button.group(0))
        self.assertIn("function updateQuickRollSubmitState(form)", app_js)
        self.assertIn('form.querySelector("[data-quick-roll-input]")', app_js)
        self.assertIn('form.querySelector("[data-quick-roll-submit]")', app_js)
        self.assertIn("submitBtn.disabled = loading || !hasExpr;", app_js)
        self.assertIn("function initQuickRollSubmitState()", app_js)
        self.assertIn('input.addEventListener("input"', app_js)
        self.assertIn("initQuickRollSubmitState();", app_js)

    def test_quick_roll_submit_locks_while_request_is_in_flight(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('form.dataset.quickRollInFlight === "1"', app_js)
        self.assertIn("submitBtn.disabled = loading || !hasExpr;", app_js)
        self.assertIn("function setQuickRollRequestUI(form, inFlight)", app_js)
        self.assertIn('form.dataset.quickRollInFlight = inFlight ? "1" : "0";', app_js)
        self.assertIn('elt.querySelector("[data-quick-roll-submit]")', app_js)
        self.assertIn("setQuickRollRequestUI(elt, true);", app_js)
        self.assertIn("setQuickRollRequestUI(elt, false);", app_js)

    def test_quick_roll_input_is_readonly_while_request_is_in_flight(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('const input = form.querySelector("[data-quick-roll-input]");', app_js)
        self.assertIn("input.readOnly = inFlight;", app_js)
        self.assertIn('input.setAttribute("aria-readonly", inFlight ? "true" : "false");', app_js)
        self.assertIn("[data-quick-roll-input][readonly]", css)
        self.assertIn("cursor: wait", css)

    def test_game_panel_save_feedback_is_announced(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn('id="sidebar-saving" class="htmx-indicator spinner" role="status" aria-live="polite"', game)
        self.assertIn('id="sidebar-save-result" role="status" aria-live="polite"', game)
        self.assertIn('id="cheat-saving" class="htmx-indicator spinner" role="status" aria-live="polite"', game)
        self.assertIn('id="cheat-save-result" role="status" aria-live="polite"', game)

    def test_desktop_story_first_mode_keeps_quick_roll_in_reach(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn(
            ".chat-card--story-first {\n"
            "  display: flex;\n"
            "  flex-direction: column;\n"
            "  height: 100%;",
            css,
        )
        self.assertIn("  min-height: 0;", css)
        self.assertIn(".chat-card--story-first .chat-history {\n  flex: 1 1 auto;\n  min-height: 0;\n  max-height: none;", css)
        self.assertIn(".chat-card--story-first .play-tools {\n  position: static;", css)
        self.assertIn(".chat-card--story-first .action-composer .textarea {\n  min-height: 56px;", css)

    def test_short_desktop_story_first_does_not_clip_action_loop(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('data-autogrow rows="1"', game)
        self.assertIn("@media (min-width: 981px) and (max-height: 760px) {", css)
        self.assertIn(
            ".page-game .app-main {\n"
            "    padding-top: 10px;\n"
            "  }",
            css,
        )
        self.assertIn(
            ".chat-card--story-first .chat-history-shell {\n"
            "    min-height: 150px;\n"
            "  }",
            css,
        )
        self.assertIn(".latest-choice-tray__heading {\n    display: none;", css)
        self.assertIn(".chat-card--story-first .action-composer__notice {\n    align-items: center;", css)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto;", css)
        self.assertIn(
            ".chat-card--story-first .play-tools {\n"
            "    max-height: calc(100% - 200px);\n"
            "    overflow-y: auto;",
            css,
        )
        self.assertNotIn("height: clamp(180px, 26vh, 190px);", css)
        self.assertIn(".page-game .page-title-row {", css)
        self.assertIn("margin-top: 0;", css)
        self.assertIn(".page-game .status-tile__label {", css)
        self.assertIn("display: none;", css)

    def test_desktop_story_first_allows_resizing_before_wide_desktop(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("@media (min-width: 981px) {", css)
        self.assertIn(
            ".chat-card--story-first {\n"
            "  display: flex;\n"
            "  flex-direction: column;",
            css,
        )
        self.assertNotIn("grid-template-columns: minmax(0, 1fr) minmax(320px, 360px);", css)
        self.assertNotIn("    grid-column: 2;\n    grid-row: 2;", css)
        self.assertIn("    width: 100%;", css)
        self.assertIn("    min-height: 0;", css)
        self.assertIn("    overflow-y: auto;", css)
        self.assertIn(".chat-card--story-first .play-tools {\n    align-content: start;", css)
        self.assertIn("    flex: 0 0 auto;", css)
        self.assertIn("    grid-template-columns: minmax(0, 1fr);", css)
        self.assertIn(".chat-card--story-first .play-tools .action-composer {\n    padding: 6px;", css)
        self.assertIn(".chat-card--story-first .play-tools .action-composer .textarea {\n    min-height: 48px;", css)
        self.assertIn(".chat-card--story-first .play-tools .quick-roll-panel {\n    padding: 5px 7px;", css)
        self.assertIn("@media (max-width: 900px) {\n  .grid--game { grid-template-columns: 1fr; }", css)
        self.assertIn(".grid:not(.grid--game) {\n    grid-template-columns: 1fr;", css)
        self.assertNotIn("  .grid {\n    grid-template-columns: 1fr;\n  }", css)
        self.assertNotIn("@media (max-width: 1440px) {\n  .grid--game-story-first", css)

    def test_mobile_story_first_keeps_story_history_readable(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 520px)", css)
        self.assertIn(
            ".chat-card--story-first .chat-history {\n"
            "    min-height: clamp(130px, 18vh, 170px);\n"
            "    max-height: min(20vh, 180px);",
            css,
        )
        self.assertNotIn("max-height: 9vh;", css)
        self.assertNotIn("max-height: min(32vh, 260px);", css)
        self.assertNotIn("min-height: 80px;", css)

    def test_story_dialogue_prioritizes_readable_width(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("grid--game-story-first", game)
        self.assertIn(".app-main {\n  max-width: 2160px;", css)
        self.assertIn(
            ".grid--game-story-first {\n"
            "  --game-sidebar-width: 400px;\n"
            "  grid-template-columns: minmax(560px, 1fr) 10px minmax(340px, var(--game-sidebar-width));",
            css,
        )
        self.assertIn("  gap: 10px;", css)
        self.assertIn(
            "@media (max-width: 900px) {\n"
            "  .grid--game { grid-template-columns: 1fr; }",
            css,
        )
        self.assertNotIn("@media (max-width: 1680px) {\n  .grid--game-story-first", css)
        self.assertIn(
            ".sidebar-card { max-height: none; overflow: visible; position: static; }",
            css,
        )
        self.assertNotIn("@media (max-width: 1320px) {\n  .grid--game { grid-template-columns: 1fr; }", css)
        self.assertIn(".chat__msg {\n  border: 1px solid var(--ledger-line);", css)
        self.assertIn("max-width: 100%;", css)
        self.assertIn(".chat__msg--user {\n  align-self: flex-end;\n  max-width: min(96%, 1280px);", css)
        self.assertIn(".chat__msg--assistant {\n  align-self: stretch;\n  width: 100%;", css)
        self.assertIn(".chat__content {\n  line-height: 1.65;", css)
        self.assertNotIn("max-height: 26vh;", css)

    def test_game_page_uses_remaining_viewport_without_sidebar_page_overflow(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("{% block body_class %}", base)
        self.assertIn("{% block body_class %}page-game{% endblock %}", game)
        page_game = re.search(r"\.page-game\s*\{([^}]*)\}", css)
        self.assertIsNotNone(page_game)
        self.assertIn("display: flex;", page_game.group(1))
        self.assertIn("flex-direction: column;", page_game.group(1))
        self.assertIn("height: 100dvh;", page_game.group(1))
        app_main = re.search(r"\.page-game \.app-main\s*\{([^}]*)\}", css)
        self.assertIsNotNone(app_main)
        self.assertIn("flex: 1 1 auto;", app_main.group(1))
        self.assertIn("height: auto;", app_main.group(1))
        self.assertNotIn("height: calc(100dvh - 71px);", css)
        self.assertIn(".page-game .grid--game {", css)
        self.assertIn("flex: 1 1 auto;", css)
        self.assertIn(".page-game .sidebar-card {", css)
        self.assertIn("height: 100%;", css)
        self.assertIn("overflow: auto;", css)
        self.assertIn("position: static;", css)

    def test_latest_choices_form_a_compact_action_deck(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn(".latest-choice-tray__list {", css)
        self.assertIn("grid-auto-flow: column;", css)
        self.assertIn("grid-auto-columns: minmax(210px, 1fr);", css)
        self.assertIn(".chat-card--story-first .quick-roll-panel {", css)
        self.assertIn("grid-template-columns: auto minmax(260px, 420px) minmax(150px, 1fr);", css)

    def test_game_layout_exposes_resizable_desktop_split(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('data-game-layout', game)
        self.assertIn('data-game-layout-resizer', game)
        self.assertIn('role="separator"', game)
        self.assertIn('aria-orientation="vertical"', game)
        self.assertIn("game.layout.resize_aria", game)
        self.assertIn('data-game-layout-reset', game)
        self.assertLess(game.index("chat-card"), game.index("data-game-layout-resizer"))
        self.assertLess(game.index("data-game-layout-resizer"), game.index("sidebar-card"))

        self.assertIn("--game-sidebar-width", css)
        self.assertIn(".game-layout-resizer", css)
        self.assertIn("cursor: col-resize;", css)
        self.assertIn("body.sidebar-collapsed .game-layout-resizer", css)
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn(".grid--game { grid-template-columns: 1fr; }", css)

    def test_game_layout_resizer_script_persists_and_resets_width(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('const GAME_LAYOUT_WIDTH_STORAGE_PREFIX = "one_person_dnd.gameSidebarWidth.";', app_js)
        self.assertIn("function initGameLayoutResizer()", app_js)
        self.assertIn('querySelector("[data-game-layout]")', app_js)
        self.assertIn('querySelector("[data-game-layout-resizer]")', app_js)
        self.assertIn('querySelector("[data-game-layout-reset]")', app_js)
        self.assertIn('--game-sidebar-width', app_js)
        self.assertIn('localStorage.setItem(gameLayoutStorageKey(grid),', app_js)
        self.assertIn('localStorage.removeItem(gameLayoutStorageKey(grid));', app_js)
        self.assertIn('resizer.addEventListener("pointerdown"', app_js)
        self.assertIn('resizer.addEventListener("dblclick"', app_js)
        self.assertIn('evt.key === "ArrowLeft"', app_js)
        self.assertIn("initGameLayoutResizer();", app_js)

    def test_chat_history_exposes_corner_height_resizer(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('class="chat-history-shell"', game)
        self.assertIn('data-chat-history-shell', game)
        self.assertIn('data-chat-history-resizable', game)
        self.assertIn('data-chat-history-resizer', game)
        self.assertIn("game.history.resize_aria", game)
        self.assertIn('aria-orientation="horizontal"', game)
        self.assertIn("game.history.resize_title", game)
        self.assertLess(game.index('id="chat-history"'), game.index("data-chat-history-resizer"))

        self.assertIn(".chat-history-shell", css)
        self.assertIn(".chat-history-resizer", css)
        self.assertIn("cursor: ns-resize;", css)
        self.assertIn("body.chat-history-resizing", css)
        self.assertIn(".chat-card--history-resized", css)
        self.assertIn(".chat-card--history-resized .chat-history", css)
        self.assertIn(".chat-card--story-first.chat-card--history-resized .chat-history", css)
        self.assertIn("height: var(--chat-history-height);", css)
        self.assertIn("@media (max-width: 520px)", css)

    def test_chat_history_resizer_script_persists_keyboard_and_resets_height(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('const CHAT_HISTORY_HEIGHT_STORAGE_PREFIX = "one_person_dnd.chatHistoryHeight.";', app_js)
        self.assertIn("function initChatHistoryResizer()", app_js)
        self.assertIn('querySelector("[data-chat-history-resizable]")', app_js)
        self.assertIn('querySelector("[data-chat-history-resizer]")', app_js)
        self.assertIn("function canResizeChatHistory(resizer)", app_js)
        self.assertIn('chat.style.setProperty("--chat-history-height", nextHeight + "px");', app_js)
        self.assertIn('localStorage.setItem(chatHistoryHeightStorageKey(),', app_js)
        self.assertIn('localStorage.removeItem(chatHistoryHeightStorageKey());', app_js)
        self.assertIn('resizer.addEventListener("pointerdown"', app_js)
        self.assertIn('resizer.addEventListener("dblclick"', app_js)
        self.assertIn('evt.key !== "ArrowUp" && evt.key !== "ArrowDown"', app_js)
        self.assertIn("resetChatHistoryHeight(chat);", app_js)
        self.assertIn("initChatHistoryResizer();", app_js)

    def test_game_page_surfaces_pending_review_callout(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("review-callout", game)
        self.assertIn("game.review.title", game)
        self.assertIn('href="#character-panel"', game)
        self.assertLess(game.index("game-status-strip"), game.index("review-callout"))
        self.assertLess(game.index("review-callout"), game.index("grid grid--game"))
        self.assertIn(".review-callout", css)
        self.assertIn(".review-callout__actions", css)

    def test_game_page_surfaces_world_setup_prompt(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("world_setup_prompt.show", game)
        self.assertIn("world-setup-callout", game)
        self.assertIn("game.world_setup.title", game)
        self.assertIn('href="/new"', game)
        self.assertIn('href="/memory/world/new"', game)
        self.assertIn('action="/game/world-setup/skip"', game)
        self.assertIn("game.world_setup.skip", game)
        self.assertLess(game.index("game-status-strip"), game.index("world-setup-callout"))
        self.assertLess(game.index("world-setup-callout"), game.index("grid grid--game"))
        self.assertIn(".world-setup-callout", css)

    def test_hidden_attribute_overrides_component_display_rules(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("[hidden] {", css)
        self.assertIn("display: none !important;", css)
        self.assertLess(css.index("[hidden] {"), css.index(".review-callout {"))

    def test_models_profiles_use_browse_first_cards(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("model-profile-library", template)
        self.assertIn("model-profile-card", template)
        self.assertIn("model-profile-actions", template)
        self.assertLess(template.index("models.existing.title"), template.index("models.add.summary"))
        self.assertIn(".model-profile-library", css)
        self.assertIn(".model-profile-card--active", css)

        english = _template_environment("en").get_template("models.html").render(
            profiles=[],
            provider_presets=[],
            active_id=None,
            created=False,
        )
        self.assertLess(english.index("Saved models"), english.index("Add model"))
        self.assertIn("Models", english)

    def test_key_forms_use_explicit_labels_and_safe_autocomplete(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        models = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")
        new = Path("src/one_person_dnd/web/templates/new.html").read_text(encoding="utf-8")
        character_panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")
        saves = Path("src/one_person_dnd/web/templates/saves.html").read_text(encoding="utf-8")

        self.assertIn('textarea class="input textarea" name="player_text" required data-turn-lockable data-autogrow rows="1" autocomplete="off"', game)
        self.assertIn('input class="input" name="tags" data-turn-lockable autocomplete="off"', game)
        self.assertIn('textarea class="input textarea" name="state_block" data-turn-lockable autocomplete="off"', game)
        self.assertIn('select class="input input--compact" name="session_id" aria-label="{{ t(\'game.session.switch_aria\') }}" autocomplete="off"', game)
        self.assertIn('input class="input" name="current_scene" value="{{ current_scene }}" autocomplete="off"', game)

        self.assertIn('id="deepseek-profile-name"', models)
        self.assertIn('id="deepseek-api-key"', models)
        self.assertIn('type="password" name="api_key" required autocomplete="new-password"', models)
        self.assertIn('type="url" name="base_url" required autocomplete="url"', models)
        self.assertIn('name="model" required autocomplete="off" spellcheck="false"', models)
        self.assertIn('type="number" step="0.1" name="timeout_seconds"', models)

        self.assertIn('id="adventure-genre"', new)
        self.assertIn('type="number" name="character_count"', new)
        self.assertIn("new.constraints.placeholder", new)

        self.assertIn('input class="input input--compact" type="number" inputmode="numeric" name="hp_delta" value="0" autocomplete="off"', character_panel)
        self.assertIn('input class="input input--compact" type="number" inputmode="numeric" name="gold_delta" value="0" autocomplete="off"', character_panel)
        self.assertIn('input class="input" name="reason" autocomplete="off" placeholder="{{ t(\'character.reason_placeholder\') }}"', character_panel)
        self.assertIn('textarea class="input textarea" name="conditions_text" autocomplete="off"', character_panel)
        self.assertIn('textarea class="input textarea" name="inventory_text" autocomplete="off"', character_panel)
        self.assertIn('textarea class="input textarea" name="notes_text" autocomplete="off"', character_panel)
        self.assertIn('textarea class="input textarea" name="character_sheet" autocomplete="off" spellcheck="false"', character_panel)

        self.assertIn('id="blank-adventure-name" class="input" name="name" required autocomplete="off"', saves)
        self.assertIn('id="new-chapter-title" class="input" name="title" required autocomplete="off"', saves)
        self.assertIn("saves.chapter.start_scene_placeholder", saves)
        self.assertIn("saves.snapshot.name_placeholder", saves)
        self.assertIn("saves.fork.title_placeholder", saves)

    def test_primary_entry_templates_keep_styles_in_css(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        models = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")
        new = Path("src/one_person_dnd/web/templates/new.html").read_text(encoding="utf-8")

        self.assertNotIn("style=", game)
        self.assertNotIn("style=", models)
        self.assertNotIn("style=", new)
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")
        for class_name in (
            ".notice__title",
            ".button--initially-hidden",
            ".notice--spaced",
            ".card--spaced",
            ".field-grid",
            ".panel-loading",
            ".recall-preview-shell",
            ".check-row",
            ".model-profile-edit",
        ):
            self.assertIn(class_name, css)

    def test_live_review_templates_keep_spacing_in_css(self) -> None:
        character_panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")
        saves = Path("src/one_person_dnd/web/templates/saves.html").read_text(encoding="utf-8")

        self.assertNotIn("style=", character_panel)
        self.assertNotIn("style=", saves)
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")
        for class_name in (
            ".stat-pills--spaced",
            ".muted--spaced",
            ".label--flush",
            ".advanced--spaced",
            ".advanced--compact",
            ".pre--wrap",
            ".row--compact-spaced",
            ".muted--compact-spaced",
        ):
            self.assertIn(class_name, css)

    def test_medium_viewport_keeps_review_chrome_compact(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("game.review.body", game)
        self.assertIn("@media (max-width: 900px) {", css)
        self.assertIn("  .grid--game { grid-template-columns: 1fr; }", css)
        self.assertIn("  .page-game .app-main { display: block; height: auto; overflow: visible; }", css)
        self.assertIn("@media (max-width: 1320px) {", css)
        self.assertIn(
            "  .game-status-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin-top: 8px; }",
            css,
        )
        self.assertIn("  .review-callout { gap: 10px; margin-top: 8px; padding: 8px 10px; }", css)

    def test_character_panel_shows_summary_before_advanced_json(self) -> None:
        panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")

        self.assertIn("character.overview", panel)
        self.assertIn("character_summary", panel)
        self.assertIn("character.change.preview", panel)
        self.assertIn("change-preview", panel)
        self.assertIn("preview.lines", panel)
        self.assertIn("character.json_summary", panel)
        self.assertIn("<details", panel)
        self.assertNotIn('class="card"', panel)

        english = _template_environment("en").get_template("partials/character_panel.html").render(
            session_id=1,
            character_sheet="{}",
            quick_stats={"hp": None, "gold": None},
            pending_changes=[],
            pending_count=0,
            notice_message="Player-authored notice",
            character_summary=SimpleNamespace(has_content=False),
        )
        self.assertIn("Character Overview", english)
        self.assertIn("Character Sheet JSON (Advanced)", english)
        self.assertIn("Player-authored notice", english)

    def test_character_panel_surfaces_notice_before_controls(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/character_panel.html")

        html = template.render(
            session_id=1,
            character_sheet="{}",
            quick_stats={"hp": None, "gold": None},
            pending_changes=[],
            pending_count=0,
            notice_message="已应用变更。",
            character_summary=SimpleNamespace(has_content=False),
        )

        self.assertIn('class="notice panel-notice"', html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertLess(html.index("已应用变更。"), html.index("角色概览"))
        self.assertLess(html.index("已应用变更。"), html.index("角色卡 JSON（高级）"))

    def test_character_panel_mutation_forms_announce_progress(self) -> None:
        panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")

        for indicator_id, key in (
            ("quick-adjust-saving", "character.applying"),
            ("quick-state-saving", "character.saving"),
            ("character-saving", "character.saving"),
        ):
            self.assertIn(f'hx-indicator="#{indicator_id}"', panel)
            translated = "{{ t('" + key + "') }}"
            self.assertIn(
                f'id="{indicator_id}" class="htmx-indicator spinner form-status" role="status" aria-live="polite">{translated}</span>',
                panel,
            )

        self.assertIn('id="character-save-result" role="status" aria-live="polite"', panel)
        self.assertIn('hx-indicator="#change-apply-saving-{{ c.id }}"', panel)
        self.assertIn(
            'id="change-apply-saving-{{ c.id }}" class="htmx-indicator spinner form-status" role="status" aria-live="polite">{{ t(\'character.applying\') }}</span>',
            panel,
        )
        self.assertIn('hx-indicator="#change-reject-saving-{{ c.id }}"', panel)
        self.assertIn(
            'id="change-reject-saving-{{ c.id }}" class="htmx-indicator spinner form-status" role="status" aria-live="polite">{{ t(\'character.rejecting\') }}</span>',
            panel,
        )

    def test_character_panel_renders_abilities_conditions_and_notes_form(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/character_panel.html")

        html = template.render(
            session_id=1,
            character_sheet="{}",
            quick_stats={"hp": 8, "gold": 15},
            pending_changes=[],
            notice_message="",
            character_summary=SimpleNamespace(
                has_content=True,
                name="艾拉",
                race="人类",
                role="游侠",
                hp=8,
                max_hp=12,
                gold=15,
                goal="找到失踪的导师",
                inventory=["短弓"],
                abilities={"DEX": 14, "WIS": 13},
                conditions=["中毒", "隐匿"],
                notes="害怕深水。",
            ),
        )

        self.assertIn("属性：DEX 14，WIS 13", html)
        self.assertIn("状态：中毒、隐匿", html)
        self.assertIn("物品：短弓", html)
        self.assertIn("备注：害怕深水。", html)
        self.assertIn('hx-post="/character/quick_state"', html)
        self.assertIn('name="conditions_text"', html)
        self.assertIn('name="inventory_text"', html)
        self.assertIn('name="notes_text"', html)

    def test_character_panel_refresh_syncs_pending_review_count(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")

        self.assertIn("data-character-pending-count", panel)
        self.assertIn("function syncPendingReviewCountFromPanel()", app_js)
        self.assertIn('document.querySelector("[data-character-pending-count]")', app_js)
        self.assertIn("setPendingReviewCount(count);", app_js)
        self.assertIn('if (evt.target && evt.target.id === "character-panel")', app_js)
        self.assertIn("syncPendingReviewCountFromPanel();", app_js)

    def test_models_edit_form_does_not_render_saved_api_key_value(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")

        self.assertNotIn('value="{{ profile.api_key', template)
        self.assertNotIn('value="{{ p.api_key', template)
        self.assertIn("models.placeholder.api_key_keep", template)
        self.assertIn('type="password" name="api_key"', template)

    def test_models_test_action_shows_progress_indicator(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")

        self.assertIn('hx-post="/models/test"', template)
        self.assertIn('hx-target="#test-result-{{ profile.id }}"', template)
        self.assertIn('hx-indicator="#test-loading-{{ profile.id }}"', template)
        self.assertIn('id="test-loading-{{ profile.id }}"', template)
        self.assertIn("models.testing", template)
        self.assertIn('class="htmx-indicator spinner"', template)

    def test_dm_choices_are_clickable_actions(self) -> None:
        partial = Path("src/one_person_dnd/web/templates/partials/chat_turn.html").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("data-choice-action", partial)
        self.assertIn("data-choice-text", partial)
        self.assertIn('aria-pressed="false"', partial)
        self.assertIn("choice-action", partial)
        self.assertIn("data-choice-action", app_js)
        self.assertIn("initChoiceActions", app_js)
        self.assertIn("function clearSelectedChoiceActions()", app_js)
        self.assertIn("function selectChoiceAction(btn)", app_js)
        self.assertIn('querySelectorAll("[data-choice-action][aria-pressed=\'true\']")', app_js)
        self.assertIn('btn.setAttribute("aria-pressed", "true");', app_js)
        self.assertIn("choice-action--selected", app_js)
        self.assertIn("dataset.choiceText", app_js)
        self.assertIn("data-choice-feedback", app_js)
        self.assertIn("function showChoiceActionFeedback()", app_js)
        self.assertIn('window.DndI18n.t("game.js.choice_filled")', app_js)
        self.assertIn("data-choice-feedback", game)
        self.assertIn('role="status"', game)
        self.assertIn(".action-composer__feedback", css)
        self.assertIn('textarea[name=player_text]', app_js)
        self.assertIn(".choice-action", css)
        self.assertIn(".choice-action:focus-visible", css)
        self.assertIn("outline: 2px solid var(--parchment);", css)
        self.assertNotIn(".choice-action:focus {\n  border-color: var(--accent);\n  background: rgba(122, 162, 247, 0.13);\n  outline: none;", css)
        self.assertIn(".choice-action--selected", css)

    def test_manual_action_edit_clears_selected_choice_state(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("function syncSelectedChoiceWithInput(form)", app_js)
        self.assertIn('document.querySelector("[data-choice-action][aria-pressed=\'true\']")', app_js)
        self.assertIn("const currentText = ta && ta.value ? ta.value.trim() : \"\";", app_js)
        self.assertIn("const selectedText = (selected.dataset.choiceText || selected.textContent || \"\").trim();", app_js)
        self.assertIn("if (!currentText || selectedText !== currentText) clearSelectedChoiceActions();", app_js)
        self.assertIn("syncSelectedChoiceWithInput(form);", app_js)

    def test_successful_turn_clears_selected_choice_state(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn(
            'if (ta && turnSucceeded) {\n'
            '                  ta.value = "";\n'
            '                  resizeAutoGrowTextarea(ta);\n'
            '                  clearSelectedChoiceActions();',
            app_js,
        )
        self.assertIn(
            'if (ta) {\n'
            '            ta.value = "";\n'
            '            resizeAutoGrowTextarea(ta);\n'
            '            clearSelectedChoiceActions();\n'
            '          }',
            app_js,
        )

    def test_starter_actions_share_choice_selected_state(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('data-choice-action aria-pressed="false"', game)
        self.assertIn("selectChoiceAction(btn);", app_js)

    def test_chat_turn_renders_action_assessment_for_new_turns(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/chat_turn.html")

        html = template.render(
            turn={
                "turn_index": 0,
                "player_text": "我成功说服守卫交出钥匙",
                "dm": {"narration": "守卫犹豫了。", "choices": [], "dm_notes": "", "memory_suggestions": ""},
                "dice_events": [],
                "action_assessment": {
                    "action_type": "social",
                    "signals": ["roll_may_be_needed"],
                    "warnings": ["declared_success"],
                },
            }
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("action-assessment", html)
        self.assertIn("系统判定", html)
        self.assertIn("行动：社交", html)
        self.assertIn('title="social"', html)
        self.assertIn("可能需要掷骰", html)
        self.assertIn('title="roll_may_be_needed"', html)
        self.assertIn("行动描述已包含结果", html)
        self.assertIn('title="declared_success"', html)
        self.assertNotIn(">roll_may_be_needed<", html)
        self.assertNotIn(">declared_success<", html)
        self.assertIn(".action-assessment", css)
        self.assertIn(".assessment-pill--warn", css)

    def test_english_history_localizes_frozen_adjudication_intent(self) -> None:
        template = _template_environment("en").get_template("partials/chat_turn.html")

        html = template.render(
            turn={
                "turn_index": 0,
                "player_text": "I sneak past the customs officer.",
                "dm": {
                    "narration": "You disappear into the lantern shadows.",
                    "choices": [],
                    "dm_notes": "",
                    "memory_suggestions": "",
                },
                "dice_events": [],
                "action_assessment": {
                    "action_type": "exploration",
                    "signals": ["ability_check_resolved"],
                    "warnings": [],
                    "adjudication": {
                        "check": {
                            "outcome": "success",
                            "ability": "DEX",
                            "skill": "Stealth",
                            "dc": 15,
                            "d20s": [16],
                            "selected_d20": 16,
                            "ability_modifier": 2,
                            "proficiency_modifier": 2,
                            "circumstance_modifier": 0,
                            "total": 20,
                            "roll_mode": "normal",
                            "natural_face": None,
                            "intent": "避免被发现",
                        }
                    },
                },
            }
        )

        self.assertIn("Intent: Avoid being detected", html)
        self.assertNotIn("避免被发现", html)

    def test_turn_diagnostics_renders_dm_critic_warnings_outside_story(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/turn_diagnostics.html")

        html = template.render(
            turn={
                "turn_index": 0,
                "player_text": "我继续向前",
                "dm": {"narration": "门后只有一条路。", "choices": ["继续"], "dm_notes": "", "memory_suggestions": ""},
                "dice_events": [],
                "critic_warnings": ["choice_count_out_of_range"],
            }
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("turn-diagnostic", html)
        self.assertIn("行动建议数量不适合继续游玩", html)
        self.assertIn('title="choice_count_out_of_range"', html)
        self.assertNotIn(">choice_count_out_of_range<", html)
        self.assertIn(".dm-review", css)

    def test_turn_diagnostics_renders_response_warnings_outside_story(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/turn_diagnostics.html")

        html = template.render(
            turn={
                "turn_index": 0,
                "player_text": "我和守卫谈判",
                "dm": {
                    "narration": "守卫仍然警惕。",
                    "choices": ["继续", "继续", "成功说服守卫"],
                    "dm_notes": "",
                    "memory_suggestions": "",
                },
                "dice_events": [],
                "response_warnings": ["duplicate_choices", "non_actionable_choice"],
            }
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("turn-diagnostic", html)
        self.assertIn("行动建议重复", html)
        self.assertIn("行动建议过于笼统", html)
        self.assertIn('title="duplicate_choices"', html)
        self.assertIn('title="non_actionable_choice"', html)
        self.assertNotIn(">duplicate_choices<", html)
        self.assertNotIn(">non_actionable_choice<", html)
        self.assertIn(".response-review", css)

    def test_streaming_renderer_outputs_action_assessment(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        diagnostics_py = Path(
            "src/one_person_dnd/web/localization/catalogs/diagnostics.py"
        ).read_text(encoding="utf-8")

        self.assertIn("action_assessment", app_js)
        self.assertIn("action-assessment", app_js)
        self.assertIn('window.DndI18n.t("game.turn.system_judgment")', app_js)
        self.assertIn("ACTION_TYPE_LABELS", app_js)
        self.assertIn("ACTION_SIGNAL_LABELS", app_js)
        self.assertIn("ACTION_WARNING_LABELS", app_js)
        # Label text itself lives in the bilingual diagnostics catalog;
        # app.js reads it from the injected `#dnd-labels` JSON at runtime
        # instead of hardcoding a second copy.
        self.assertIn("可能需要掷骰", diagnostics_py)
        self.assertIn("行动描述已包含结果", diagnostics_py)

    def test_streaming_renderer_localizes_frozen_adjudication_intent(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("ADJUDICATION_INTENT_LABELS", app_js)
        self.assertIn("labelForCode(ADJUDICATION_INTENT_LABELS, check.intent)", app_js)

    def test_streaming_renderer_places_dice_events_with_player_action(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('const userMsg = turnEl.querySelector(".chat__msg--user");', app_js)
        self.assertIn("const diceEvents = (turn && turn.dice_events) || [];", app_js)
        self.assertIn("const hasCanonicalCheck = Boolean(", app_js)
        self.assertIn("if (userMsg && diceEvents && diceEvents.length > 0 && !hasCanonicalCheck) {", app_js)
        self.assertIn("adjudication-summary", app_js)
        self.assertIn("userMsg.appendChild(wrap);", app_js)
        self.assertLess(app_js.index("renderActionAssessment(userMsg"), app_js.index("const diceEvents ="))
        self.assertLess(
            app_js.index("userMsg.appendChild(wrap);"),
            app_js.index('const asstMsg = turnEl.querySelector(".chat__msg--assistant");'),
        )
        self.assertNotIn(
            "asstMsg.appendChild(wrap);\n"
            "          }\n\n"
            "          const narration",
            app_js,
        )

    def test_streaming_turn_skeleton_shows_and_clears_waiting_state(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("streaming-wait", app_js)
        self.assertIn('window.DndI18n.t("game.js.dm_thinking")', app_js)
        self.assertIn('asstContent.dataset.waiting = "1"', app_js)
        self.assertIn('asstContent.textContent = ""', app_js)
        self.assertIn('asstContent.classList.remove("streaming-wait", "spinner")', app_js)
        self.assertLess(app_js.index('asstContent.textContent = ""'), app_js.index('asstContent.textContent += payload.text || ""'))
        self.assertIn(".streaming-wait", css)

    def test_streaming_renderer_outputs_dm_critic_warnings(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        diagnostics_py = Path(
            "src/one_person_dnd/web/localization/catalogs/diagnostics.py"
        ).read_text(encoding="utf-8")

        self.assertIn("critic_warnings", app_js)
        self.assertIn("dm-review", app_js)
        self.assertIn('window.DndI18n.t("game.turn.dm_review")', app_js)
        self.assertIn("CRITIC_WARNING_LABELS", app_js)
        # Single source: the label text lives in the catalog, not app.js.
        self.assertIn("行动建议数量不适合继续游玩", diagnostics_py)

    def test_streaming_renderer_outputs_response_warnings(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")
        diagnostics_py = Path(
            "src/one_person_dnd/web/localization/catalogs/diagnostics.py"
        ).read_text(encoding="utf-8")

        self.assertIn("response_warnings", app_js)
        self.assertIn("response-review", app_js)
        self.assertIn('window.DndI18n.t("game.turn.response_review")', app_js)
        self.assertIn("RESPONSE_WARNING_LABELS", app_js)
        # Single source: the label text lives in the catalog, not app.js.
        self.assertIn("行动建议重复", diagnostics_py)
        self.assertIn("行动建议过于笼统", diagnostics_py)

    def test_chat_turn_append_renders_recalled_context_preview(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        register_jinja_globals(env)
        template = env.get_template("partials/chat_turn_append.html")

        html = template.render(
            turn={
                "turn_index": 0,
                "player_text": "我调查门厅",
                "dm": {"narration": "门厅很安静。", "choices": [], "dm_notes": "", "memory_suggestions": ""},
                "dice_events": [],
            },
            recalled_world=[],
            recalled_context=[
                {
                    "kind": "world_bible",
                    "title": "WorldBible 1",
                    "source": "world_bible",
                    "reason": "匹配玩家填写的标签。",
                    "preview": "[Location] 门厅",
                },
                {
                    "kind": "character_state",
                    "title": "Character Sheet",
                    "source": "character_sheets",
                    "status": "included",
                    "reason": "注入当前角色卡摘要。",
                    "preview": "艾拉 HP：8/12",
                },
                {
                    "kind": "story_memory",
                    "title": "Story Memory 3",
                    "source": "story_journal",
                    "status": "skipped",
                    "reason": "因上下文预算裁剪。",
                    "preview": "旧剧情摘要",
                },
            ],
        )
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("本回合参考", html)
        self.assertIn("WorldBible 1", html)
        self.assertIn("匹配玩家填写的标签。", html)
        self.assertIn("艾拉 HP：8/12", html)
        self.assertIn("已裁剪", html)
        self.assertIn("因上下文预算裁剪。", html)
        self.assertIn("recall-stack", html)
        self.assertIn("recall-item--skipped", html)
        self.assertIn(".recall-stack", css)
        self.assertIn(".recall-item--skipped", css)

    def test_game_recall_preview_empty_state_describes_all_context_sources(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("game.recall.title", game)
        self.assertIn("game.recall.initial", game)
        self.assertNotIn("本回合召回设定", game)
        self.assertNotIn("发送一次行动后显示命中的 WorldBible 条目", game)

    def test_streaming_renderer_outputs_recalled_context_preview(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn("recalled_context", app_js)
        self.assertIn("renderRecalledContext", app_js)
        self.assertIn('window.DndI18n.t("game.recall.title")', app_js)
        self.assertIn('window.DndI18n.t("game.recall.trimmed")', app_js)
        self.assertIn("recall-stack", app_js)

    def test_streaming_renderer_splits_real_sse_newlines(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertIn('buf.split("\\n\\n")', app_js)
        self.assertIn('chunk.split("\\n").filter(Boolean)', app_js)
        self.assertNotIn('buf.split("\\\\n\\\\n")', app_js)
        self.assertNotIn('chunk.split("\\\\n").filter(Boolean)', app_js)

    def test_base_inline_script_uses_valid_plain_js_quotes(self) -> None:
        app_js = Path("src/one_person_dnd/web/static/js/app.js").read_text(encoding="utf-8")

        self.assertNotIn('document.getElementById(\\"', app_js)
        self.assertNotIn('document.createElement(\\"', app_js)
        self.assertNotIn('document.querySelector(\\"', app_js)
        self.assertNotIn('form.querySelector(\\"', app_js)
        self.assertNotIn('addEventListener(\\n            \\"', app_js)

    def test_saves_campaigns_use_mobile_friendly_cards(self) -> None:
        saves = Path("src/one_person_dnd/web/templates/saves.html").read_text(encoding="utf-8")

        self.assertIn("campaign-list", saves)
        self.assertIn("campaign-card", saves)
        self.assertNotIn("<table", saves)

    def test_saves_page_avoids_nested_card_shells(self) -> None:
        saves = Path("src/one_person_dnd/web/templates/saves.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertNotIn('class="card" style=', saves)
        self.assertIn("management-grid", saves)
        self.assertIn("management-section", saves)
        self.assertIn("snapshot-card", saves)
        self.assertIn("saves.snapshots.summary", saves)
        self.assertIn("saves.snapshot.recent_counts", saves)
        self.assertIn("saves.snapshots.empty_title", saves)
        self.assertIn(".management-grid", css)
        self.assertIn(".snapshot-card", css)

    def test_threads_close_action_is_not_duplicated_inside_update_form(self) -> None:
        threads = Path("src/one_person_dnd/web/templates/threads.html").read_text(encoding="utf-8")

        self.assertEqual(threads.count('action="/threads/close"'), 1)
        update_form = threads.split('action="/threads/update"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn('action="/threads/close"', update_form)

    def test_css_declares_adventure_ledger_visual_system(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('<meta name="theme-color" content="#080b10" />', base)
        self.assertIn("html {\n  color-scheme: dark;", css)
        self.assertIn("--bg: #080b10;", css)
        self.assertIn("--parchment: #e4d3b0;", css)
        self.assertIn("--ember: #c07643;", css)
        self.assertIn("--ledger-line", css)
        self.assertIn(".ledger-rail", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("touch-action: manipulation;", css)
        self.assertIn("-webkit-tap-highlight-color: rgba(228, 211, 176, 0.18);", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

    def test_css_has_responsive_grid_nav_and_table_rules(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn(".panel-section", css)
        self.assertIn(".panel-section__title", css)
        self.assertIn(".game-status-strip", css)
        self.assertIn(".tool-panel", css)
        self.assertIn(".campaign-list", css)
        self.assertIn(".nav", css)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn(".grid:not(.grid--game) {\n    grid-template-columns: 1fr;", css)
        self.assertIn("@media (max-width: 900px) {\n  .grid--game { grid-template-columns: 1fr; }", css)
        self.assertIn("overflow-x: auto", css)
