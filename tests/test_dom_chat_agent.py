#!/usr/bin/env python3
"""
测试 DOM 聊天回复器
"""
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.dom_chat_agent import DOMChatAgent, DOMChatMemory, DOMChatMemoryStore


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


def make_config():
    return {
        "api": {
            "kimi_api_key": "test-key",
            "kimi_base_url": "https://api.moonshot.cn/v1",
            "kimi_text_model": "moonshot-v1-8k",
        },
        "telegram_user": {
            "persona": "自然聊天，不暴露 AI 身份",
            "relationship_context": "普通熟人关系",
            "response_style": "简洁自然",
            "allowed_topics": ["日常寒暄", "工作近况"],
            "blocked_topics": ["成人内容"],
            "max_message_chars": 80,
        },
    }


class TestDOMChatAgent(unittest.TestCase):

    def test_generate_reply_returns_llm_result(self):
        agent = DOMChatAgent(
            platform_name="telegram",
            client=FakeClient('{"reply":"今天忙得怎么样？","topic":"日常寒暄","reason":"承接最近聊天"}'),
            app_config=make_config(),
        )

        result = agent.generate_reply(
            latest_message="今天还在忙吗",
            history=[{"role": "user", "text": "今天还在忙吗"}],
            target_label="当前已锁定聊天",
            memory=None,
            fallback_reply=lambda: "fallback",
        )

        self.assertEqual(result.message, "今天忙得怎么样？")
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.topic, "日常寒暄")

    def test_generate_reply_prompt_includes_memory(self):
        client = FakeClient('{"reply":"那你先忙，晚点聊。","topic":"工作近况","reason":"承接摘要"}')
        agent = DOMChatAgent(
            platform_name="telegram",
            client=client,
            app_config=make_config(),
        )
        memory = DOMChatMemory(
            chat_label="小波",
            relationship_summary="最近主要在聊工作安排。",
            salient_facts=["对方最近在忙项目"],
            open_loops=["等对方确认周末安排"],
            recent_topics=["工作近况"],
        )

        agent.generate_reply(
            latest_message="今天还在开会",
            history=[{"role": "user", "text": "今天还在开会"}],
            target_label="小波",
            memory=memory,
            fallback_reply=lambda: "fallback",
        )

        prompt = client.chat.completions.last_kwargs["messages"][1]["content"]
        self.assertIn("最近主要在聊工作安排", prompt)
        self.assertIn("对方最近在忙项目", prompt)
        self.assertIn("等对方确认周末安排", prompt)

    def test_generate_reply_falls_back_when_json_invalid(self):
        agent = DOMChatAgent(
            platform_name="telegram",
            client=FakeClient("not-json"),
            app_config=make_config(),
        )

        result = agent.generate_reply(
            latest_message="你好",
            history=[],
            target_label="当前已锁定聊天",
            memory=None,
            fallback_reply=lambda: "你好呀",
        )

        self.assertEqual(result.message, "你好呀")
        self.assertEqual(result.source, "fallback")

    def test_summarize_history_returns_memory(self):
        agent = DOMChatAgent(
            platform_name="telegram",
            client=FakeClient(
                '{"relationship_summary":"最近围绕工作和日常安排在聊",'
                '"salient_facts":["对方最近开会比较多"],'
                '"open_loops":["周末安排还没定"],'
                '"recent_topics":["工作近况","生活安排"]}'
            ),
            app_config=make_config(),
        )

        memory = agent.summarize_history(
            history=[
                {"role": "user", "text": "最近一直在开会"},
                {"role": "assistant", "text": "那你先忙"},
                {"role": "user", "text": "周末再看看要不要见"},
                {"role": "assistant", "text": "好，到时再约"},
            ],
            target_label="小波",
            existing_memory=DOMChatMemory(chat_label="小波"),
            now=datetime(2026, 3, 26, 12, 0, 0),
        )

        self.assertEqual(memory.chat_label, "小波")
        self.assertIn("工作", memory.relationship_summary)
        self.assertIn("对方最近开会比较多", memory.salient_facts)
        self.assertEqual(memory.source_message_count, 4)


class TestDOMChatMemoryStore(unittest.TestCase):

    def test_memory_store_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            store = DOMChatMemoryStore(platform_name="telegram", base_dir=Path(temp_dir))
            memory = DOMChatMemory(
                chat_label="小波",
                relationship_summary="最近围绕工作和日常安排在聊",
                salient_facts=["对方最近开会比较多"],
                open_loops=["周末安排还没定"],
                recent_topics=["工作近况"],
                last_refreshed_at="2026-03-26T12:00:00",
                source_message_count=6,
            )
            store.save(memory)
            loaded = store.load("小波")

        self.assertEqual(loaded.chat_label, "小波")
        self.assertEqual(loaded.source_message_count, 6)
        self.assertIn("周末安排还没定", loaded.open_loops)

    def test_memory_store_can_clear_chat_memory(self):
        with TemporaryDirectory() as temp_dir:
            store = DOMChatMemoryStore(platform_name="telegram", base_dir=Path(temp_dir))
            memory = DOMChatMemory(chat_label="小波", relationship_summary="测试摘要")
            store.save(memory)
            path = store.path_for_chat("小波")

            cleared = store.clear("小波")
            exists_after_clear = path.exists()

        self.assertTrue(cleared)
        self.assertFalse(exists_after_clear)


if __name__ == "__main__":
    unittest.main()
