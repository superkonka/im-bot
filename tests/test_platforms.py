#!/usr/bin/env python3
"""
测试平台适配
"""
import unittest
from src.platforms import get_platform, list_platforms
from src.platforms.whatsapp import WhatsAppPlatform
from src.platforms.telegram import TelegramPlatform


class TestPlatformFactory(unittest.TestCase):
    
    def test_list_platforms(self):
        platforms = list_platforms()
        self.assertIn('whatsapp', platforms)
        self.assertIn('telegram', platforms)
        
    def test_get_whatsapp(self):
        platform = get_platform('whatsapp')
        self.assertIsInstance(platform, WhatsAppPlatform)
        self.assertEqual(platform.config.name, 'WhatsApp Web')
        
    def test_get_telegram(self):
        platform = get_platform('telegram')
        self.assertIsInstance(platform, TelegramPlatform)
        self.assertEqual(platform.config.name, 'Telegram Web')
        
    def test_invalid_platform(self):
        with self.assertRaises(ValueError):
            get_platform('invalid')


class TestWhatsApp(unittest.TestCase):
    
    def setUp(self):
        self.platform = WhatsAppPlatform()
        
    def test_config(self):
        self.assertEqual(self.platform.config.login_method, 'qr_code')
        self.assertTrue(self.platform.config.url.startswith('https://'))
        
    def test_generate_reply(self):
        reply = self.platform.generate_reply('你好')
        self.assertIn('你好', reply)
        
        reply = self.platform.generate_reply('谢谢')
        self.assertIn('不客气', reply)


class TestTelegram(unittest.TestCase):
    
    def setUp(self):
        self.platform = TelegramPlatform()
        
    def test_config(self):
        self.assertEqual(self.platform.config.login_method, 'phone_code')
        
    def test_commands(self):
        reply = self.platform.generate_reply('/start')
        self.assertIn('欢迎', reply)
        
        reply = self.platform.generate_reply('/help')
        self.assertIn('命令', reply)


if __name__ == '__main__':
    unittest.main()
