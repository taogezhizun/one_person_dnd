import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.adjudication import AdjudicationRecord
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import (
    adjudication_records,
    campaigns,
    character_sheets,
    plot_threads,
    session_snapshots,
    sessions,
    state_change_requests,
    story_journal,
    summaries,
    turn_logs,
)
from one_person_dnd.db.schema import init_db
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import saves


class TestSaveSnapshotRoutes(unittest.TestCase):
    def test_restore_creates_safety_snapshot_before_overwriting_current_state(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        paths = AppPaths(root, app_dir, root / "api_config.ini", app_dir / "one_person_dnd.sqlite3")
        init_db(paths.db_path)

        conn = get_connection(paths.db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "雾港")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="最新场景",
            )
            sessions.update_session_sidebar(
                conn,
                campaign_id=campaign_id,
                session_id=session_id,
                current_scene="最新场景",
                session_state="最新状态",
                pinned_world_notes="最新规则",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text=json.dumps({"party": [{"name": "现在的角色", "hp": 3}]}, ensure_ascii=False),
            )
            target_snapshot_id = session_snapshots.create_snapshot(
                conn,
                session_id=session_id,
                snapshot_name="进入遗迹前",
                turn_index=2,
                current_scene="旧场景",
                session_state="旧状态",
                pinned_world_notes="旧规则",
                character_sheet_json=json.dumps({"party": [{"name": "过去的角色", "hp": 10}]}, ensure_ascii=False),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
            ):
                response = saves.saves_session_restore(
                    session_id=session_id,
                    snapshot_id=target_snapshot_id,
                )

            self.assertEqual(response.status_code, 303)
            conn = get_connection(paths.db_path)
            try:
                snapshots = session_snapshots.list_snapshots(conn, session_id=session_id)
                self.assertEqual(len(snapshots), 2)
                safety = session_snapshots.get_snapshot(conn, snapshot_id=int(snapshots[0]["id"]))
                self.assertIsNotNone(safety)
                assert safety is not None
                self.assertEqual(safety["snapshot_name"], "恢复前自动备份 · 进入遗迹前")
                self.assertEqual(safety["current_scene"], "最新场景")
                self.assertEqual(safety["session_state"], "最新状态")
                self.assertIn("现在的角色", safety["character_sheet_json"])

                current = sessions.get_session_sidebar(conn, session_id)
                self.assertEqual(current["current_scene"], "旧场景")
                self.assertEqual(current["session_state"], "旧状态")
                self.assertEqual(current["pinned_world_notes"], "旧规则")
                self.assertIn("过去的角色", character_sheets.get_character_sheet(conn, session_id=session_id))
            finally:
                conn.close()
        finally:
            tmp.cleanup()

    def test_saves_page_lists_recent_50_snapshots_with_total_count(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        paths = AppPaths(root, app_dir, root / "api_config.ini", app_dir / "one_person_dnd.sqlite3")
        init_db(paths.db_path)

        conn = get_connection(paths.db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "雾港")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="码头",
            )
            for index in range(55):
                session_snapshots.create_snapshot(
                    conn,
                    session_id=session_id,
                    snapshot_name=f"快照 {index:02d}",
                    turn_index=index,
                    current_scene="码头",
                    session_state="",
                    pinned_world_notes="",
                    character_sheet_json="{}",
                )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
                patch("one_person_dnd.web.routes.saves.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = saves.saves(request=object())

            snapshots = context["snapshots_map"][session_id]
            self.assertEqual(len(snapshots), 50)
            self.assertEqual(snapshots[0]["snapshot_name"], "快照 54")
            self.assertEqual(snapshots[-1]["snapshot_name"], "快照 05")
            self.assertEqual(context["sessions"][0]["snapshot_count"], 55)
        finally:
            tmp.cleanup()


def _make_env() -> tuple[tempfile.TemporaryDirectory, AppPaths]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    app_dir = root / ".one_person_dnd"
    app_dir.mkdir()
    paths = AppPaths(root, app_dir, root / "api_config.ini", app_dir / "one_person_dnd.sqlite3")
    init_db(paths.db_path)
    return tmp, paths


class TestSaveSnapshotFullNarrativeRewind(unittest.TestCase):
    """
    Covers the approved full-rewind restore design: a snapshot captures the
    entire session narrative (turn_logs, story_journal_entries, plot_threads,
    session_summaries), and restore transactionally replaces the session's
    narrative with that captured set rather than only scene/character state.
    """

    def test_restore_rewinds_full_narrative_and_is_reversible(self) -> None:
        tmp, paths = _make_env()
        try:
            conn = get_connection(paths.db_path)
            try:
                campaign_id = campaigns.create_campaign(conn, "回响之城")
                session_id = sessions.create_session(
                    conn, campaign_id=campaign_id, title="第一章", current_scene="城门"
                )
                character_sheets.upsert_character_sheet(
                    conn,
                    session_id=session_id,
                    json_text=json.dumps({"party": [{"name": "艾拉", "hp": 12}]}, ensure_ascii=False),
                )

                # --- narrative as of turn 2 (the point we will snapshot) ---
                for i in range(3):
                    turn_logs.insert_turn_log(
                        conn,
                        session_id=session_id,
                        turn_index=i,
                        player_text=f"玩家行动{i}",
                        dm_text=f"DM叙事{i}",
                        dice_events_json="[]",
                    )
                for i in range(3):
                    story_journal.insert_story_journal_entry(
                        conn,
                        session_id=session_id,
                        scene_id="城门",
                        summary=f"故事记忆{i}",
                        turn_index=i,
                    )
                thread_id = plot_threads.create_thread(
                    conn,
                    session_id=session_id,
                    title="寻找钥匙",
                    priority=1,
                    summary="N状态摘要",
                    next_step="N状态下一步",
                )
                summaries.insert_summary(
                    conn,
                    session_id=session_id,
                    level="chapter",
                    start_turn=0,
                    end_turn=1,
                    summary="早期章节摘要",
                )
                conn.commit()
            finally:
                conn.close()

            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
            ):
                snap_response = saves.saves_session_snapshot(session_id=session_id, snapshot_name="回合2快照")
            self.assertEqual(snap_response.status_code, 303)

            conn = get_connection(paths.db_path)
            try:
                snaps = session_snapshots.list_snapshots(conn, session_id=session_id)
                self.assertEqual(len(snaps), 1)
                target_snapshot_id = int(snaps[0]["id"])
                target_full = session_snapshots.get_snapshot(conn, snapshot_id=target_snapshot_id)
                self.assertIsNotNone(target_full)
                assert target_full is not None
                self.assertIsNotNone(target_full["narrative_json"])
                captured = json.loads(target_full["narrative_json"])
                self.assertEqual(len(captured["turn_logs"]), 3)
                self.assertEqual(len(captured["story_journal_entries"]), 3)
                self.assertEqual(len(captured["plot_threads"]), 1)
                self.assertEqual(len(captured["session_summaries"]), 1)

                # --- the story moves on past the snapshot point ---
                for i in (3, 4):
                    turn_logs.insert_turn_log(
                        conn,
                        session_id=session_id,
                        turn_index=i,
                        player_text=f"玩家行动{i}",
                        dm_text=f"DM叙事{i}",
                        dice_events_json="[]",
                    )
                story_journal.insert_story_journal_entry(
                    conn,
                    session_id=session_id,
                    scene_id="密室",
                    summary="故事记忆3(N之后)",
                    turn_index=3,
                )
                # plot_threads has no history table: it is updated in place, so
                # this simulates the case a simple "delete forward" cannot undo.
                plot_threads.update_thread(
                    conn,
                    thread_id=thread_id,
                    session_id=session_id,
                    title="寻找钥匙",
                    priority=1,
                    summary="N之后摘要",
                    next_step="N之后下一步",
                    tags="",
                )
                plot_threads.set_status(conn, thread_id=thread_id, session_id=session_id, status="closed")
                new_thread_id = plot_threads.create_thread(
                    conn, session_id=session_id, title="N之后新线索", priority=0, summary="", next_step=""
                )
                summaries.insert_summary(
                    conn,
                    session_id=session_id,
                    level="chapter",
                    start_turn=2,
                    end_turn=3,
                    summary="N之后章节摘要",
                )
                state_change_requests.create_request(
                    conn,
                    session_id=session_id,
                    turn_index=4,
                    kind="state_delta",
                    delta_json_text=json.dumps({"hp": -1}),
                )
                conn.commit()
            finally:
                conn.close()

            # --- restore to the N snapshot: this must be a full rewind ---
            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
            ):
                restore_response = saves.saves_session_restore(session_id=session_id, snapshot_id=target_snapshot_id)
            self.assertEqual(restore_response.status_code, 303)

            conn = get_connection(paths.db_path)
            try:
                turns = turn_logs.list_all_for_session(conn, session_id=session_id)
                self.assertEqual([t["turn_index"] for t in turns], [0, 1, 2])
                self.assertEqual(turn_logs.get_next_turn_index(conn, session_id), 3)

                journal = story_journal.list_all_for_session(conn, session_id=session_id)
                self.assertEqual(len(journal), 3)
                self.assertNotIn("故事记忆3(N之后)", [j["summary"] for j in journal])

                threads = plot_threads.list_threads(conn, session_id=session_id)
                self.assertEqual(len(threads), 1)
                restored_thread = plot_threads.get_thread(conn, session_id=session_id, thread_id=thread_id)
                self.assertIsNotNone(restored_thread)
                assert restored_thread is not None
                self.assertEqual(restored_thread["status"], "open")
                self.assertEqual(restored_thread["summary"], "N状态摘要")
                self.assertEqual(restored_thread["next_step"], "N状态下一步")
                self.assertIsNone(plot_threads.get_thread(conn, session_id=session_id, thread_id=new_thread_id))

                summary_rows = summaries.list_all_for_session(conn, session_id=session_id)
                self.assertEqual(len(summary_rows), 1)
                self.assertEqual(summary_rows[0]["summary"], "早期章节摘要")

                # pending change requests referencing discarded future turns are cleared
                self.assertEqual(state_change_requests.list_pending(conn, session_id=session_id), [])

                # the pre-restore safety snapshot exists and holds the post-N narrative
                all_snaps = session_snapshots.list_snapshots(conn, session_id=session_id)
                self.assertEqual(len(all_snaps), 2)
                safety_snapshot_id = int(all_snaps[0]["id"])  # list_snapshots orders newest first
                self.assertNotEqual(safety_snapshot_id, target_snapshot_id)
            finally:
                conn.close()

            # --- reversibility: restoring the safety snapshot undoes the rewind ---
            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
            ):
                undo_response = saves.saves_session_restore(session_id=session_id, snapshot_id=safety_snapshot_id)
            self.assertEqual(undo_response.status_code, 303)

            conn = get_connection(paths.db_path)
            try:
                turns = turn_logs.list_all_for_session(conn, session_id=session_id)
                self.assertEqual([t["turn_index"] for t in turns], [0, 1, 2, 3, 4])
                self.assertEqual(turn_logs.get_next_turn_index(conn, session_id), 5)

                journal = story_journal.list_all_for_session(conn, session_id=session_id)
                self.assertEqual(len(journal), 4)

                restored_thread = plot_threads.get_thread(conn, session_id=session_id, thread_id=thread_id)
                self.assertIsNotNone(restored_thread)
                assert restored_thread is not None
                self.assertEqual(restored_thread["status"], "closed")
                self.assertEqual(restored_thread["summary"], "N之后摘要")
                self.assertIsNotNone(plot_threads.get_thread(conn, session_id=session_id, thread_id=new_thread_id))

                summary_rows = summaries.list_all_for_session(conn, session_id=session_id)
                self.assertEqual(len(summary_rows), 2)
            finally:
                conn.close()
        finally:
            tmp.cleanup()

    def test_restore_narrative_rebuilds_only_snapshot_adjudication_ledger(self) -> None:
        tmp, paths = _make_env()
        try:
            conn = get_connection(paths.db_path)
            try:
                campaign_id = campaigns.create_campaign(conn, "裁决回退")
                session_id = sessions.create_session(
                    conn, campaign_id=campaign_id, title="第一章", current_scene="机关门"
                )

                for turn_index in (0, 1):
                    attempt_id = f"snapshot-attempt-{turn_index}"
                    fingerprint = f"snapshot-fingerprint-{turn_index}"
                    record_json = json.dumps(
                        {
                            "request_fingerprint": fingerprint,
                            "degree": "success",
                            "roll": 12 + turn_index,
                        },
                        ensure_ascii=False,
                    )
                    turn_logs.insert_turn_log(
                        conn,
                        session_id=session_id,
                        turn_index=turn_index,
                        player_text=f"快照行动{turn_index}",
                        dm_text=f"快照叙事{turn_index}",
                        dice_events_json="[]",
                        attempt_id=attempt_id,
                        adjudication_json=record_json,
                    )
                    adjudication_records.create(
                        conn,
                        session_id=session_id,
                        attempt_id=attempt_id,
                        fingerprint=fingerprint,
                        record_json=record_json,
                        turn_index=turn_index,
                    )

                compatibility_json = json.dumps(
                    {
                        "attempt_id": "compatibility-fingerprint-key",
                        "policy_version": "srd_5_2_1_solo_checks_v1",
                        "fingerprint": "compatibility-fingerprint",
                        "status": "no_check",
                        "action_type": "other",
                        "check": None,
                        "manual_rolls": [],
                        "signals": [],
                        "warnings": [],
                    }
                )
                turn_logs.insert_turn_log(
                    conn,
                    session_id=session_id,
                    turn_index=2,
                    player_text="兼容格式行动",
                    dm_text="兼容格式叙事",
                    dice_events_json="[]",
                    attempt_id="compatibility-fingerprint-key",
                    adjudication_json=compatibility_json,
                )
                adjudication_records.create(
                    conn,
                    session_id=session_id,
                    attempt_id="compatibility-fingerprint-key",
                    fingerprint="compatibility-fingerprint",
                    record_json=compatibility_json,
                    turn_index=2,
                )

                # A v10 turn can still carry an older adjudication JSON shape.
                # Its ledger row exists now, but cannot be safely reconstructed
                # after restore because the captured JSON lacks a fingerprint.
                legacy_json = json.dumps({"degree": "success", "roll": 18})
                turn_logs.insert_turn_log(
                    conn,
                    session_id=session_id,
                    turn_index=3,
                    player_text="旧格式行动",
                    dm_text="旧格式叙事",
                    dice_events_json="[]",
                    attempt_id="legacy-without-fingerprint",
                    adjudication_json=legacy_json,
                )
                adjudication_records.create(
                    conn,
                    session_id=session_id,
                    attempt_id="legacy-without-fingerprint",
                    fingerprint="external-only-fingerprint",
                    record_json=legacy_json,
                    turn_index=3,
                )
                snapshot_narrative = saves._capture_narrative_json(
                    conn, session_id=session_id
                )

                future_json = json.dumps(
                    {"request_fingerprint": "future-fingerprint", "degree": "failure"}
                )
                turn_logs.insert_turn_log(
                    conn,
                    session_id=session_id,
                    turn_index=4,
                    player_text="快照后的行动",
                    dm_text="快照后的叙事",
                    dice_events_json="[]",
                    attempt_id="future-attempt",
                    adjudication_json=future_json,
                )
                adjudication_records.create(
                    conn,
                    session_id=session_id,
                    attempt_id="future-attempt",
                    fingerprint="future-fingerprint",
                    record_json=future_json,
                    turn_index=3,
                )
                adjudication_records.create(
                    conn,
                    session_id=session_id,
                    attempt_id="unfinished-attempt",
                    fingerprint="unfinished-fingerprint",
                    record_json=json.dumps(
                        {"request_fingerprint": "unfinished-fingerprint"}
                    ),
                )

                saves._restore_narrative(
                    conn,
                    session_id=session_id,
                    narrative_json=snapshot_narrative,
                )
                conn.commit()

                restored_turns = turn_logs.list_all_for_session(
                    conn, session_id=session_id
                )
                self.assertEqual(
                    [row["turn_index"] for row in restored_turns],
                    [0, 1, 2, 3],
                )
                ledger = conn.execute(
                    """
                    SELECT attempt_id, fingerprint, record_json, turn_index, completed_at
                    FROM adjudication_records
                    WHERE session_id = ?
                    ORDER BY turn_index ASC
                    """,
                    (session_id,),
                ).fetchall()
                self.assertEqual(
                    [row["attempt_id"] for row in ledger],
                    [
                        "snapshot-attempt-0",
                        "snapshot-attempt-1",
                        "compatibility-fingerprint-key",
                    ],
                )
                self.assertEqual(
                    [row["fingerprint"] for row in ledger],
                    [
                        "snapshot-fingerprint-0",
                        "snapshot-fingerprint-1",
                        "compatibility-fingerprint",
                    ],
                )
                self.assertEqual([row["turn_index"] for row in ledger], [0, 1, 2])
                self.assertTrue(all(row["completed_at"] for row in ledger))
                self.assertTrue(all(row["record_json"] for row in ledger))
                compatibility_record = AdjudicationRecord.from_json(ledger[2]["record_json"])
                self.assertEqual(
                    compatibility_record.request_fingerprint,
                    "compatibility-fingerprint",
                )
                restored_compatibility_turn = next(
                    row
                    for row in restored_turns
                    if row["attempt_id"] == "compatibility-fingerprint-key"
                )
                self.assertEqual(
                    json.loads(restored_compatibility_turn["adjudication_json"])[
                        "request_fingerprint"
                    ],
                    "compatibility-fingerprint",
                )
                for removed_attempt in (
                    "legacy-without-fingerprint",
                    "future-attempt",
                    "unfinished-attempt",
                ):
                    self.assertIsNone(
                        adjudication_records.get_by_attempt(
                            conn,
                            session_id=session_id,
                            attempt_id=removed_attempt,
                        )
                    )
            finally:
                conn.close()
        finally:
            tmp.cleanup()

    def test_restore_with_null_narrative_json_falls_back_to_state_only(self) -> None:
        """Snapshots taken before this feature have narrative_json IS NULL; restoring
        one must not delete turn_logs/story/threads/summaries, only scene/character
        state, so old snapshots stay usable after the migration."""
        tmp, paths = _make_env()
        try:
            conn = get_connection(paths.db_path)
            try:
                campaign_id = campaigns.create_campaign(conn, "旧存档")
                session_id = sessions.create_session(
                    conn, campaign_id=campaign_id, title="第一章", current_scene="现在的场景"
                )
                sessions.update_session_sidebar(
                    conn,
                    campaign_id=campaign_id,
                    session_id=session_id,
                    current_scene="现在的场景",
                    session_state="现在的状态",
                    pinned_world_notes="",
                )
                for i in range(4):
                    turn_logs.insert_turn_log(
                        conn,
                        session_id=session_id,
                        turn_index=i,
                        player_text=f"玩家行动{i}",
                        dm_text=f"DM叙事{i}",
                        dice_events_json="[]",
                    )
                # Old-style snapshot: no narrative_json captured (pre-migration row).
                target_snapshot_id = session_snapshots.create_snapshot(
                    conn,
                    session_id=session_id,
                    snapshot_name="迁移前快照",
                    turn_index=1,
                    current_scene="旧场景",
                    session_state="旧状态",
                    pinned_world_notes="旧规则",
                    character_sheet_json=json.dumps({"party": [{"name": "旧角色", "hp": 5}]}, ensure_ascii=False),
                )
                conn.commit()
            finally:
                conn.close()

            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
            ):
                response = saves.saves_session_restore(session_id=session_id, snapshot_id=target_snapshot_id)
            self.assertEqual(response.status_code, 303)

            conn = get_connection(paths.db_path)
            try:
                # State-only fields restored as before.
                current = sessions.get_session_sidebar(conn, session_id)
                self.assertEqual(current["current_scene"], "旧场景")
                self.assertEqual(current["session_state"], "旧状态")
                self.assertIn("旧角色", character_sheets.get_character_sheet(conn, session_id=session_id))

                # Narrative untouched: all 4 turns still present, nothing deleted.
                turns = turn_logs.list_all_for_session(conn, session_id=session_id)
                self.assertEqual([t["turn_index"] for t in turns], [0, 1, 2, 3])
                self.assertEqual(turn_logs.get_next_turn_index(conn, session_id), 4)
            finally:
                conn.close()
        finally:
            tmp.cleanup()
