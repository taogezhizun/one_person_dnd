import ast
from pathlib import Path
import re
import unittest
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from one_person_dnd.web.localization import (
    LOCALE_COOKIE,
    Localizer,
    LocaleMiddleware,
    MessageFormatError,
    UnsupportedLocale,
    language_response,
    locale_for,
    localization_context,
    normalize_locale,
    safe_next_path,
)
from one_person_dnd.web.routes.common import templates
from one_person_dnd.web.routes.locale import router as locale_router
from one_person_dnd.web.recalled_context_presenter import present_recalled_context
from one_person_dnd.web.security import UnsafeWriteProtectionMiddleware


class TestLocalizer(unittest.TestCase):
    def test_diagnostic_display_literals_are_owned_by_catalog(self) -> None:
        labels_path = Path("src/one_person_dnd/web/labels.py")
        tree = ast.parse(labels_path.read_text(encoding="utf-8"))
        han = re.compile(r"[\u3400-\u9fff]")

        duplicated_literals = sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and han.search(node.value)
            }
        )

        self.assertEqual(
            duplicated_literals,
            [],
            "diagnostic display copy belongs in localization/catalogs/diagnostics.py",
        )

    def test_localizer_translates_semantic_key(self) -> None:
        self.assertEqual(Localizer("zh-CN")("nav.play"), "游玩")
        self.assertEqual(Localizer("en")("nav.play"), "Play")
        self.assertEqual(
            Localizer("en")("locale.switch_aria", language="中文"),
            "Switch interface language to 中文",
        )

    def test_locale_aliases_and_strict_rejection(self) -> None:
        self.assertEqual(normalize_locale("en-US"), "en")
        self.assertEqual(normalize_locale("zh_Hans"), "zh-CN")
        self.assertEqual(normalize_locale("not-a-locale"), "zh-CN")
        with self.assertRaises(UnsupportedLocale):
            normalize_locale("not-a-locale", strict=True)

    def test_missing_interpolation_value_is_typed(self) -> None:
        localizer = Localizer("en")
        with self.assertRaises(MessageFormatError):
            localizer("common.pending_changes_count")

    def test_direct_route_style_request_defaults_to_chinese(self) -> None:
        self.assertEqual(locale_for(object()).locale, "zh-CN")
        request = SimpleNamespace(state=SimpleNamespace(ui=Localizer("en")))
        self.assertEqual(locale_for(request).locale, "en")

    def test_template_context_localizes_diagnostic_maps(self) -> None:
        request = SimpleNamespace(state=SimpleNamespace(ui=Localizer("en")))
        context = localization_context(request)
        self.assertEqual(context["locale"], "en")
        self.assertEqual(context["action_type_labels"]["exploration"], "Exploration")
        self.assertEqual(context["critic_warning_labels"]["empty_narration"], "Narration is empty")

    def test_all_frozen_adjudication_intents_have_english_labels(self) -> None:
        request = SimpleNamespace(state=SimpleNamespace(ui=Localizer("en")))
        labels = localization_context(request)["adjudication_intent_labels"]

        self.assertEqual(
            labels,
            {
                "用谎言误导对方": "Mislead the target with a lie",
                "迫使对方屈服": "Force the target to yield",
                "改变对方的决定": "Change the target's decision",
                "判断他人的真实意图": "Read another person's true intentions",
                "避免被发现": "Avoid being detected",
                "以灵巧动作克服障碍": "Overcome an obstacle with agility",
                "以力量克服障碍": "Overcome an obstacle with strength",
                "不被察觉地操纵物品": "Manipulate an object without being noticed",
                "打开上锁的装置": "Open a locked mechanism",
                "从线索推导结论": "Draw a conclusion from the clues",
                "发现不明显的线索": "Notice a subtle clue",
                "在野外追踪或求生": "Track or survive in the wild",
                "回忆或辨认奥术知识": "Recall or identify arcane lore",
                "回忆历史知识": "Recall historical lore",
                "辨认自然知识": "Identify natural lore",
                "回忆宗教知识": "Recall religious lore",
                "判断或处理伤病": "Assess or treat an injury",
                "控制或安抚动物": "Control or calm an animal",
                "以表演影响观众": "Influence an audience through performance",
            },
        )

    def test_public_copy_matches_retry_party_and_rules_semantics(self) -> None:
        zh = Localizer("zh-CN")
        en = Localizer("en")

        self.assertEqual(
            en("game.error.attempt_conflict"),
            "This action conflicts with a saved attempt. Edit the draft before sending it again.",
        )
        self.assertEqual(en("new.field.character_count"), "Party size")
        self.assertEqual(en("new.preview.companions"), "Characters")
        self.assertEqual(en("new.preview.companions_heading"), "Your party")
        self.assertEqual(en("home.ancestry_unknown"), "Ancestry undecided")
        self.assertEqual(en("new.preview.role_unknown"), "Class undecided")
        self.assertEqual(
            en(
                "game.turn.roll_formula",
                faces="16",
                selected=16,
                ability="+2",
                proficiency="+2",
                circumstance="+0",
                total=20,
            ),
            "d20 [16], take 16; +2 ability modifier, +2 proficiency bonus, +0 circumstance modifier = 20",
        )
        self.assertEqual(zh("new.field.character_count"), "队伍角色数量")

    def test_recalled_prompt_metadata_gets_an_independent_english_preview(self) -> None:
        raw = [
            {
                "kind": "scene_state",
                "title": "Scene",
                "source": "sessions",
                "status": "included",
                "reason_code": "scene_state",
                "preview": "会话：第一章 当前场景：Moonlit Harbor",
                "preview_data": {
                    "type": "scene",
                    "session_title": "第一章",
                    "current_scene": "Moonlit Harbor",
                },
            },
            {
                "kind": "character_state",
                "title": "Character Sheet",
                "source": "character_sheets",
                "status": "included",
                "reason_code": "character_state",
                "preview": "名称：Elara 种族/职业：Elf / Ranger HP：8/12 状态：Hidden",
                "preview_data": {
                    "type": "character_summary",
                    "name": "Elara",
                    "race": "Elf",
                    "role": "Ranger",
                    "hp": 8,
                    "max_hp": 12,
                    "conditions": ["Hidden"],
                },
            },
            {
                "kind": "world_bible",
                "title": "WorldBible 1",
                "source": "world_bible",
                "preview": "[Location] Moonlit Harbor 标签：harbor,mystery Salt fog hides the docks.",
                "preview_data": {
                    "type": "world_bible",
                    "entry_type": "Location",
                    "title": "Moonlit Harbor",
                    "tags": "harbor,mystery",
                    "content": "Salt fog hides the docks.",
                },
            },
            {
                "kind": "plot_threads",
                "title": "Open Thread 1",
                "source": "plot_threads",
                "preview": "[#7 · P3] Missing courier 标签：main 进展：A boot was found 下一步：Check the lighthouse",
                "preview_data": {
                    "type": "plot_thread",
                    "id": 7,
                    "priority": 3,
                    "title": "Missing courier",
                    "tags": "main",
                    "summary": "A boot was found",
                    "next_step": "Check the lighthouse",
                },
            },
            {
                "kind": "story_memory",
                "title": "Story Memory 1",
                "source": "story_journal",
                "preview": "场景：Dock 摘要：The bell rang 未解决：Missing courier 要点：Red sail",
                "preview_data": {
                    "type": "story_memory",
                    "scene": "Dock",
                    "summary": "The bell rang",
                    "open_threads": "Missing courier",
                    "key_facts": "Red sail",
                },
            },
            {
                "kind": "action_assessment",
                "title": "Action Assessment",
                "source": "action_judge",
                "preview": "action_type: exploration intent: 避免被发现",
                "preview_data": {
                    "type": "action_assessment",
                    "action_type": "exploration",
                    "signals": ["ability_check_resolved"],
                    "warnings": [],
                    "check": {
                        "intent": "避免被发现",
                        "ability": "DEX",
                        "skill": "Stealth",
                        "dc": 15,
                        "total": 20,
                        "outcome": "success",
                    },
                },
            },
        ]

        presented = present_recalled_context(raw, ui=Localizer("en"))

        self.assertEqual(
            presented[0]["display_preview"],
            "Chapter: 第一章 Current scene: Moonlit Harbor",
        )
        self.assertEqual(
            presented[1]["display_preview"],
            "Name: Elara Ancestry / class: Elf / Ranger HP: 8/12 Conditions: Hidden",
        )
        self.assertEqual(
            presented[2]["display_preview"],
            "[Location] Moonlit Harbor Tags: harbor,mystery Salt fog hides the docks.",
        )
        self.assertEqual(
            presented[3]["display_preview"],
            "[#7 · P3] Missing courier Tags: main Progress: A boot was found Next: Check the lighthouse",
        )
        self.assertEqual(
            presented[4]["display_preview"],
            "Scene: Dock Summary: The bell rang Unresolved: Missing courier Key facts: Red sail",
        )
        self.assertEqual(
            presented[5]["display_preview"],
            "Exploration · Ability check resolved · Success · DEX / Stealth · DC 15 · Total 20 · Intent: Avoid being detected",
        )
        self.assertNotIn("preview_data", presented[0])
        self.assertEqual(raw[0]["preview"], "会话：第一章 当前场景：Moonlit Harbor")

    def test_ui_templates_and_browser_code_have_no_hardcoded_chinese(self) -> None:
        paths = list(Path("src/one_person_dnd/web/templates").rglob("*.html"))
        paths.extend(
            [
                Path("src/one_person_dnd/web/static/js/app.js"),
                Path("src/one_person_dnd/web/static/js/turn_stream_state.js"),
                Path("src/one_person_dnd/web/static/js/i18n.js"),
            ]
        )
        han = re.compile(r"[\u3400-\u9fff]")
        offenders = [str(path) for path in paths if han.search(path.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [], "move visible Chinese text into the bilingual catalog")

    def test_literal_translation_calls_reference_catalog_keys(self) -> None:
        roots = [
            Path("src/one_person_dnd/web/templates"),
            Path("src/one_person_dnd/web/routes"),
            Path("src/one_person_dnd/web/static/js"),
        ]
        paths: list[Path] = []
        for root in roots:
            paths.extend(path for path in root.rglob("*") if path.suffix in {".html", ".py", ".js"})
        paths.append(Path("src/one_person_dnd/web/turn_errors.py"))

        patterns = (
            re.compile(r"\bt\(\s*['\"]([^'\"]+)"),
            re.compile(r"\bui\(\s*['\"]([^'\"]+)"),
            re.compile(r"locale_for\([^)]*\)\(\s*['\"]([^'\"]+)"),
            re.compile(r"DndI18n\.t\(\s*['\"`]([^'\"`]+)"),
        )
        referenced: set[str] = set()
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                referenced.update(pattern.findall(text))

        static_keys = {
            key
            for key in referenced
            if not key.endswith(".") and "${" not in key
        }
        catalog = Localizer("en").client_catalog()
        self.assertEqual(sorted(static_keys.difference(catalog)), [])


class TestLocaleWebAdapter(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.add_middleware(UnsafeWriteProtectionMiddleware)
        app.add_middleware(LocaleMiddleware)
        app.include_router(locale_router)

        @app.get("/locale-probe")
        def locale_probe(request: Request) -> JSONResponse:
            ui = locale_for(request)
            return JSONResponse({"locale": ui.locale, "play": ui("nav.play")})

        self.client = TestClient(app)

    def test_cookie_binds_english_for_full_response(self) -> None:
        self.client.cookies.set(LOCALE_COOKIE, "en")
        response = self.client.get("/locale-probe")
        self.assertEqual(response.json(), {"locale": "en", "play": "Play"})
        self.assertEqual(response.headers["content-language"], "en")
        self.assertIn("Cookie", response.headers["vary"])

    def test_page_locale_header_wins_over_cookie(self) -> None:
        self.client.cookies.set(LOCALE_COOKIE, "zh-CN")
        response = self.client.get("/locale-probe", headers={"X-DND-UI-Locale": "en"})
        self.assertEqual(response.json()["locale"], "en")

    def test_invalid_page_locale_header_falls_back_to_chinese(self) -> None:
        self.client.cookies.set(LOCALE_COOKIE, "en")
        response = self.client.get(
            "/locale-probe",
            headers={"X-DND-UI-Locale": "not-a-supported-locale"},
        )
        self.assertEqual(response.json(), {"locale": "zh-CN", "play": "游玩"})

    def test_language_response_sets_cookie_and_rejects_open_redirect(self) -> None:
        response = language_response(locale="en", next_path="https://evil.example/game")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        cookie = response.headers["set-cookie"]
        self.assertIn(f"{LOCALE_COOKIE}=en", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)

    def test_safe_next_path_keeps_local_query(self) -> None:
        self.assertEqual(safe_next_path("/models?created=1"), "/models?created=1")
        self.assertEqual(safe_next_path("//evil.example"), "/")
        self.assertEqual(safe_next_path("/\\evil.example"), "/")

    def test_locale_route_switches_the_next_request_to_english(self) -> None:
        response = self.client.post(
            "/locale",
            data={"locale": "en", "next_path": "/locale-probe"},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/locale-probe")
        follow_up = self.client.get("/locale-probe")
        self.assertEqual(follow_up.json(), {"locale": "en", "play": "Play"})

    def test_locale_route_rejects_cross_origin_form(self) -> None:
        self.client.cookies.set(LOCALE_COOKIE, "en")
        response = self.client.post(
            "/locale",
            data={"locale": "en", "next_path": "/"},
            headers={"Origin": "https://evil.example"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.text, "Cross-site write request rejected.")

    def test_base_template_uses_same_english_catalog_and_html_language(self) -> None:
        app = FastAPI()
        app.add_middleware(LocaleMiddleware)

        @app.get("/")
        def base_page(request: Request):
            return templates.TemplateResponse(request=request, name="base.html", context={})

        client = TestClient(app)
        client.cookies.set(LOCALE_COOKIE, "en")
        response = client.get("/?panel=threads&sort=recent")
        self.assertIn('<html lang="en">', response.text)
        self.assertIn(">Play</a>", response.text)
        self.assertIn(">New Adventure</a>", response.text)
        self.assertIn('value="zh-CN"', response.text)
        self.assertIn('value="/?panel=threads&amp;sort=recent"', response.text)
        self.assertIn('aria-label="Switch interface language to 中文"', response.text)
        self.assertIn("中文", response.text)
        self.assertIn('<script src="/static/js/i18n.js"></script>', response.text)


if __name__ == "__main__":
    unittest.main()
