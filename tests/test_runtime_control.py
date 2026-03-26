#!/usr/bin/env python3
"""
测试运行时控制存储
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.runtime_control import (
    OperatorControlStore,
    PendingDraft,
    RuntimeDashboard,
    RuntimeDashboardStore,
)


class TestRuntimeDashboardStore(unittest.TestCase):

    def test_runtime_dashboard_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime.json"
            store = RuntimeDashboardStore(path)
            dashboard = RuntimeDashboard(
                session_name="test_session",
                target_chat="target_user",
                status="running",
                automation_paused=False,
                manual_review_enabled=True,
                last_decision="待审核",
                pending_draft=PendingDraft(
                    draft_id="draft:1",
                    mode="reply",
                    topic="日常寒暄",
                    message="今天忙吗？",
                    reason="承接上下文",
                    created_at="2026-03-26T12:00:00",
                ),
            )
            dashboard.note_message("user", "在忙吗？", "2026-03-26 11:58")
            store.save(dashboard)
            loaded = store.load()

        self.assertEqual(loaded.session_name, "test_session")
        self.assertEqual(loaded.pending_draft.message, "今天忙吗？")
        self.assertEqual(len(loaded.recent_messages), 1)


class TestOperatorControlStore(unittest.TestCase):

    def test_append_and_pop_commands(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "control.json"
            store = OperatorControlStore(path)
            store.set_paused(True)
            store.set_proactive_paused(True)
            store.append_command("approve_draft", {"draft_id": "draft:1"})
            paused, proactive_paused, commands = store.pop_commands()

        self.assertTrue(paused)
        self.assertTrue(proactive_paused)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].action, "approve_draft")
        self.assertEqual(commands[0].payload["draft_id"], "draft:1")


if __name__ == "__main__":
    unittest.main()
