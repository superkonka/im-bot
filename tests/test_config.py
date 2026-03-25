#!/usr/bin/env python3
"""
测试配置中心
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config import ConfigManager, DEFAULT_APP_CONFIG, CONFIG_SCHEMA, _deep_merge


class TestConfigHelpers(unittest.TestCase):

    def test_deep_merge_keeps_defaults(self):
        merged = _deep_merge(
            {"runtime": {"max_steps": 500, "step_delay": 3}},
            {"runtime": {"step_delay": 5}}
        )
        self.assertEqual(merged["runtime"]["max_steps"], 500)
        self.assertEqual(merged["runtime"]["step_delay"], 5)


class TestConfigManager(unittest.TestCase):

    def test_load_creates_default_config(self):
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "app_config.json"
            manager = ConfigManager(config_path, DEFAULT_APP_CONFIG, CONFIG_SCHEMA)

            config = manager.load()

            self.assertTrue(config_path.exists())
            self.assertEqual(config["runtime"]["max_steps"], 500)

    def test_save_and_reload_config(self):
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "app_config.json"
            manager = ConfigManager(config_path, DEFAULT_APP_CONFIG, CONFIG_SCHEMA)

            config = manager.load()
            config["runtime"]["max_steps"] = 321
            config["browser"]["headless"] = True
            manager.save(config)

            reloaded = manager.load()
            self.assertEqual(reloaded["runtime"]["max_steps"], 321)
            self.assertTrue(reloaded["browser"]["headless"])

    def test_reset_restores_defaults(self):
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "app_config.json"
            manager = ConfigManager(config_path, DEFAULT_APP_CONFIG, CONFIG_SCHEMA)

            config = manager.load()
            config["runtime"]["step_delay"] = 9
            manager.save(config)
            reset_config = manager.reset()

            self.assertEqual(reset_config["runtime"]["step_delay"], 3)


if __name__ == "__main__":
    unittest.main()
