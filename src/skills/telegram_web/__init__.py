#!/usr/bin/env python3
"""
Telegram Web Skill

基于 Playwright 的 Telegram Web 自动化方案。
通过浏览器登录并保存状态，直接操作 DOM 收发消息。
无需 api_id/api_hash，适合无法接收短信验证码的场景。
"""

from .skill import TelegramWebSkill

__all__ = ["TelegramWebSkill"]
