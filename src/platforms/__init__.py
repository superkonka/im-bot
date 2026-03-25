#!/usr/bin/env python3
"""
平台适配模块
"""
from .base import BasePlatform, PlatformConfig
from .whatsapp import WhatsAppPlatform
from .telegram import TelegramPlatform

__all__ = ['BasePlatform', 'PlatformConfig', 'WhatsAppPlatform', 'TelegramPlatform', 'get_platform']


def get_platform(name: str) -> BasePlatform:
    """获取平台实例"""
    name = name.lower()
    if name in ['whatsapp', 'wa', 'wp']:
        return WhatsAppPlatform()
    elif name in ['telegram', 'tg', 'tl']:
        return TelegramPlatform()
    else:
        raise ValueError(f"不支持的平台: {name}。支持: whatsapp, telegram")


def list_platforms() -> list[str]:
    """列出支持的平台"""
    return ['whatsapp', 'telegram']
