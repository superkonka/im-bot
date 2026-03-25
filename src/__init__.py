#!/usr/bin/env python3
"""
Kimi 视觉驱动 IM 机器人

支持 WhatsApp Web 和 Telegram Web 的自动化消息监控与回复
"""

__version__ = "1.1.0"
__author__ = "Kimi Code CLI"

from .im_bot import IMBot
from .browser_controller import BrowserController
from .vision_agent import KimiVisionAgent
from .use_cases import UseCaseDefinition, UseCaseValidationResult
from .platforms import get_platform

__all__ = [
    'IMBot',
    'BrowserController',
    'KimiVisionAgent',
    'UseCaseDefinition',
    'UseCaseValidationResult',
    'get_platform'
]
