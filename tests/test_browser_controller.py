#!/usr/bin/env python3
"""
测试 BrowserController 的关键调试与点击行为
"""
import unittest

from src.browser_controller import BrowserController, Element, PageState


class FakeNthLocator:

    def __init__(self):
        self.clicked = False
        self.timeout = None

    def click(self, timeout=None):
        self.clicked = True
        self.timeout = timeout


class FakeLocator:

    def __init__(self):
        self.nth_calls = []
        self.instances = {}

    def nth(self, index):
        self.nth_calls.append(index)
        locator = FakeNthLocator()
        self.instances[index] = locator
        return locator


class FakePage:

    def __init__(self):
        self.locators = {}

    def locator(self, selector):
        if selector not in self.locators:
            self.locators[selector] = FakeLocator()
        return self.locators[selector]


class TestBrowserController(unittest.TestCase):

    def test_click_uses_selector_specific_index(self):
        controller = BrowserController(headless=True)
        controller._page = FakePage()
        controller.get_state = lambda: PageState(
            url="https://example.com",
            title="Example",
            elements=[
                Element(
                    index=3,
                    tag="a",
                    text="目标聊天",
                    clickable=True,
                    selector="a",
                    selector_index=1,
                )
            ],
        )

        clicked = controller.click(1, wait=0)

        self.assertTrue(clicked)
        locator = controller._page.locators["a"]
        self.assertEqual(locator.nth_calls, [1])
        self.assertTrue(locator.instances[1].clicked)
        self.assertEqual(controller.get_last_action_debug()["element"]["selector_index"], 1)


if __name__ == "__main__":
    unittest.main()
