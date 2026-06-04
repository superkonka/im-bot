#!/usr/bin/env python3
"""
Telegram Skill 类型定义

所有数据模型均为不可变 dataclass，便于序列化和跨 Agent 传递。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class ChatType(Enum):
    """聊天类型"""
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"
    BOT = "bot"


class MediaType(Enum):
    """媒体类型"""
    NONE = auto()
    PHOTO = auto()
    VIDEO = auto()
    AUDIO = auto()
    VOICE = auto()
    DOCUMENT = auto()
    STICKER = auto()
    LOCATION = auto()
    CONTACT = auto()
    POLL = auto()


@dataclass(frozen=True)
class UserProfile:
    """用户资料"""
    user_id: int
    username: Optional[str] = None
    first_name: str = ""
    last_name: str = ""
    phone: Optional[str] = None
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    is_bot: bool = False
    is_verified: bool = False
    is_premium: bool = False
    language_code: Optional[str] = None

    @property
    def display_name(self) -> str:
        """返回最佳展示名称"""
        name = f"{self.first_name} {self.last_name}".strip()
        if name:
            return name
        if self.username:
            return f"@{self.username}"
        return f"User_{self.user_id}"


@dataclass(frozen=True)
class ChatInfo:
    """聊天会话信息"""
    chat_id: int
    type: ChatType
    title: str = ""
    username: Optional[str] = None
    unread_count: int = 0
    last_message_id: Optional[int] = None
    last_message_time: Optional[datetime] = None
    member_count: Optional[int] = None
    is_muted: bool = False
    is_pinned: bool = False
    photo_url: Optional[str] = None

    @property
    def display_name(self) -> str:
        """返回最佳展示名称"""
        if self.title:
            return self.title
        if self.username:
            return f"@{self.username}"
        return f"Chat_{self.chat_id}"


@dataclass(frozen=True)
class Message:
    """单条消息"""
    message_id: int
    chat_id: int
    sender_id: int
    text: str = ""
    timestamp: Optional[datetime] = None
    is_outgoing: bool = False
    reply_to_message_id: Optional[int] = None
    forward_from_chat_id: Optional[int] = None
    forward_from_message_id: Optional[int] = None
    media_type: MediaType = MediaType.NONE
    media_caption: Optional[str] = None
    media_file_name: Optional[str] = None
    is_edited: bool = False
    entities: List[Dict[str, Any]] = field(default_factory=list)
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def is_media(self) -> bool:
        return self.media_type != MediaType.NONE


@dataclass(frozen=True)
class MessageEvent:
    """新消息事件 —— 推送给 Agent 消费"""
    message: Message
    chat: ChatInfo
    sender: UserProfile
    is_mention: bool = False
    is_first_contact: bool = False
    # 会话级上下文（Agent 负责维护，Skill 只提供原始数据）
    session_context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    """发送消息结果"""
    success: bool
    message_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class ConversationContext:
    """
    会话上下文（可变，由 Agent 层维护）

    Skill 不直接操作此对象，但 Agent 可以将其作为 session_context
    传入 MessageEvent，实现跨轮次记忆。
    """
    chat_id: int
    user_id: int
    message_history: List[Message] = field(default_factory=list)
    user_profile: Optional[UserProfile] = None
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    custom_data: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        """添加消息到历史（保持最近 50 条）"""
        self.message_history.append(message)
        if len(self.message_history) > 50:
            self.message_history = self.message_history[-50:]
