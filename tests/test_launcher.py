#!/usr/bin/env python3
"""
测试统一启动器
"""
import unittest
from unittest.mock import Mock, patch

from src.launcher import launch_platform, resolve_telegram_transport


class TestLauncher(unittest.TestCase):

    def test_resolve_telegram_transport_prefers_explicit_choice(self):
        config = {"telegram_user": {"transport": "user"}}
        self.assertEqual(resolve_telegram_transport("web", config), "web")

    def test_resolve_telegram_transport_uses_config_default(self):
        config = {"telegram_user": {"transport": "user"}}
        self.assertEqual(resolve_telegram_transport("auto", config), "user")

    @patch("src.launcher.TelegramUserBot")
    @patch("src.launcher.validate_telegram_user_settings")
    @patch("src.launcher.validate_telegram_user_config")
    @patch("src.launcher.validate_config")
    @patch("src.launcher.get_app_config")
    def test_launch_platform_routes_telegram_to_userbot(
        self,
        mock_get_app_config,
        mock_validate_config,
        mock_validate_telegram_user_config,
        mock_validate_telegram_user_settings,
        mock_userbot_cls,
    ):
        mock_get_app_config.return_value = {
            "runtime": {"max_steps": 500, "step_delay": 3},
            "telegram_user": {"transport": "user"},
        }
        bot_instance = Mock()
        mock_userbot_cls.return_value = bot_instance

        result = launch_platform("telegram", transport="auto")

        self.assertEqual(result, "telegram_user")
        mock_validate_config.assert_called_once()
        mock_validate_telegram_user_config.assert_called_once()
        mock_validate_telegram_user_settings.assert_called_once()
        bot_instance.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
