from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from jinja2 import Environment, FileSystemLoader


class TestUITemplates(unittest.TestCase):
    def test_primary_nav_is_play_first(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        for href, label in (
            ('href="/game"', "游玩"),
            ('href="/new"', "新冒险"),
            ('href="/saves"', "冒险"),
            ('href="/memory/world"', "世界"),
            ('href="/threads"', "剧情线"),
            ('href="/models"', "模型"),
        ):
            self.assertIn(href, base)
            self.assertIn(label, base)
        self.assertNotIn('href="/setup">配置', base)

    def test_base_preconnects_external_script_origin(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('<link rel="preconnect" href="https://unpkg.com" crossorigin />', base)
        self.assertLess(
            base.index('rel="preconnect" href="https://unpkg.com"'),
            base.index('src="https://unpkg.com/htmx.org@1.9.12"'),
        )

    def test_home_model_setup_cta_points_to_models(self) -> None:
        index = Path("src/one_person_dnd/web/templates/index.html").read_text(encoding="utf-8")

        self.assertIn('href="/models"', index)
        self.assertIn("去配置模型", index)
        self.assertNotIn('href="/setup">去配置', index)

    def test_home_prioritizes_continuing_before_creating_new_adventure(self) -> None:
        index = Path("src/one_person_dnd/web/templates/index.html").read_text(encoding="utf-8")

        self.assertIn('href="/new">创建新冒险', index)
        self.assertIn("继续这场冒险", index)
        self.assertLess(index.index('href="/game"'), index.index('href="/new"'))
        self.assertLess(index.index('href="/game"'), index.index('href="/saves"'))

    def test_new_adventure_generation_shows_long_submit_state(self) -> None:
        new = Path("src/one_person_dnd/web/templates/new.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("new-adventure__notice-actions", new)
        self.assertIn('href="/models">去配置模型', new)
        self.assertIn(".new-adventure__notice-actions", css)
        self.assertIn('data-long-submit', new)
        self.assertIn('data-long-submit-label="正在铺开世界……"', new)
        self.assertIn('formaction="/new/propose"', new)
        self.assertIn("帮我想一套", new)
        self.assertIn('data-long-submit-button', new)
        self.assertIn('data-long-submit-status', new)
        self.assertIn("模型正在构思", new)
        self.assertIn("function initLongSubmitForms()", base)
        self.assertIn('querySelectorAll("[data-long-submit]")', base)
        self.assertIn('querySelector("[data-long-submit-button]")', base)
        self.assertIn('querySelector("[data-long-submit-status]")', base)
        self.assertIn("button.disabled = true;", base)
        self.assertIn("status.hidden = false;", base)
        self.assertIn("initLongSubmitForms();", base)
        self.assertIn(".form-status", css)

    def test_new_adventure_preview_summarizes_generated_content(self) -> None:
        template = Path("src/one_person_dnd/web/templates/new_preview.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("new-preview-summary", template)
        self.assertIn("new-preview-summary__grid", template)
        self.assertIn("世界设定", template)
        self.assertIn("同行角色", template)
        self.assertIn("开场地点或局面", template)
        self.assertIn("查看技术数据", template)
        self.assertIn("返回修改", template)
        self.assertNotIn(">放弃<", template)
        self.assertIn(".new-preview-summary", css)
        self.assertIn(".new-preview-summary__grid", css)
        self.assertIn(".lore-preview-grid", css)

    def test_new_adventure_preview_renders_counts_and_character_json(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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
                "character_sheet": {"party": [{"name": "阿洛"}], "notes": "开局在码头"},
            },
            preview_json="{}",
            character_sheet_json='{\n  "party": [\n    {"name": "阿洛"}\n  ]\n}',
        )

        self.assertIn("世界设定", html)
        self.assertIn('class="status-tile__value">2 条</div>', html)
        self.assertIn("同行角色", html)
        self.assertIn('class="status-tile__value">1 名</div>', html)
        self.assertIn("阿洛", html)
        self.assertIn("雾港疑云", html)

    def test_home_uses_adventure_dashboard_visual_shell(self) -> None:
        index = Path("src/one_person_dnd/web/templates/index.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("home-dashboard", index)
        self.assertIn("home-panel home-panel--primary", index)
        self.assertIn("继续上次旅程", index)
        self.assertIn('href="/game">继续这场冒险', index)
        self.assertIn('href="/new">创建新冒险', index)
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('data-skip-link', base)
        self.assertIn("function initSkipLinks()", base)
        self.assertIn('querySelectorAll("[data-skip-link]")', base)
        self.assertIn('target.focus({ preventScroll: true });', base)
        self.assertIn('target.scrollIntoView({ block: "start" });', base)
        self.assertIn("initSkipLinks();", base)

    def test_game_sidebar_uses_adventure_panel_sections(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("冒险面板", game)
        self.assertIn("game-status-strip", game)
        self.assertIn("panel-section", game)
        self.assertIn("角色卡与变更", game)
        self.assertIn("场景与世界", game)
        self.assertIn("剧情与章节", game)
        self.assertIn("系统与高级工具", game)
        self.assertIn("回合诊断", game)

        self.assertLess(game.index('id="character-panel"'), game.index('id="sidebar-form"'))
        self.assertLess(game.index("角色卡与变更"), game.index("场景与世界"))
        self.assertIn('data-system-tools', game)

    def test_game_sidebar_uses_tabbed_adventure_panel(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("panel-tabs", game)
        self.assertIn('role="tablist"', game)
        for tab_id, label, panel_class in (
            ("panel-tab-character", "角色", "panel-tabs__panel--character"),
            ("panel-tab-world", "世界", "panel-tabs__panel--world"),
            ("panel-tab-threads", "剧情", "panel-tabs__panel--threads"),
            ("panel-tab-system", "系统", "panel-tabs__panel--system"),
        ):
            self.assertIn(f'id="{tab_id}"', game)
            self.assertIn(f'for="{tab_id}"', game)
            self.assertIn(label, game)
            self.assertIn(panel_class, game)

        self.assertIn(".panel-tabs__panel {", css)
        self.assertIn("display: none", css)
        self.assertIn("#panel-tab-character:checked", css)
        self.assertIn(".panel-tabs__tab", css)

    def test_game_sidebar_tabs_are_keyboard_accessible(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('role="tablist"', game)
        self.assertIn('role="tab" tabindex="0" aria-selected="true"', game)
        self.assertIn('role="tab" tabindex="-1" aria-selected="false"', game)
        self.assertIn('data-panel-tab="panel-tab-character"', game)
        self.assertIn('aria-controls="panel-character"', game)
        self.assertIn('id="panel-character" role="tabpanel" aria-labelledby="panel-tab-label-character"', game)
        self.assertIn('id="panel-world" role="tabpanel" aria-labelledby="panel-tab-label-world"', game)
        self.assertIn("function initAdventurePanelTabs()", base)
        self.assertIn('querySelectorAll("[data-panel-tab]")', base)
        self.assertIn('tab.setAttribute("aria-selected", checked ? "true" : "false");', base)
        self.assertIn("ArrowRight", base)
        self.assertIn("ArrowLeft", base)
        self.assertIn("Home", base)
        self.assertIn("End", base)
        self.assertIn("targetTab.focus();", base)
        self.assertIn("initAdventurePanelTabs();", base)
        self.assertIn(".panel-tabs__tab:focus-visible", css)

    def test_game_threads_tab_renders_open_plot_threads(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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
        self.assertIn("下一步行动", game)
        self.assertIn('placeholder="描述你的行动…"', game)
        self.assertIn("例如：我特别留意窗外脚步声，或提醒 DM 上回合的一个细节…", game)
        self.assertIn("例如：正在潜行、带着诅咒、某个人物正在同行……", game)
        self.assertIn("世界硬规则/重要关系/禁忌…", game)
        self.assertNotIn('placeholder="描述你的行动..."', game)
        self.assertNotIn("一个细节...", game)
        self.assertNotIn("NPC 正在同行", game)
        self.assertNotIn("禁忌...", game)
        self.assertNotIn("快捷键：Ctrl/Cmd + Enter", game)
        self.assertIn(".action-composer__header", css)
        self.assertIn(".action-composer__kicker", css)

    def test_game_action_surface_guides_player_when_dm_is_not_connected(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

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
        self.assertIn('dataset.llmReady === "0"', base)

    def test_turn_submit_starts_disabled_until_player_enters_action(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        submit_button = re.search(r"<button\b[^>]*data-turn-submit[^>]*>", game, re.S)
        self.assertIsNotNone(submit_button)
        self.assertIn("disabled", submit_button.group(0))
        self.assertIn("const hasText = Boolean(ta && ta.value.trim());", base)
        self.assertIn("submitBtn.disabled = loading || !hasText || !llmReady;", base)
        self.assertIn('ta.addEventListener("input"', base)
        self.assertIn("updateTurnSubmitState(form);", base)

    def test_fresh_game_page_offers_clickable_starter_actions(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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
            "  height: clamp(360px, calc(100vh - 332px), 920px);",
            css,
        )
        self.assertIn("  min-height: 0;", css)
        self.assertIn("overflow: hidden;", css)
        self.assertIn(".chat-card--story-first .chat-history {\n  flex: 1 1 auto;\n  min-height: 0;\n  max-height: none;", css)
        self.assertIn(".chat-card--story-first .play-tools", css)
        self.assertIn(".chat-card--story-first .play-tools {\n  position: static;", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);", css)
        self.assertIn(".chat-card--story-first .action-composer {\n  position: static;", css)
        self.assertIn(".chat-card--story-first .action-composer__controls {\n  grid-column: 2;", css)
        self.assertIn(".chat-card--story-first .quick-roll-panel {\n  padding: 8px 10px;", css)

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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("data-action-jump", game)
        self.assertIn("initActionJump", base)
        self.assertIn("focusPlayerActionInput", base)
        self.assertIn('closest("[data-action-jump]")', base)
        self.assertIn('textarea[name=player_text]', base)
        self.assertIn("ta.focus()", base)
        self.assertIn("setSelectionRange", base)
        self.assertIn('scrollIntoView({ block: "center", behavior: "smooth" })', base)

    def test_turn_action_draft_is_persisted_per_session_until_success(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("TURN_DRAFT_STORAGE_PREFIX", base)
        self.assertIn("function turnDraftKey(form)", base)
        self.assertIn('querySelector("input[name=session_id]")', base)
        self.assertIn("function initTurnDraftPersistence()", base)
        self.assertIn('localStorage.getItem(turnDraftKey(form))', base)
        self.assertIn("function showTurnDraftFeedback()", base)
        self.assertIn('feedback.textContent = "已恢复未发送的行动草稿，可继续编辑或发送";', base)
        self.assertIn(
            "if (saved && !ta.value.trim()) {\n"
            "              ta.value = saved;\n"
            "              resizeAutoGrowTextarea(ta);\n"
            "              showTurnDraftFeedback();\n"
            "            }",
            base,
        )
        self.assertIn('localStorage.setItem(turnDraftKey(form), ta.value)', base)
        self.assertIn('localStorage.removeItem(turnDraftKey(form))', base)
        self.assertIn("initTurnDraftPersistence();", base)
        self.assertIn("let turnSucceeded = false;", base)
        self.assertIn("turnSucceeded = true;", base)
        self.assertIn("if (ta && turnSucceeded)", base)
        self.assertIn("clearTurnDraft(form);", base)

    def test_player_action_textarea_autogrows_without_overrunning_story(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('name="player_text" required data-turn-lockable data-autogrow', game)
        self.assertIn("function resizeAutoGrowTextarea(ta)", base)
        self.assertIn('ta.style.height = "auto";', base)
        self.assertIn("Math.min(ta.scrollHeight, maxHeight)", base)
        self.assertIn('document.querySelectorAll("textarea[data-autogrow]")', base)
        self.assertIn('ta.addEventListener("input", function () {', base)
        self.assertIn("resizeAutoGrowTextarea(ta);", base)
        self.assertIn("initAutoGrowTextareas();", base)
        self.assertIn(".textarea[data-autogrow]", css)
        self.assertIn("max-height: min(34vh, 260px);", css)
        self.assertIn("overflow-y: auto;", css)

    def test_turn_extra_context_draft_is_scoped_and_cleared_after_success(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("STATE_BLOCK_DRAFT_STORAGE_PREFIX", base)
        self.assertIn("function stateBlockDraftKey(form)", base)
        self.assertIn("function clearStateBlockDraft(form)", base)
        self.assertIn("function initStateBlockDraftPersistence()", base)
        self.assertIn('textarea[name=state_block]', base)
        self.assertIn('localStorage.getItem(stateBlockDraftKey(form))', base)
        self.assertIn(
            "if (saved && !stateBlock.value.trim()) {\n"
            "              stateBlock.value = saved;\n"
            "              showTurnContextFeedback(saved.trim());\n"
            "              revealTurnContextInput(stateBlock);\n"
            "            }",
            base,
        )
        self.assertIn('localStorage.setItem(stateBlockDraftKey(form), stateBlock.value)', base)
        self.assertIn('localStorage.removeItem(stateBlockDraftKey(form))', base)
        self.assertIn("initStateBlockDraftPersistence();", base)
        self.assertIn("if (stateBlock && turnSucceeded)", base)
        self.assertIn('stateBlock.value = "";', base)
        self.assertIn("clearStateBlockDraft(form);", base)

    def test_story_first_keeps_empty_advanced_inputs_collapsed_on_restore(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("function hasStateBlockDraft(form)", base)
        self.assertIn('localStorage.getItem(stateBlockDraftKey(form))', base)
        self.assertIn('const compactStory = Boolean(details.closest(".chat-card--story-first"));', base)
        self.assertIn(
            'if (saved === "1" && (!compactStory || hasStateBlockDraft(form))) details.open = true;',
            base,
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("function hasUnsavedTurnDraft(form)", base)
        self.assertIn('form.dataset.turnInFlight === "1"', base)
        self.assertIn('form.querySelector("textarea[name=player_text]")', base)
        self.assertIn('form.querySelector("textarea[name=state_block]")', base)
        self.assertIn("Boolean(playerText && playerText.value.trim())", base)
        self.assertIn("Boolean(stateBlock && stateBlock.value.trim())", base)
        self.assertIn("function initUnsavedTurnWarning()", base)
        self.assertIn('window.addEventListener("beforeunload"', base)
        self.assertIn("if (!hasUnsavedTurnDraft(form)) return;", base)
        self.assertIn("evt.preventDefault();", base)
        self.assertIn('evt.returnValue = "";', base)
        self.assertIn("initUnsavedTurnWarning();", base)

    def test_turn_submit_button_reflects_input_and_loading_state(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("data-turn-submit", game)
        self.assertIn('data-default-label="发送"', game)
        self.assertIn('data-loading-label="发送中…"', game)
        self.assertIn("function updateTurnSubmitState(form)", base)
        self.assertIn("function initTurnSubmitState()", base)
        self.assertIn("form.dataset.turnInFlight", base)
        self.assertIn("submitBtn.textContent = loading ? loadingLabel : defaultLabel", base)
        self.assertIn("submitBtn.disabled = loading || !hasText || !llmReady;", base)
        self.assertIn("ta.addEventListener(\"input\"", base)
        self.assertIn("initTurnSubmitState();", base)
        self.assertIn("updateTurnSubmitState(form);", base)
        self.assertIn(".btn:disabled", css)
        self.assertIn("cursor: not-allowed", css)

    def test_turn_keyboard_shortcut_respects_submit_button_state(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("function submitTurnFormFromShortcut(form)", base)
        self.assertIn("updateTurnSubmitState(form);", base)
        self.assertIn('const submitBtn = form.querySelector("[data-turn-submit]");', base)
        self.assertIn("if (!submitBtn || submitBtn.disabled) return;", base)
        self.assertIn("form.requestSubmit(submitBtn);", base)
        self.assertIn("submitTurnFormFromShortcut(form);", base)
        self.assertNotIn("form.requestSubmit();", base)

    def test_turn_loading_state_is_announced(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('id="turn-loading" class="htmx-indicator spinner" role="status" aria-live="polite"', game)
        self.assertIn('asstContent.setAttribute("role", "status");', base)
        self.assertIn('asstContent.setAttribute("aria-live", "polite");', base)
        self.assertIn("DM 正在思考下一幕…", base)

    def test_turn_request_locks_editable_fields_while_in_flight(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('name="player_text" required data-turn-lockable', game)
        self.assertIn('name="tags" data-turn-lockable', game)
        self.assertIn('name="state_block" data-turn-lockable', game)
        self.assertIn("function setTurnFieldsReadOnly(form, readOnly)", base)
        self.assertIn('querySelectorAll("[data-turn-lockable]")', base)
        self.assertIn("field.readOnly = readOnly;", base)
        self.assertIn('field.setAttribute("aria-readonly", readOnly ? "true" : "false");', base)
        self.assertIn("setTurnFieldsReadOnly(form, inFlight);", base)
        self.assertIn("function isTurnRequestInFlight()", base)
        self.assertIn("if (isTurnRequestInFlight()) return;", base)
        self.assertIn("[data-turn-lockable][readonly]", css)
        self.assertIn("cursor: wait", css)

    def test_streaming_turn_cancel_or_network_failure_replaces_waiting_state(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("function renderTurnRequestNotice(turnEl, title, message, warn)", base)
        self.assertIn('err && err.name === "AbortError"', base)
        self.assertIn('renderTurnRequestNotice(turnEl, "请求已取消"', base)
        self.assertIn("行动草稿已保留，可以修改后重新发送。", base)
        self.assertIn('renderTurnRequestNotice(turnEl, "请求失败"', base)
        self.assertIn('err && err.message ? err.message : "网络连接中断，请稍后重试。"', base)
        self.assertIn('notice.className = warn ? "notice notice--err" : "notice"', base)
        self.assertIn('notice.setAttribute("role", "status");', base)
        self.assertIn('notice.setAttribute("aria-live", "polite");', base)
        self.assertIn("asstMsg.innerHTML = '';", base)

    def test_successful_turn_refreshes_character_review_panel(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")

        self.assertIn("function refreshCharacterPanel()", base)
        self.assertIn('document.getElementById("character-panel")', base)
        self.assertIn('window.htmx.ajax("GET", "/character/panel"', base)
        self.assertIn('target: "#character-panel"', base)
        self.assertIn('swap: "innerHTML"', base)
        self.assertIn("refreshCharacterPanel();", base)
        self.assertLess(base.index("turnSucceeded = true;"), base.index("refreshCharacterPanel();"))
        self.assertIn("function surfacePendingReview(turn)", base)
        self.assertIn("turn && turn.has_pending_review", base)
        self.assertIn('document.querySelector("[data-pending-count]")', base)
        self.assertIn("条 DM 建议待确认。应用前可先查看预览；角色状态和剧情线不会自动改写。", base)
        self.assertIn("data-review-callout", game)
        self.assertIn("data-review-callout-text", game)
        self.assertIn('surfacePendingReview(payload.turn);', base)
        self.assertLess(base.index("refreshCharacterPanel();"), base.index("surfacePendingReview(payload.turn);"))
        self.assertIn("if (evt.detail && evt.detail.successful === false)", base)

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
        self.assertIn("<summary>高级选项</summary>", game)
        self.assertNotIn("高级选项（标签 / 额外上下文，可选）", game)

    def test_quick_roll_result_can_be_applied_to_turn_context(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
        template = env.get_template("partials/roll_result.html")
        html = template.render(event={"expr": "1d20+5", "rolls": [13], "modifier": 5, "total": 18})
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('hx-post="/game/roll"', game)
        self.assertIn('hx-indicator="#quick-roll-loading"', game)
        quick_roll_input = re.search(r'<input\b[^>]*name="roll_expr_text"[^>]*>', game, re.S)
        self.assertIsNotNone(quick_roll_input)
        quick_roll_attrs = quick_roll_input.group(0)
        self.assertIn("required", quick_roll_attrs)
        self.assertIn('aria-label="掷骰表达式"', quick_roll_attrs)
        self.assertIn('autocomplete="off"', quick_roll_attrs)
        self.assertIn('id="quick-roll-loading"', game)
        self.assertIn('id="quick-roll-loading" class="htmx-indicator spinner" role="status" aria-live="polite"', game)
        self.assertIn("掷骰中…", game)
        self.assertIn('class="htmx-indicator spinner"', game)
        self.assertIn('id="quick-roll-result" class="muted quick-roll-panel__result" role="status" aria-live="polite"', game)
        self.assertIn("data-roll-context", html)
        self.assertIn("带入本回合线索", html)
        self.assertIn("掷骰结果：1d20+5", html)
        self.assertIn("[13]", html)
        self.assertIn("= 18", html)
        self.assertIn("initRollContextActions", base)
        self.assertIn('closest("[data-roll-context]")', base)
        self.assertIn('textarea[name=state_block]', base)
        self.assertIn("data-turn-context-feedback", game)
        self.assertIn("function showTurnContextFeedback(context)", base)
        self.assertIn("function hideTurnContextFeedback()", base)
        self.assertIn('document.querySelector("[data-turn-context-feedback]")', base)
        self.assertIn('feedback.textContent = "已带入本回合线索：" + context;', base)
        self.assertIn("function revealTurnContextInput(stateBlock)", base)
        self.assertIn('const advanced = stateBlock.closest("[data-advanced-inputs]");', base)
        self.assertIn("advanced.open = true;", base)
        self.assertIn('localStorage.setItem(ADVANCED_STORAGE_KEY, "1");', base)
        self.assertIn('stateBlock.focus({ preventScroll: true });', base)
        self.assertIn('stateBlock.scrollIntoView({ block: "center", behavior: "smooth" });', base)
        self.assertIn('const contextLines = current.split("\\n").map((line) => line.trim()).filter(Boolean);', base)
        self.assertIn("if (contextLines.includes(context)) {", base)
        self.assertIn('showTurnContextFeedback("该线索已在本回合上下文中");', base)
        self.assertIn('btn.textContent = "已带入过"', base)
        self.assertIn("hideTurnContextFeedback();", base)
        self.assertNotIn("turnContextFeedbackTimer", base)
        self.assertIn('btn.textContent = "已带入线索"', base)
        self.assertIn("window.setTimeout", base)
        self.assertIn("btn.disabled = true", base)
        self.assertIn(".action-composer__context-feedback", css)
        self.assertIn(".roll-result__actions", css)

    def test_quick_roll_submit_starts_disabled_until_expression_is_entered(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        quick_roll_input = re.search(r'<input\b[^>]*name="roll_expr_text"[^>]*>', game, re.S)
        quick_roll_button = re.search(r'<button\b[^>]*data-quick-roll-submit[^>]*>', game, re.S)
        self.assertIsNotNone(quick_roll_input)
        self.assertIsNotNone(quick_roll_button)
        self.assertIn("data-quick-roll-input", quick_roll_input.group(0))
        self.assertIn("disabled", quick_roll_button.group(0))
        self.assertIn("function updateQuickRollSubmitState(form)", base)
        self.assertIn('form.querySelector("[data-quick-roll-input]")', base)
        self.assertIn('form.querySelector("[data-quick-roll-submit]")', base)
        self.assertIn("submitBtn.disabled = loading || !hasExpr;", base)
        self.assertIn("function initQuickRollSubmitState()", base)
        self.assertIn('input.addEventListener("input"', base)
        self.assertIn("initQuickRollSubmitState();", base)

    def test_quick_roll_submit_locks_while_request_is_in_flight(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('form.dataset.quickRollInFlight === "1"', base)
        self.assertIn("submitBtn.disabled = loading || !hasExpr;", base)
        self.assertIn("function setQuickRollRequestUI(form, inFlight)", base)
        self.assertIn('form.dataset.quickRollInFlight = inFlight ? "1" : "0";', base)
        self.assertIn('elt.querySelector("[data-quick-roll-submit]")', base)
        self.assertIn("setQuickRollRequestUI(elt, true);", base)
        self.assertIn("setQuickRollRequestUI(elt, false);", base)

    def test_quick_roll_input_is_readonly_while_request_is_in_flight(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('const input = form.querySelector("[data-quick-roll-input]");', base)
        self.assertIn("input.readOnly = inFlight;", base)
        self.assertIn('input.setAttribute("aria-readonly", inFlight ? "true" : "false");', base)
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
            "  height: clamp(360px, calc(100vh - 332px), 920px);",
            css,
        )
        self.assertIn("  min-height: 0;", css)
        self.assertIn(".chat-card--story-first .chat-history {\n  flex: 1 1 auto;\n  min-height: 0;\n  max-height: none;", css)
        self.assertIn(".chat-card--story-first .play-tools {\n  position: static;", css)
        self.assertIn(".chat-card--story-first .action-composer .textarea {\n  min-height: 56px;", css)

    def test_short_desktop_story_first_does_not_clip_action_loop(self) -> None:
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("@media (min-width: 981px) and (max-height: 760px) {", css)
        self.assertIn(
            ".chat-card--story-first {\n"
            "    height: auto;\n"
            "    overflow: visible;\n"
            "  }",
            css,
        )
        self.assertIn(
            ".chat-card--story-first .chat-history {\n"
            "    flex: 0 0 auto;\n"
            "    height: clamp(180px, 26vh, 190px);\n"
            "    min-height: clamp(180px, 26vh, 190px);\n"
            "    max-height: clamp(180px, 26vh, 190px);\n"
            "  }",
            css,
        )

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
        self.assertIn("    grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);", css)
        self.assertIn(".chat-card--story-first .play-tools .action-composer {\n    padding: 6px;", css)
        self.assertIn(".chat-card--story-first .play-tools .action-composer .textarea {\n    min-height: 48px;", css)
        self.assertIn(".chat-card--story-first .play-tools .quick-roll-panel {\n    padding: 7px 8px;", css)
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

    def test_game_layout_exposes_resizable_desktop_split(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('data-game-layout', game)
        self.assertIn('data-game-layout-resizer', game)
        self.assertIn('role="separator"', game)
        self.assertIn('aria-orientation="vertical"', game)
        self.assertIn("调整故事对话和冒险面板宽度", game)
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('const GAME_LAYOUT_WIDTH_STORAGE_PREFIX = "one_person_dnd.gameSidebarWidth.";', base)
        self.assertIn("function initGameLayoutResizer()", base)
        self.assertIn('querySelector("[data-game-layout]")', base)
        self.assertIn('querySelector("[data-game-layout-resizer]")', base)
        self.assertIn('querySelector("[data-game-layout-reset]")', base)
        self.assertIn('--game-sidebar-width', base)
        self.assertIn('localStorage.setItem(gameLayoutStorageKey(grid),', base)
        self.assertIn('localStorage.removeItem(gameLayoutStorageKey(grid));', base)
        self.assertIn('resizer.addEventListener("pointerdown"', base)
        self.assertIn('resizer.addEventListener("dblclick"', base)
        self.assertIn('evt.key === "ArrowLeft"', base)
        self.assertIn("initGameLayoutResizer();", base)

    def test_chat_history_exposes_corner_height_resizer(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn('class="chat-history-shell"', game)
        self.assertIn('data-chat-history-shell', game)
        self.assertIn('data-chat-history-resizable', game)
        self.assertIn('data-chat-history-resizer', game)
        self.assertIn('aria-label="调整故事记录高度"', game)
        self.assertIn('aria-orientation="horizontal"', game)
        self.assertIn('title="拖拽调整高度，双击复位"', game)
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('const CHAT_HISTORY_HEIGHT_STORAGE_PREFIX = "one_person_dnd.chatHistoryHeight.";', base)
        self.assertIn("function initChatHistoryResizer()", base)
        self.assertIn('querySelector("[data-chat-history-resizable]")', base)
        self.assertIn('querySelector("[data-chat-history-resizer]")', base)
        self.assertIn("function canResizeChatHistory(resizer)", base)
        self.assertIn('chat.style.setProperty("--chat-history-height", nextHeight + "px");', base)
        self.assertIn('localStorage.setItem(chatHistoryHeightStorageKey(),', base)
        self.assertIn('localStorage.removeItem(chatHistoryHeightStorageKey());', base)
        self.assertIn('resizer.addEventListener("pointerdown"', base)
        self.assertIn('resizer.addEventListener("dblclick"', base)
        self.assertIn('evt.key !== "ArrowUp" && evt.key !== "ArrowDown"', base)
        self.assertIn("resetChatHistoryHeight(chat);", base)
        self.assertIn("initChatHistoryResizer();", base)

    def test_game_page_surfaces_pending_review_callout(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("review-callout", game)
        self.assertIn("待审状态 / 剧情线更新", game)
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
        self.assertIn("这局还没有世界观", game)
        self.assertIn('href="/new"', game)
        self.assertIn('href="/memory/world/new"', game)
        self.assertIn('action="/game/world-setup/skip"', game)
        self.assertIn("继续空白开局", game)
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
        self.assertLess(template.index("已有模型"), template.index("添加模型"))
        self.assertIn(".model-profile-library", css)
        self.assertIn(".model-profile-card--active", css)

    def test_key_forms_use_explicit_labels_and_safe_autocomplete(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        models = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")
        new = Path("src/one_person_dnd/web/templates/new.html").read_text(encoding="utf-8")
        character_panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")
        saves = Path("src/one_person_dnd/web/templates/saves.html").read_text(encoding="utf-8")

        self.assertIn('textarea class="input textarea" name="player_text" required data-turn-lockable data-autogrow autocomplete="off"', game)
        self.assertIn('input class="input" name="tags" data-turn-lockable autocomplete="off"', game)
        self.assertIn('textarea class="input textarea" name="state_block" data-turn-lockable autocomplete="off"', game)
        self.assertIn('select class="input input--compact" name="session_id" aria-label="切换章节" autocomplete="off"', game)
        self.assertIn('input class="input" name="current_scene" value="{{ current_scene }}" autocomplete="off"', game)

        self.assertIn('id="deepseek-profile-name"', models)
        self.assertIn('id="deepseek-api-key"', models)
        self.assertIn('type="password" name="api_key" required autocomplete="new-password"', models)
        self.assertIn('type="url" name="base_url" required autocomplete="url"', models)
        self.assertIn('name="model" required autocomplete="off" spellcheck="false"', models)
        self.assertIn('type="number" step="0.1" name="timeout_seconds"', models)

        self.assertIn('id="adventure-genre"', new)
        self.assertIn('type="number" name="character_count"', new)
        self.assertIn('placeholder="例如：世界里不能复活；主角必须是半精灵游侠；开局在雪国小镇……"', new)

        self.assertIn('input class="input input--compact" type="number" inputmode="numeric" name="hp_delta" value="0" autocomplete="off"', character_panel)
        self.assertIn('input class="input input--compact" type="number" inputmode="numeric" name="gold_delta" value="0" autocomplete="off"', character_panel)
        self.assertIn('input class="input" name="reason" autocomplete="off" placeholder="例如：剧情奖励 / 惩罚 / 测试分支"', character_panel)
        self.assertIn('textarea class="input textarea" name="conditions_text" autocomplete="off"', character_panel)
        self.assertIn('textarea class="input textarea" name="inventory_text" autocomplete="off"', character_panel)
        self.assertIn('textarea class="input textarea" name="notes_text" autocomplete="off"', character_panel)
        self.assertIn('textarea class="input textarea" name="character_sheet" autocomplete="off" spellcheck="false"', character_panel)

        self.assertIn('id="blank-adventure-name" class="input" name="name" required autocomplete="off"', saves)
        self.assertIn('id="new-chapter-title" class="input" name="title" required autocomplete="off"', saves)
        self.assertIn('id="new-chapter-scene" class="input" name="current_scene" value="起始" autocomplete="off"', saves)
        self.assertIn('name="snapshot_name" autocomplete="off" placeholder="例如：进入钟楼前"', saves)
        self.assertIn('class="input input--compact" name="fork_title" autocomplete="off" placeholder="故事分支标题（可选）"', saves)

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

        self.assertIn("条 DM 建议待确认。应用前可先查看预览；角色状态和剧情线不会自动改写。", game)
        self.assertIn(
            "@media (max-width: 900px) {\n"
            "  .grid--game { grid-template-columns: 1fr; }\n"
            "  .game-layout-resizer { display: none; }\n"
            "  .sidebar-card { max-height: none; overflow: visible; position: static; }\n"
            "}\n\n"
            "@media (max-width: 1320px) {\n"
            "  .game-status-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin-top: 8px; }\n"
            "  .status-tile { padding: 6px 8px; }\n"
            "  .status-tile__label { display: block; }\n"
            "  .status-tile__value { font-size: 0.9rem; line-height: 1.25; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }\n"
            "  .review-callout { gap: 10px; margin-top: 8px; padding: 8px 10px; }\n",
            css,
        )

    def test_character_panel_shows_summary_before_advanced_json(self) -> None:
        panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")

        self.assertIn("角色概览", panel)
        self.assertIn("character_summary", panel)
        self.assertIn("变更预览", panel)
        self.assertIn("change-preview", panel)
        self.assertIn("preview.lines", panel)
        self.assertIn("角色卡 JSON（高级）", panel)
        self.assertIn("<details", panel)
        self.assertNotIn('class="card"', panel)

    def test_character_panel_surfaces_notice_before_controls(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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

        for indicator_id, text in (
            ("quick-adjust-saving", "应用中…"),
            ("quick-state-saving", "保存中…"),
            ("character-saving", "保存中…"),
        ):
            self.assertIn(f'hx-indicator="#{indicator_id}"', panel)
            self.assertIn(
                f'id="{indicator_id}" class="htmx-indicator spinner form-status" role="status" aria-live="polite">{text}</span>',
                panel,
            )

        self.assertIn('id="character-save-result" role="status" aria-live="polite"', panel)
        self.assertIn('hx-indicator="#change-apply-saving-{{ c.id }}"', panel)
        self.assertIn('id="change-apply-saving-{{ c.id }}" class="htmx-indicator spinner form-status" role="status" aria-live="polite">应用中…</span>', panel)
        self.assertIn('hx-indicator="#change-reject-saving-{{ c.id }}"', panel)
        self.assertIn('id="change-reject-saving-{{ c.id }}" class="htmx-indicator spinner form-status" role="status" aria-live="polite">拒绝中…</span>', panel)

    def test_character_panel_renders_abilities_conditions_and_notes_form(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        panel = Path("src/one_person_dnd/web/templates/partials/character_panel.html").read_text(encoding="utf-8")

        self.assertIn("data-character-pending-count", panel)
        self.assertIn("function syncPendingReviewCountFromPanel()", base)
        self.assertIn('document.querySelector("[data-character-pending-count]")', base)
        self.assertIn("setPendingReviewCount(count);", base)
        self.assertIn('if (evt.target && evt.target.id === "character-panel")', base)
        self.assertIn("syncPendingReviewCountFromPanel();", base)

    def test_models_edit_form_does_not_render_saved_api_key_value(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")

        self.assertNotIn('value="{{ profile.api_key', template)
        self.assertNotIn('value="{{ p.api_key', template)
        self.assertIn('placeholder="留空则保持原密钥"', template)
        self.assertIn('type="password" name="api_key"', template)

    def test_models_test_action_shows_progress_indicator(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")

        self.assertIn('hx-post="/models/test"', template)
        self.assertIn('hx-target="#test-result-{{ profile.id }}"', template)
        self.assertIn('hx-indicator="#test-loading-{{ profile.id }}"', template)
        self.assertIn('id="test-loading-{{ profile.id }}"', template)
        self.assertIn("测试中……", template)
        self.assertIn('class="htmx-indicator spinner"', template)

    def test_dm_choices_are_clickable_actions(self) -> None:
        partial = Path("src/one_person_dnd/web/templates/partials/chat_turn.html").read_text(encoding="utf-8")
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("data-choice-action", partial)
        self.assertIn("data-choice-text", partial)
        self.assertIn('aria-pressed="false"', partial)
        self.assertIn("choice-action", partial)
        self.assertIn("data-choice-action", base)
        self.assertIn("initChoiceActions", base)
        self.assertIn("function clearSelectedChoiceActions()", base)
        self.assertIn("function selectChoiceAction(btn)", base)
        self.assertIn('querySelectorAll("[data-choice-action][aria-pressed=\'true\']")', base)
        self.assertIn('btn.setAttribute("aria-pressed", "true");', base)
        self.assertIn("choice-action--selected", base)
        self.assertIn("dataset.choiceText", base)
        self.assertIn("data-choice-feedback", base)
        self.assertIn("function showChoiceActionFeedback()", base)
        self.assertIn("已填入行动，可直接发送", base)
        self.assertIn("data-choice-feedback", game)
        self.assertIn('role="status"', game)
        self.assertIn(".action-composer__feedback", css)
        self.assertIn('textarea[name=player_text]', base)
        self.assertIn(".choice-action", css)
        self.assertIn(".choice-action:focus-visible", css)
        self.assertIn("outline: 2px solid var(--parchment);", css)
        self.assertNotIn(".choice-action:focus {\n  border-color: var(--accent);\n  background: rgba(122, 162, 247, 0.13);\n  outline: none;", css)
        self.assertIn(".choice-action--selected", css)

    def test_manual_action_edit_clears_selected_choice_state(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("function syncSelectedChoiceWithInput(form)", base)
        self.assertIn('document.querySelector("[data-choice-action][aria-pressed=\'true\']")', base)
        self.assertIn("const currentText = ta && ta.value ? ta.value.trim() : \"\";", base)
        self.assertIn("const selectedText = (selected.dataset.choiceText || selected.textContent || \"\").trim();", base)
        self.assertIn("if (!currentText || selectedText !== currentText) clearSelectedChoiceActions();", base)
        self.assertIn("syncSelectedChoiceWithInput(form);", base)

    def test_successful_turn_clears_selected_choice_state(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn(
            'if (ta && turnSucceeded) {\n'
            '                  ta.value = "";\n'
            '                  resizeAutoGrowTextarea(ta);\n'
            '                  clearSelectedChoiceActions();',
            base,
        )
        self.assertIn(
            'if (ta) {\n'
            '            ta.value = "";\n'
            '            resizeAutoGrowTextarea(ta);\n'
            '            clearSelectedChoiceActions();\n'
            '          }',
            base,
        )

    def test_starter_actions_share_choice_selected_state(self) -> None:
        game = Path("src/one_person_dnd/web/templates/game.html").read_text(encoding="utf-8")
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('data-choice-action aria-pressed="false"', game)
        self.assertIn("selectChoiceAction(btn);", base)

    def test_chat_turn_renders_action_assessment_for_new_turns(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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

    def test_turn_diagnostics_renders_dm_critic_warnings_outside_story(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("action_assessment", base)
        self.assertIn("action-assessment", base)
        self.assertIn("系统判定", base)
        self.assertIn("ACTION_TYPE_LABELS", base)
        self.assertIn("ACTION_SIGNAL_LABELS", base)
        self.assertIn("ACTION_WARNING_LABELS", base)
        self.assertIn("可能需要掷骰", base)
        self.assertIn("行动描述已包含结果", base)

    def test_streaming_renderer_places_dice_events_with_player_action(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('const userMsg = turnEl.querySelector(".chat__msg--user");', base)
        self.assertIn("const diceEvents = (turn && turn.dice_events) || [];", base)
        self.assertIn("if (userMsg && diceEvents && diceEvents.length > 0) {", base)
        self.assertIn("userMsg.appendChild(wrap);", base)
        self.assertLess(base.index("renderActionAssessment(userMsg"), base.index("const diceEvents ="))
        self.assertLess(
            base.index("userMsg.appendChild(wrap);"),
            base.index('const asstMsg = turnEl.querySelector(".chat__msg--assistant");'),
        )
        self.assertNotIn(
            "asstMsg.appendChild(wrap);\n"
            "          }\n\n"
            "          const narration",
            base,
        )

    def test_streaming_turn_skeleton_shows_and_clears_waiting_state(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("streaming-wait", base)
        self.assertIn("DM 正在思考下一幕", base)
        self.assertIn('asstContent.dataset.waiting = "1"', base)
        self.assertIn('asstContent.textContent = ""', base)
        self.assertIn('asstContent.classList.remove("streaming-wait", "spinner")', base)
        self.assertLess(base.index('asstContent.textContent = ""'), base.index('asstContent.textContent += payload.text || ""'))
        self.assertIn(".streaming-wait", css)

    def test_streaming_renderer_outputs_dm_critic_warnings(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("critic_warnings", base)
        self.assertIn("dm-review", base)
        self.assertIn("DM 审查", base)
        self.assertIn("CRITIC_WARNING_LABELS", base)
        self.assertIn("选项数量不适合继续游玩", base)

    def test_streaming_renderer_outputs_response_warnings(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("response_warnings", base)
        self.assertIn("response-review", base)
        self.assertIn("反应评估", base)
        self.assertIn("RESPONSE_WARNING_LABELS", base)
        self.assertIn("选项重复", base)
        self.assertIn("选项过于笼统", base)

    def test_chat_turn_append_renders_recalled_context_preview(self) -> None:
        env = Environment(loader=FileSystemLoader("src/one_person_dnd/web/templates"), autoescape=True)
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

        self.assertIn('<div class="muted recall-preview-title">本回合参考</div>', game)
        self.assertIn(
            "（发送一次行动后显示 DM 使用的角色、世界、剧情线、故事记忆、掷骰和行动判定）",
            game,
        )
        self.assertNotIn("本回合召回设定", game)
        self.assertNotIn("发送一次行动后显示命中的 WorldBible 条目", game)

    def test_streaming_renderer_outputs_recalled_context_preview(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn("recalled_context", base)
        self.assertIn("renderRecalledContext", base)
        self.assertIn("本回合参考", base)
        self.assertIn("已裁剪", base)
        self.assertIn("recall-stack", base)

    def test_streaming_renderer_splits_real_sse_newlines(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('buf.split("\\n\\n")', base)
        self.assertIn('chunk.split("\\n").filter(Boolean)', base)
        self.assertNotIn('buf.split("\\\\n\\\\n")', base)
        self.assertNotIn('chunk.split("\\\\n").filter(Boolean)', base)

    def test_base_inline_script_uses_valid_plain_js_quotes(self) -> None:
        base = Path("src/one_person_dnd/web/templates/base.html").read_text(encoding="utf-8")

        self.assertNotIn('document.getElementById(\\"', base)
        self.assertNotIn('document.createElement(\\"', base)
        self.assertNotIn('document.querySelector(\\"', base)
        self.assertNotIn('form.querySelector(\\"', base)
        self.assertNotIn('addEventListener(\\n            \\"', base)

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
