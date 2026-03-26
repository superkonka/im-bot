#!/usr/bin/env python3
"""
测试 Telegram 用户账号对话引擎
"""
import asyncio
import unittest
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace

from src.runtime_control import RuntimeDashboard
from src.telegram_userbot import (
    ConversationDecision,
    ConversationGuard,
    ConversationMemory,
    ConversationMemoryStore,
    ConversationState,
    ConversationTurn,
    DialogChoice,
    ProactiveSettings,
    SafetyReviewSettings,
    TelegramLLMOrchestrator,
    TelegramSafetyReviewer,
    TelegramUserBot,
    TelegramUserSettings,
)


class FakeCompletions:

    def __init__(self, content: str):
        self.content = content
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:

    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def make_settings() -> TelegramUserSettings:
    return TelegramUserSettings(
        api_id=123456,
        api_hash="hash",
        session_name="test_session",
        phone_number="",
        target_chat="target_user",
        timezone_name="Asia/Shanghai",
        history_limit=10,
        max_message_chars=60,
        persona="自然聊天，不暴露 AI 身份",
        relationship_context="普通熟人关系",
        response_style="克制自然",
        allowed_topics=["日常寒暄", "工作近况"],
        blocked_topics=["投资建议", "成人内容"],
        proactive=ProactiveSettings(
            enabled=True,
            cooldown_minutes=120,
            min_idle_since_incoming_minutes=60,
            max_daily_initiations=2,
            active_hours_start=9,
            active_hours_end=22,
            poll_interval_seconds=30,
            reply_delay_seconds=1,
        ),
        safety_review=SafetyReviewSettings(
            enabled=True,
            max_risk="medium",
            minimum_confidence=0.55,
            block_if_topic_missing=True,
        ),
        dry_run=True,
    )


class TestConversationGuard(unittest.TestCase):

    def setUp(self):
        self.settings = make_settings()
        self.guard = ConversationGuard(self.settings)

    def test_can_initiate_requires_idle_time(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        state = ConversationState(
            last_incoming_at=(now - timedelta(minutes=20)).isoformat()
        )

        allowed, reason = self.guard.can_initiate(now, state)

        self.assertFalse(allowed)
        self.assertIn("太短", reason)

    def test_can_initiate_respects_daily_limit(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        state = ConversationState(
            last_incoming_at=(now - timedelta(hours=5)).isoformat(),
            daily_initiation_counts={now.date().isoformat(): 2},
        )

        allowed, reason = self.guard.can_initiate(now, state)

        self.assertFalse(allowed)
        self.assertIn("上限", reason)

    def test_validate_decision_blocks_disallowed_topic(self):
        decision = ConversationDecision(
            action="reply",
            topic="感情试探",
            message="今天想你了吗？",
            reason="主动升温",
            confidence=0.8,
        )

        result = self.guard.validate_decision(
            decision=decision,
            mode="reply",
            history=[],
            state=ConversationState(),
        )

        self.assertEqual(result.action, "hold")
        self.assertIn("白名单", result.reason)

    def test_validate_decision_blocks_duplicate_message(self):
        decision = ConversationDecision(
            action="reply",
            topic="日常寒暄",
            message="今天工作还顺利吗？",
            reason="承接上下文",
            confidence=0.9,
        )
        state = ConversationState(last_outgoing_text="今天工作还顺利吗？")

        result = self.guard.validate_decision(
            decision=decision,
            mode="reply",
            history=[],
            state=state,
        )

        self.assertEqual(result.action, "hold")
        self.assertIn("重复", result.reason)


class TestDialogChoice(unittest.TestCase):

    def test_target_value_prefers_username(self):
        choice = DialogChoice(title="Alice", username="alice_test", dialog_id=12345)
        self.assertEqual(choice.target_value(), "alice_test")
        self.assertIn("@alice_test", choice.display_label())

    def test_target_value_falls_back_to_id(self):
        choice = DialogChoice(title="Bob", username="", dialog_id=67890)
        self.assertEqual(choice.target_value(), "67890")
        self.assertIn("id=67890", choice.display_label())


class TestTelegramLLMOrchestrator(unittest.TestCase):

    def setUp(self):
        self.settings = make_settings()

    def test_decide_reply_parses_json(self):
        fake_client = FakeClient(
            '{"action":"reply","topic":"日常寒暄","message":"今天过得怎么样？","reason":"对方刚发来消息，适合礼貌回应","confidence":0.92,"risk":"low"}'
        )
        orchestrator = TelegramLLMOrchestrator(self.settings, client=fake_client)
        history = [
            ConversationTurn(role="user", text="在忙吗？", timestamp="2026-03-26 13:50"),
        ]

        decision = orchestrator.decide_reply(
            history=history,
            latest_partner_message="在忙吗？",
            now=datetime(2026, 3, 26, 14, 0, 0),
        )

        self.assertEqual(decision.action, "reply")
        self.assertEqual(decision.topic, "日常寒暄")
        self.assertIn("今天过得怎么样", decision.message)
        prompt = fake_client.chat.completions.last_kwargs["messages"][1]["content"]
        self.assertIn("只返回 JSON", prompt)

    def test_decide_proactive_invalid_json_falls_back_to_hold(self):
        fake_client = FakeClient("not-json")
        orchestrator = TelegramLLMOrchestrator(self.settings, client=fake_client)

        decision = orchestrator.decide_proactive(
            history=[],
            now=datetime(2026, 3, 26, 16, 0, 0),
        )

        self.assertEqual(decision.action, "hold")
        self.assertIn("JSON", decision.reason)

    def test_summarize_memory_updates_structure(self):
        fake_client = FakeClient(
            '{"relationship_summary":"熟人关系，近期围绕工作和日常轻松交流",'
            '"salient_facts":["对方最近在忙项目"],'
            '"open_loops":["等对方反馈周末安排"],'
            '"recent_topics":["工作近况","日常寒暄"]}'
        )
        orchestrator = TelegramLLMOrchestrator(self.settings, client=fake_client)
        history = [
            ConversationTurn(role="user", text="这周项目有点忙", timestamp="2026-03-25 10:00"),
            ConversationTurn(role="assistant", text="那你先忙，注意休息", timestamp="2026-03-25 10:02"),
            ConversationTurn(role="user", text="周末再约吧", timestamp="2026-03-25 10:05"),
            ConversationTurn(role="assistant", text="好，到时候再看", timestamp="2026-03-25 10:06"),
            ConversationTurn(role="user", text="今天还在开会", timestamp="2026-03-26 11:00"),
            ConversationTurn(role="assistant", text="辛苦了，午饭记得吃", timestamp="2026-03-26 11:02"),
        ]

        memory = orchestrator.summarize_memory(
            history=history,
            existing_memory=ConversationMemory(),
            now=datetime(2026, 3, 26, 14, 0, 0),
        )

        self.assertIn("熟人关系", memory.relationship_summary)
        self.assertIn("对方最近在忙项目", memory.salient_facts)
        self.assertEqual(memory.source_message_count, 6)


class TestConversationMemoryStore(unittest.TestCase):

    def test_memory_store_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory.json"
            store = ConversationMemoryStore(path)
            memory = ConversationMemory(
                relationship_summary="测试关系摘要",
                salient_facts=["事实 A"],
                open_loops=["话题 A"],
                recent_topics=["日常寒暄"],
                interaction_notes=["03-26 14:00 回复: 好呀"],
                last_refreshed_at="2026-03-26T14:00:00",
                source_message_count=8,
            )
            store.save(memory)
            loaded = store.load()

        self.assertEqual(loaded.relationship_summary, "测试关系摘要")
        self.assertEqual(loaded.salient_facts, ["事实 A"])
        self.assertEqual(loaded.source_message_count, 8)


class TestTelegramSafetyReviewer(unittest.TestCase):

    def setUp(self):
        self.settings = make_settings()

    def test_review_blocks_high_risk(self):
        fake_client = FakeClient(
            '{"allow": true, "reason": "内容略显越界", "risk": "high", "confidence": 0.91, "suggested_message": ""}'
        )
        reviewer = TelegramSafetyReviewer(self.settings, client=fake_client)
        decision = ConversationDecision(
            action="reply",
            topic="日常寒暄",
            message="我一直在想你",
            reason="模型生成",
            confidence=0.8,
        )

        result = reviewer.review(
            decision=decision,
            mode="reply",
            history=[],
            memory=ConversationMemory(),
            now=datetime(2026, 3, 26, 14, 0, 0),
        )

        self.assertFalse(result.allow)
        self.assertIn("风险过高", result.reason)

    def test_review_blocks_missing_topic_when_required(self):
        reviewer = TelegramSafetyReviewer(self.settings, client=FakeClient("{}"))
        decision = ConversationDecision(
            action="reply",
            topic="",
            message="今天忙什么呢？",
            reason="模型生成",
            confidence=0.8,
        )

        result = reviewer.review(
            decision=decision,
            mode="reply",
            history=[],
            memory=ConversationMemory(),
            now=datetime(2026, 3, 26, 14, 0, 0),
        )

        self.assertFalse(result.allow)
        self.assertIn("话题标签", result.reason)


class FakeRuntimeStore:

    def __init__(self):
        self.save_calls = 0

    def save(self, dashboard):
        self.save_calls += 1


class TestTelegramUserBotOperatorCommands(unittest.TestCase):

    def test_manual_send_dispatches_message(self):
        bot = object.__new__(TelegramUserBot)
        bot.runtime = RuntimeDashboard(
            session_name="test_session",
            target_chat="target_user",
        )
        bot.runtime_store = FakeRuntimeStore()

        dispatched = []

        async def fake_dispatch_message(message, topic, proactive, source_label):
            dispatched.append((message, topic, proactive, source_label))

        bot._dispatch_message = fake_dispatch_message

        asyncio.run(bot._handle_operator_command("manual_send", {"message": "你好呀"}))

        self.assertEqual(
            dispatched,
            [("你好呀", "manual_send", False, "manual_send")],
        )
        self.assertEqual(bot.runtime.last_decision, "已执行人工发送")
        self.assertEqual(bot.runtime_store.save_calls, 1)


if __name__ == "__main__":
    unittest.main()
