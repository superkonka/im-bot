#!/usr/bin/env python3
"""
测试 Web 模式下的 IMBot 辅助目标聊天流程
"""
import unittest
from types import SimpleNamespace

from src.im_bot import IMBot
from src.runtime_control import RuntimeDashboard


class FakeBrowser:

    def __init__(self):
        self.enter_pressed = False
        self.arrow_down_pressed = False
        self.js_click_attempted = False
        self.chat_title = "小波"

    def click_selector_by_text(self, selector, text, wait=1, timeout_ms=2500):
        return False

    def click_by_text(self, text, wait=1, timeout_ms=2500):
        return False

    def click_visible_text_via_js(self, text, wait=1, left_panel_only=False):
        self.js_click_attempted = True
        return False

    def input_by_selector(self, selector, text, wait=1, timeout_ms=2500):
        return True

    def press_key(self, key, wait=1):
        if key == "ArrowDown":
            self.arrow_down_pressed = True
        if key == "Enter":
            self.enter_pressed = True
        return True

    def has_visible_selector(self, selector, timeout_ms=1000):
        return selector in {".composer-input", ".message"}

    def get_texts_by_selector(self, selector):
        return ["你好", "最近怎么样"]

    def get_first_text_by_selector(self, selector):
        return self.chat_title

    def get_message_items(self, selector, limit=12):
        return [
            {"role": "user", "text": "你好"},
            {"role": "user", "text": "最近怎么样"},
        ]

    def is_page_alive(self):
        return True


class FakeMemoryStore:

    def __init__(self):
        self.last_loaded = ""
        self.last_cleared = ""

    def load(self, chat_label):
        self.last_loaded = chat_label
        return SimpleNamespace(
            chat_label=chat_label,
            relationship_summary="",
            salient_facts=[],
            open_loops=[],
            recent_topics=[],
            last_refreshed_at="",
            source_message_count=0,
        )

    def save(self, memory):
        return None

    def clear(self, chat_label):
        self.last_cleared = chat_label
        return True

    def path_for_chat(self, chat_label):
        return f"/tmp/{chat_label}.json"


class FakeRuntimeStore:

    def __init__(self):
        self.save_calls = 0

    def save(self, runtime):
        self.save_calls += 1


class FakeControlStore:

    def __init__(self, paused=False, proactive_paused=False, commands=None):
        self.paused = paused
        self.proactive_paused = proactive_paused
        self.commands = list(commands or [])

    def pop_commands(self):
        commands = list(self.commands)
        self.commands = []
        return self.paused, self.proactive_paused, commands


def make_bot(browser=None):
    bot = object.__new__(IMBot)
    bot.target_chat_name = "小波"
    bot.target_chat_prepare_timeout = 9
    bot.target_chat_mode = "search_then_lock"
    bot.target_chat_dom_history_limit = 10
    bot.target_chat_use_llm = True
    bot.last_seen_incoming_text = ""
    bot.last_sent_reply = ""
    bot.target_chat_open_failures = 2
    bot.max_target_chat_open_failures = 3
    bot.manual_target_chat_mode = False
    bot.manual_target_chat_prompted = False
    bot.locked_chat_title = ""
    bot.last_locked_at = ""
    bot.dom_chat_agent = None
    bot.chat_memory = SimpleNamespace(
        chat_label="",
        relationship_summary="",
        salient_facts=[],
        open_loops=[],
        recent_topics=[],
        last_refreshed_at="",
        source_message_count=0,
    )
    bot.dom_chat_memory_store = FakeMemoryStore()
    bot.runtime = RuntimeDashboard(session_name="telegram_web", target_chat="小波", transport="web")
    bot.runtime_store = FakeRuntimeStore()
    bot.control_store = FakeControlStore()
    bot.browser = browser or FakeBrowser()
    bot.platform = SimpleNamespace(
        config=SimpleNamespace(
            selectors={
                "chat_item": ".chat",
                "search_input": "input[type='text']",
                "chat_header_title": "header h3",
                "message_input": ".composer-input",
                "message_bubble": ".message",
            }
        )
    )
    return bot


class TestIMBotTargetChatFlow(unittest.TestCase):

    def test_open_target_chat_uses_search_enter_fallback(self):
        bot = make_bot()

        opened = bot._open_target_chat()

        self.assertTrue(opened)
        self.assertTrue(bot.browser.js_click_attempted)
        self.assertTrue(bot.browser.arrow_down_pressed)
        self.assertTrue(bot.browser.enter_pressed)

    def test_wait_for_manual_target_chat_selection_locks_current_chat(self):
        bot = make_bot()

        locked = bot._wait_for_manual_target_chat_selection()

        self.assertTrue(locked)
        self.assertTrue(bot.manual_target_chat_mode)
        self.assertTrue(bot.manual_target_chat_prompted)
        self.assertEqual(bot.target_chat_open_failures, 0)
        self.assertEqual(bot.last_seen_incoming_text, "最近怎么样")

    def test_should_use_target_chat_flow_for_manual_lock_without_name(self):
        bot = make_bot()
        bot.target_chat_name = ""
        bot.target_chat_mode = "manual_lock"

        self.assertTrue(bot._should_use_target_chat_flow())

    def test_manual_lock_uses_detected_chat_title_for_memory(self):
        browser = FakeBrowser()
        browser.chat_title = "阿明"
        bot = make_bot(browser=browser)
        bot.target_chat_name = ""
        bot.target_chat_mode = "manual_lock"

        locked = bot._wait_for_manual_target_chat_selection()

        self.assertTrue(locked)
        self.assertEqual(bot.locked_chat_title, "阿明")
        self.assertEqual(bot.dom_chat_memory_store.last_loaded, "阿明")

    def test_apply_runtime_controls_can_clear_current_chat_memory(self):
        bot = make_bot()
        bot.manual_target_chat_mode = True
        bot.locked_chat_title = "小波"
        bot.last_locked_at = "2026-03-26T12:00:00"
        bot.chat_memory.relationship_summary = "已有摘要"
        bot.control_store = FakeControlStore(
            commands=[SimpleNamespace(action="clear_memory", payload={})]
        )

        should_continue = bot._apply_runtime_controls()

        self.assertTrue(should_continue)
        self.assertEqual(bot.dom_chat_memory_store.last_cleared, "小波")
        self.assertEqual(bot.chat_memory.chat_label, "小波")
        self.assertEqual(bot.chat_memory.relationship_summary, "")
        self.assertTrue(bot.runtime.locked)

    def test_apply_runtime_controls_respects_automation_pause(self):
        bot = make_bot()
        bot.control_store = FakeControlStore(paused=True)

        should_continue = bot._apply_runtime_controls()

        self.assertFalse(should_continue)
        self.assertTrue(bot.runtime.automation_paused)


if __name__ == "__main__":
    unittest.main()
