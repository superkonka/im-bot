#!/usr/bin/env python3
"""
Telegram Skill

基于 Telethon (MTProto) 的 Telegram 对话能力封装。
不依赖浏览器，直接通过 Telegram 协议收发消息。
"""

from .skill import TelegramSkill
from .types import (
    ChatInfo,
    Message,
    MessageEvent,
    UserProfile,
    ChatType,
    MediaType,
)

__all__ = [
    "TelegramSkill",
    "ChatInfo",
    "Message",
    "MessageEvent",
    "UserProfile",
    "ChatType",
    "MediaType",
]
