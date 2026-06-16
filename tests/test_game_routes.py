import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from one_person_dnd.config import LLMConfig
from one_person_dnd.db.repos import campaigns, plot_threads, sessions, state_change_requests
from one_person_dnd.db.schema import init_db
from one_person_dnd.db.conn import get_connection
from one_person_dnd.domain.actions import ActionAssessment
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import ChatMessage
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import game


class TestGameRoutes(unittest.TestCase):
    def _paths_with_session(self) -> tuple[tempfile.TemporaryDirectory, AppPaths, int, int]:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        db_path = app_dir / "one_person_dnd.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
            conn.commit()
        finally:
            conn.close()
        paths = AppPaths(
            project_root=root,
            app_dir=app_dir,
            config_path=root / "api_config.ini",
            db_path=db_path,
        )
        return tmp, paths, campaign_id, session_id

    def test_build_turn_prompt_overrides_do_not_duplicate_session_context(self) -> None:
        helper = getattr(game, "_build_turn_prompt_overrides", None)
        self.assertIsNotNone(helper)

        turn_context, cheat_prompt = helper(
            cheat_enabled=False,
            cheat_prompt="秘密优势",
            state_block="我小心行动",
        )

        self.assertEqual(turn_context, "我小心行动")
        self.assertNotIn("秘密优势", turn_context)
        self.assertEqual(cheat_prompt, "")

    def test_build_turn_prompt_overrides_keeps_enabled_cheat_separate(self) -> None:
        turn_context, cheat_prompt = game._build_turn_prompt_overrides(
            cheat_enabled=True,
            cheat_prompt="允许一次命运改写",
            state_block="  我检查门缝  ",
        )

        self.assertEqual(turn_context, "我检查门缝")
        self.assertEqual(cheat_prompt, "允许一次命运改写")

    def test_game_page_context_includes_open_plot_threads(self) -> None:
        tmp, paths, campaign_id, session_id = self._paths_with_session()
        conn = get_connection(paths.db_path)
        try:
            plot_threads.create_thread(
                conn,
                session_id=session_id,
                title="追踪银钥匙",
                priority=2,
                summary="银钥匙来自旧码头。",
                next_step="询问酒馆老板娘。",
                tags="主线,钥匙",
            )
            closed_id = plot_threads.create_thread(
                conn,
                session_id=session_id,
                title="已结束线索",
                priority=5,
                summary="这条不该显示。",
                next_step="",
                tags="旧",
            )
            plot_threads.set_status(conn, thread_id=closed_id, session_id=session_id, status="closed")
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.game.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.game.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.game.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = game.game(request=object())

            self.assertEqual([t["title"] for t in context["open_threads"]], ["追踪银钥匙"])
            self.assertEqual(context["open_threads"][0]["next_step"], "询问酒馆老板娘。")
        finally:
            tmp.cleanup()

    def test_game_page_context_exposes_llm_readiness(self) -> None:
        tmp, paths, campaign_id, session_id = self._paths_with_session()

        try:
            with (
                patch("one_person_dnd.web.routes.game.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.game.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.game.load_active_llm_config", return_value=None),
                patch("one_person_dnd.web.routes.game.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = game.game(request=object())

            self.assertFalse(context["llm_configured"])
        finally:
            tmp.cleanup()

    def test_non_streaming_turn_uses_turn_pipeline(self) -> None:
        tmp, paths, campaign_id, session_id = self._paths_with_session()
        protocol = "\n".join(
            [
                "===NARRATION===",
                "门开了。",
                "===CHOICES===",
                "- 进入",
                "===DM_NOTES===",
                "ok",
                "===MEMORY===",
                "开门。",
            ]
        )

        class RecordingPipeline:
            used = False
            captured_state_block = None

            def __init__(self, *, dm_client) -> None:
                self.dm_client = dm_client

            def run_non_streaming(self, conn, *, action, memory_cfg, state_block="", cheat_prompt=""):
                RecordingPipeline.used = True
                RecordingPipeline.captured_state_block = state_block
                return SimpleNamespace(
                    turn_index=0,
                    dm_raw_text=protocol,
                    dm=parse_dm_text(protocol),
                    recalled_world=[],
                    recalled_context=[
                        {
                            "kind": "action_assessment",
                            "title": "Action Assessment",
                            "source": "action_judge",
                            "reason": "评估玩家行动风险与掷骰需求。",
                            "preview": "action_type: social",
                        }
                    ],
                    dice_events=[],
                    critic_warnings=["choice_count_out_of_range"],
                    response_warnings=["duplicate_choices"],
                    action_assessment=ActionAssessment(
                        action_type="social",
                        dice_events=[],
                        signals=["roll_may_be_needed"],
                        warnings=["declared_success"],
                    ),
                )

        try:
            with (
                patch("one_person_dnd.web.routes.game.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.game.load_active_llm_config",
                    return_value=LLMConfig(base_url="http://example.test/v1", api_key="k", model="m"),
                ),
                patch("one_person_dnd.web.routes.game.create_llm_client", return_value=object()),
                patch("one_person_dnd.web.routes.game.TurnPipeline", RecordingPipeline, create=True),
                patch("one_person_dnd.web.routes.game.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = game.game_turn(
                    request=object(),
                    campaign_id=campaign_id,
                    session_id=session_id,
                    player_text="我推开门",
                    tags="门厅",
                    state_block="只记录本回合额外线索",
                )

            self.assertTrue(RecordingPipeline.used)
            self.assertEqual(RecordingPipeline.captured_state_block, "只记录本回合额外线索")
            self.assertEqual(context["turn"]["dm"].narration, "门开了。")
            self.assertEqual(context["turn"]["action_assessment"]["action_type"], "social")
            self.assertEqual(context["turn"]["action_assessment"]["warnings"], ["declared_success"])
            self.assertEqual(context["turn"]["critic_warnings"], ["choice_count_out_of_range"])
            self.assertEqual(context["turn"]["response_warnings"], ["duplicate_choices"])
            self.assertEqual(context["recalled_context"][0]["kind"], "action_assessment")
        finally:
            tmp.cleanup()

    def test_non_streaming_turn_marks_pending_review_when_dm_suggests_state_change(self) -> None:
        tmp, paths, campaign_id, session_id = self._paths_with_session()
        protocol = "\n".join(
            [
                "===NARRATION===",
                "陷阱划伤了你的手臂。",
                "===CHOICES===",
                "- 检查伤口",
                "- 继续前进",
                "===DM_NOTES===",
                "state delta",
                "===MEMORY===",
                "玩家在门厅受伤。",
                "===STATE_DELTA===",
                '{"party":[{"hp":7}]}',
            ]
        )

        class RecordingPipeline:
            def __init__(self, *, dm_client) -> None:
                self.dm_client = dm_client

            def run_non_streaming(self, conn, *, action, memory_cfg, state_block="", cheat_prompt=""):
                return SimpleNamespace(
                    turn_index=0,
                    dm_raw_text=protocol,
                    dm=parse_dm_text(protocol),
                    recalled_world=[],
                    recalled_context=[],
                    dice_events=[],
                    critic_warnings=[],
                    response_warnings=[],
                    action_assessment=None,
                )

        try:
            with (
                patch("one_person_dnd.web.routes.game.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.game.load_active_llm_config",
                    return_value=LLMConfig(base_url="http://example.test/v1", api_key="k", model="m"),
                ),
                patch("one_person_dnd.web.routes.game.create_llm_client", return_value=object()),
                patch("one_person_dnd.web.routes.game.TurnPipeline", RecordingPipeline, create=True),
                patch("one_person_dnd.web.routes.game.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = game.game_turn(
                    request=object(),
                    campaign_id=campaign_id,
                    session_id=session_id,
                    player_text="我继续前进",
                    tags="",
                    state_block="",
                )

            self.assertTrue(context["turn"]["has_pending_review"])
        finally:
            tmp.cleanup()

    def test_streaming_turn_prepares_messages_through_pipeline(self) -> None:
        tmp, paths, campaign_id, session_id = self._paths_with_session()
        protocol = "\n".join(
            [
                "===NARRATION===",
                "门开了。",
                "===CHOICES===",
                "- 进入",
                "===DM_NOTES===",
                "ok",
                "===MEMORY===",
                "开门。",
            ]
        )

        class FakeStreamClient:
            def chat_stream_sse(self, messages):
                yield protocol

        class RecordingStateKeeper:
            def persist(
                self,
                conn,
                *,
                session_id,
                player_text,
                dm_raw,
                dm_struct,
                recalled_world,
                dice_events,
                recalled_context=None,
            ):
                return SimpleNamespace(
                    turn_index=0,
                    dm_raw_text=dm_raw,
                    dm=dm_struct,
                    recalled_world=recalled_world,
                    recalled_context=[
                        {
                            "kind": "world_bible",
                            "title": "WorldBible 1",
                            "source": "world_bible",
                            "reason": "匹配玩家填写的标签。",
                            "preview": "门厅",
                        }
                    ],
                    dice_events=dice_events,
                    critic_warnings=["choice_count_out_of_range"],
                    response_warnings=["non_actionable_choice"],
                )

        class RecordingPipeline:
            prepared = False

            def __init__(self, *, dm_client) -> None:
                self.dm_client = dm_client
                self.state_keeper = RecordingStateKeeper()

            def prepare_messages(self, conn, *, action, memory_cfg, state_block="", cheat_prompt=""):
                RecordingPipeline.prepared = True
                return (
                    [ChatMessage(role="user", content=action.text)],
                    [{"title": "门厅"}],
                    [
                        {
                            "kind": "world_bible",
                            "title": "WorldBible 1",
                            "source": "world_bible",
                            "reason": "匹配玩家填写的标签。",
                            "preview": "门厅",
                        }
                    ],
                    [],
                    ActionAssessment(
                        action_type="exploration",
                        dice_events=[],
                        signals=["roll_may_be_needed"],
                        warnings=[],
                    ),
                )

            def persist_dm_output(
                self,
                conn,
                *,
                action,
                dm_raw,
                recalled_world,
                dice_events,
                recalled_context=None,
                action_assessment=None,
            ):
                dm_struct = parse_dm_text(dm_raw)
                result = self.state_keeper.persist(
                    conn,
                    session_id=action.session_id,
                    player_text=action.text,
                    dm_raw=dm_raw,
                    dm_struct=dm_struct,
                    recalled_world=recalled_world,
                    dice_events=dice_events,
                    recalled_context=recalled_context,
                )
                result.action_assessment = action_assessment
                return result

        async def collect_body(response) -> str:
            chunks: list[str] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
            return "".join(chunks)

        try:
            with (
                patch("one_person_dnd.web.routes.game.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.game.load_active_llm_config",
                    return_value=LLMConfig(base_url="http://example.test/v1", api_key="k", model="m"),
                ),
                patch("one_person_dnd.web.routes.game.create_llm_client", return_value=FakeStreamClient()),
                patch("one_person_dnd.web.routes.game.TurnPipeline", RecordingPipeline, create=True),
            ):
                response = game.game_turn_stream(
                    request=object(),
                    campaign_id=campaign_id,
                    session_id=session_id,
                    player_text="我推开门",
                    tags="门厅",
                    state_block="",
                )
                body = asyncio.run(collect_body(response))

            self.assertTrue(RecordingPipeline.prepared)
            self.assertIn("event: final", body)
            self.assertIn('"recalled_world": [{"title": "门厅"}]', body)
            self.assertIn('"recalled_context": [{"kind": "world_bible"', body)
            self.assertIn('"reason": "匹配玩家填写的标签。"', body)
            self.assertIn('"action_assessment": {"action_type": "exploration"', body)
            self.assertIn('"signals": ["roll_may_be_needed"]', body)
            self.assertIn('"critic_warnings": ["choice_count_out_of_range"]', body)
            self.assertIn('"response_warnings": ["non_actionable_choice"]', body)
        finally:
            tmp.cleanup()

    def test_streaming_turn_suppresses_malformed_state_delta(self) -> None:
        tmp, paths, campaign_id, session_id = self._paths_with_session()
        malformed_protocol = "\n".join(
            [
                "===NARRATION===",
                "陷阱擦伤了你的手臂。",
                "===CHOICES===",
                "- 检查伤口",
                "- 继续前进",
                "===DM_NOTES===",
                "state delta malformed",
                "===MEMORY===",
                "玩家在门厅触发了一个小陷阱。",
                "===STATE_DELTA===",
                '{"party":[{"hp":7}',
            ]
        )

        class FakeStreamClient:
            def chat_stream_sse(self, messages):
                yield malformed_protocol

        async def collect_body(response) -> str:
            chunks: list[str] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
            return "".join(chunks)

        try:
            with (
                patch("one_person_dnd.web.routes.game.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.game.load_active_llm_config",
                    return_value=LLMConfig(base_url="http://example.test/v1", api_key="k", model="m"),
                ),
                patch("one_person_dnd.web.routes.game.create_llm_client", return_value=FakeStreamClient()),
            ):
                response = game.game_turn_stream(
                    request=object(),
                    campaign_id=campaign_id,
                    session_id=session_id,
                    player_text="我继续前进",
                    tags="",
                    state_block="",
                )
                body = asyncio.run(collect_body(response))

            self.assertIn("event: final", body)
            conn = get_connection(paths.db_path)
            try:
                pending = state_change_requests.list_pending(conn, session_id=session_id)
            finally:
                conn.close()
            self.assertEqual(pending, [])
        finally:
            tmp.cleanup()
