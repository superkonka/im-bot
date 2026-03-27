#!/usr/bin/env python3
"""
FreeWebBot 测试
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.free_web_bot import FreeWebBot


class FakeBrowser:
    """模拟浏览器"""
    def __init__(self):
        self.opened = False
        self.closed = False
        self.clicks = []
        self.inputs = []
        self.screenshots = []
        self._page = MagicMock()
        
    def open(self, url, wait=3):
        self.opened = True
        self.current_url = url
        return True
        
    def close(self):
        self.closed = True
        return True
        
    def screenshot(self, filepath=None):
        self.screenshots.append(filepath)
        return filepath or "screenshot.png"
        
    def click(self, index, wait=2):
        self.clicks.append(index)
        return True
        
    def click_by_text(self, text, wait=2, timeout_ms=3000):
        self.clicks.append(f"text:{text}")
        return True
        
    def type_text(self, text, wait=1):
        self.inputs.append(text)
        return True
        
    def input_to_element(self, index, text, wait=1):
        self.inputs.append((index, text))
        return True
        
    def get_state(self):
        from src.browser_controller import PageState, Element
        return PageState(
            url="https://example.com",
            title="Test Page",
            elements=[
                Element(index=1, tag="button", text="Submit", clickable=True),
                Element(index=2, tag="input", text="", input_field=True),
            ]
        )
        
    def get_page(self):
        return self._page
        
    def press_key(self, key, wait=1):
        return True
        
    def get_last_action_debug(self):
        return {"action": "fake", "success": True}
        
    def find_text_candidates(self, text, selector="", limit=8, left_panel_only=False):
        return [{"text": text, "selector": selector}]


class FakeVisionAgent:
    """模拟视觉代理"""
    def __init__(self):
        self.decisions = []
        self.current_step = 0
        self.system_prompt = ""
        
    def set_system_prompt(self, prompt):
        self.system_prompt = prompt
        
    def analyze_screenshot(self, screenshot_path, context=""):
        from src.vision_agent import ActionDecision
        self.current_step += 1
        # 模拟几步后完成
        if self.current_step >= 3:
            decision = ActionDecision(
                action="done",
                params={},
                reason="Task completed",
                confidence=0.95
            )
        else:
            decision = ActionDecision(
                action="click",
                params={"index": 1},
                reason="Click submit button",
                confidence=0.9
            )
        self.decisions.append(decision)
        return decision
        
    def get_last_analysis_debug(self):
        return {"model": "fake"}


class TestFreeWebBot(unittest.TestCase):
    """FreeWebBot 测试用例"""

    def test_initialization(self):
        """测试初始化"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标",
            max_steps=10,
            step_delay=2,
            headless=True
        )
        
        self.assertEqual(bot.url, "https://example.com")
        self.assertEqual(bot.goal, "测试目标")
        self.assertEqual(bot.max_steps, 10)
        self.assertEqual(bot.step_delay, 2)
        self.assertEqual(bot.headless, True)
        
    def test_system_prompt_contains_goal(self):
        """测试系统提示词包含目标"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="搜索今天的新闻"
        )
        
        prompt = bot._build_system_prompt()
        self.assertIn("搜索今天的新闻", prompt)
        self.assertIn("用户目标", prompt)
        self.assertIn("可用操作", prompt)
        
    def test_build_visual_context(self):
        """测试构建视觉上下文"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标"
        )
        bot.browser = FakeBrowser()
        
        context, payload = bot._build_visual_context()
        
        self.assertIn("页面 URL:", context)
        self.assertIn("测试目标", context)
        self.assertEqual(payload["url"], "https://example.com")
        self.assertIn("elements", payload)
        
    @patch('src.free_web_bot.BrowserController')
    @patch('src.free_web_bot.KimiVisionAgent')
    def test_start_and_stop(self, MockVision, MockBrowser):
        """测试启动和停止"""
        fake_browser = FakeBrowser()
        fake_vision = FakeVisionAgent()
        MockBrowser.return_value = fake_browser
        MockVision.return_value = fake_vision
        
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标",
            max_steps=5
        )
        
        # 运行应该正常完成
        bot.start()
        
        # 验证浏览器已打开和关闭
        self.assertTrue(fake_browser.opened)
        self.assertTrue(fake_browser.closed)
        
    def test_execute_decision_click(self):
        """测试执行点击决策"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标"
        )
        bot.browser = FakeBrowser()
        
        from src.vision_agent import ActionDecision
        decision = ActionDecision(
            action="click",
            params={"index": 1},
            reason="Test click",
            confidence=0.9
        )
        
        result = bot._execute_decision(decision)
        self.assertEqual(bot.browser.clicks, [1])
        
    def test_execute_decision_type(self):
        """测试执行输入决策"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标"
        )
        bot.browser = FakeBrowser()
        
        from src.vision_agent import ActionDecision
        decision = ActionDecision(
            action="type",
            params={"text": "Hello World"},
            reason="Test type",
            confidence=0.9
        )
        
        result = bot._execute_decision(decision)
        self.assertEqual(bot.browser.inputs, ["Hello World"])
        
    def test_handle_scroll(self):
        """测试滚动处理"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标"
        )
        bot.browser = FakeBrowser()
        
        result = bot._handle_scroll({"direction": "down", "amount": 300})
        self.assertIn("down", result)
        
    def test_handle_wait(self):
        """测试等待处理"""
        bot = FreeWebBot(
            url="https://example.com",
            goal="测试目标"
        )
        
        import time
        start = time.time()
        result = bot._handle_wait({"seconds": 1})
        elapsed = time.time() - start
        
        self.assertIn("等待", result)
        self.assertGreaterEqual(elapsed, 0.5)  # 至少等待了 0.5 秒


if __name__ == "__main__":
    unittest.main()
