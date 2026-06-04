#!/usr/bin/env python3
"""
Telegram Skill 核心实现

基于 Telethon 封装所有 Telegram 对话操作，提供 Agent 友好的异步接口。
所有 Telethon 原生对象在此层转换为强类型的 dataclass，避免 Agent 层依赖 Telethon。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from telethon import TelegramClient, events
from telethon.tl import types as tl_types

from .session_manager import SessionManager
from .types import (
    ChatInfo,
    ChatType,
    MediaType,
    Message,
    MessageEvent,
    SendResult,
    UserProfile,
)


class TelegramSkill:
    """
    Telegram 对话能力封装（Skill 层）。

    用法示例:
        skill = TelegramSkill("my_account")
        await skill.start(api_id=12345, api_hash="xxx", phone="+86...")

        # 监听新消息
        def on_message(event: MessageEvent):
            print(f"[{event.chat.display_name}] {event.sender.display_name}: {event.message.text}")
        skill.on_new_message(on_message)

        # 发送消息
        await skill.send_message(chat_id=123456789, text="你好！")

        await skill.stop()
    """

    def __init__(self, session_name: str = "default"):
        self.session_name = session_name
        self._session = SessionManager(session_name)
        self._client: Optional[TelegramClient] = None
        self._handlers: List[Callable[[MessageEvent], Awaitable[None] | None]] = []
        self._event_handler_registered = False
        self._me_id: Optional[int] = None
        # 缓存：避免反复查询同一用户/聊天
        self._user_cache: Dict[int, UserProfile] = {}
        self._chat_cache: Dict[int, ChatInfo] = {}

    # ────────────────────────────── 生命周期 ──────────────────────────────

    async def start(
        self,
        api_id: int,
        api_hash: str,
        phone: Optional[str] = None,
        code_callback: Optional[Callable[[], str]] = None,
        password_callback: Optional[Callable[[], str]] = None,
        proxy: Optional[tuple] = None,
    ) -> None:
        """启动 Skill，建立 Telegram 连接"""
        self._client = await self._session.connect(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            code_callback=code_callback,
            password_callback=password_callback,
            proxy=proxy,
        )
        me = await self._client.get_me()
        self._me_id = me.id
        self._register_event_handler()
        print(f"[TelegramSkill] 已启动，当前账号 ID: {self._me_id}")

    async def stop(self) -> None:
        """停止 Skill，断开连接"""
        if self._client:
            # 移除事件处理器
            self._client.remove_event_handler(self._on_raw_message)
        await self._session.disconnect()
        self._client = None
        self._event_handler_registered = False
        print("[TelegramSkill] 已停止")

    @property
    def is_running(self) -> bool:
        return self._session.is_connected()

    # ────────────────────────────── 消息发送 ──────────────────────────────

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: Optional[int] = None,
        parse_mode: Optional[str] = "md",
    ) -> SendResult:
        """
        发送文本消息。

        参数:
            chat_id: 目标聊天 ID
            text: 消息内容（支持 Markdown）
            reply_to: 回复某条消息的 ID
            parse_mode: "md" | "html" | None
        """
        if not self._client:
            return SendResult(success=False, error="Skill 未启动")

        try:
            entity = await self._client.get_entity(chat_id)
            result = await self._client.send_message(
                entity=entity,
                message=text,
                reply_to=reply_to,
                parse_mode=parse_mode,
            )
            return SendResult(
                success=True,
                message_id=result.id,
                timestamp=result.date.replace(tzinfo=timezone.utc) if result.date else None,
            )
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    async def send_typing(self, chat_id: int, duration: float = 5.0) -> None:
        """模拟正在输入状态（人性化延迟）"""
        if not self._client:
            return
        entity = await self._client.get_entity(chat_id)
        async with self._client.action(entity, "typing"):
            await asyncio.sleep(duration)

    async def mark_read(self, chat_id: int, max_id: Optional[int] = None) -> None:
        """标记聊天为已读"""
        if not self._client:
            return
        entity = await self._client.get_entity(chat_id)
        messages = await self._client.get_messages(entity, limit=1)
        if messages:
            await self._client.send_read_acknowledge(
                entity, messages=[messages[0]] if max_id is None else None, max_id=max_id
            )

    # ────────────────────────────── 消息获取 ──────────────────────────────

    async def get_messages(
        self,
        chat_id: int,
        limit: int = 20,
        offset_id: int = 0,
    ) -> List[Message]:
        """获取某聊天的历史消息"""
        if not self._client:
            return []

        entity = await self._client.get_entity(chat_id)
        raw_messages = await self._client.get_messages(
            entity, limit=limit, offset_id=offset_id
        )
        return [self._convert_message(m) for m in raw_messages if m]

    async def get_message_by_id(self, chat_id: int, message_id: int) -> Optional[Message]:
        """获取单条消息"""
        messages = await self.get_messages(chat_id, limit=1, offset_id=message_id - 1)
        for m in messages:
            if m.message_id == message_id:
                return m
        return None

    # ────────────────────────────── 聊天列表 ──────────────────────────────

    async def list_chats(
        self,
        limit: int = 50,
        unread_only: bool = False,
    ) -> List[ChatInfo]:
        """
        获取聊天列表。

        参数:
            limit: 最多返回多少个
            unread_only: 是否只返回有未读消息的
        """
        if not self._client:
            return []

        result: List[ChatInfo] = []
        async for dialog in self._client.iter_dialogs(limit=limit):
            unread = dialog.unread_count or 0
            if unread_only and unread == 0:
                continue

            chat_info = self._convert_dialog(dialog)
            self._chat_cache[chat_info.chat_id] = chat_info
            result.append(chat_info)

        return result

    async def get_chat_info(self, chat_id: int) -> Optional[ChatInfo]:
        """获取聊天详细信息"""
        if chat_id in self._chat_cache:
            return self._chat_cache[chat_id]

        if not self._client:
            return None

        try:
            entity = await self._client.get_entity(chat_id)
            chat_info = self._convert_entity_to_chat(entity)
            self._chat_cache[chat_id] = chat_info
            return chat_info
        except Exception:
            return None

    # ────────────────────────────── 用户信息 ──────────────────────────────

    async def get_user_profile(self, user_id: int) -> Optional[UserProfile]:
        """获取用户资料"""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        if not self._client:
            return None

        try:
            entity = await self._client.get_entity(user_id)
            profile = self._convert_user(entity)
            self._user_cache[user_id] = profile
            return profile
        except Exception:
            return None

    async def get_me(self) -> Optional[UserProfile]:
        """获取当前登录账号的资料"""
        if not self._client:
            return None
        me = await self._client.get_me()
        return self._convert_user(me) if me else None

    # ────────────────────────────── 事件监听 ──────────────────────────────

    def on_new_message(
        self,
        callback: Callable[[MessageEvent], Awaitable[None] | None],
    ) -> None:
        """
        注册新消息回调。

        回调函数签名:
            async def handler(event: MessageEvent) -> None: ...
            # 或同步函数
            def handler(event: MessageEvent) -> None: ...
        """
        self._handlers.append(callback)

    def remove_handler(
        self,
        callback: Callable[[MessageEvent], Awaitable[None] | None],
    ) -> None:
        """移除回调"""
        if callback in self._handlers:
            self._handlers.remove(callback)

    # ────────────────────────────── 内部：事件处理 ──────────────────────────────

    def _register_event_handler(self) -> None:
        """注册 Telethon 事件处理器"""
        if self._event_handler_registered or not self._client:
            return
        self._client.add_event_handler(
            self._on_raw_message,
            events.NewMessage,
        )
        self._event_handler_registered = True

    async def _on_raw_message(self, event: events.NewMessage.Event) -> None:
        """Telethon 原始事件 -> 转换为 MessageEvent -> 分发给 handlers"""
        try:
            raw_msg = event.message
            if not raw_msg:
                return

            # 忽略自己发出的消息（避免回声）
            sender_id = raw_msg.sender_id
            if sender_id == self._me_id:
                return

            message = self._convert_message(raw_msg)
            chat = await self.get_chat_info(message.chat_id)
            sender = await self.get_user_profile(sender_id) if sender_id else None

            if not chat or not sender:
                return

            # 判断是否是 @提及（群聊中）
            is_mention = False
            if chat.type in (ChatType.GROUP, ChatType.CHANNEL) and raw_msg.mentioned:
                is_mention = True

            # 判断是否是首次联系（通过历史消息数推断）
            is_first = False
            try:
                async for _ in self._client.iter_messages(chat.chat_id, limit=2, from_user=sender_id):
                    pass
                else:
                    is_first = True
            except Exception:
                pass

            msg_event = MessageEvent(
                message=message,
                chat=chat,
                sender=sender,
                is_mention=is_mention,
                is_first_contact=is_first,
            )

            # 并发调用所有 handler（不阻塞 Telethon 事件循环）
            for handler in self._handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        asyncio.create_task(handler(msg_event))
                    else:
                        handler(msg_event)
                except Exception as exc:
                    print(f"[TelegramSkill] Handler 异常: {exc}")

        except Exception as exc:
            print(f"[TelegramSkill] 事件处理异常: {exc}")

    # ────────────────────────────── 内部：类型转换 ──────────────────────────────

    @staticmethod
    def _convert_message(raw) -> Message:
        """Telethon Message -> 我们的 Message"""
        media_type = MediaType.NONE
        media_caption = None
        media_file_name = None

        if raw.media:
            if isinstance(raw.media, tl_types.MessageMediaPhoto):
                media_type = MediaType.PHOTO
            elif isinstance(raw.media, tl_types.MessageMediaDocument):
                doc = raw.media.document
                mime = getattr(doc, "mime_type", "")
                if mime.startswith("video"):
                    media_type = MediaType.VIDEO
                elif mime.startswith("audio"):
                    media_type = MediaType.AUDIO
                elif "voice" in mime or "ogg" in mime:
                    media_type = MediaType.VOICE
                else:
                    media_type = MediaType.DOCUMENT
                # 尝试获取文件名
                for attr in getattr(doc, "attributes", []):
                    if isinstance(attr, tl_types.DocumentAttributeFilename):
                        media_file_name = attr.file_name
                        break
            elif isinstance(raw.media, tl_types.MessageMediaGeo):
                media_type = MediaType.LOCATION
            elif isinstance(raw.media, tl_types.MessageMediaContact):
                media_type = MediaType.CONTACT
            elif isinstance(raw.media, tl_types.MessageMediaPoll):
                media_type = MediaType.POLL

        return Message(
            message_id=raw.id,
            chat_id=raw.chat_id if hasattr(raw, "chat_id") else 0,
            sender_id=raw.sender_id or 0,
            text=raw.text or "",
            timestamp=raw.date.replace(tzinfo=timezone.utc) if raw.date else None,
            is_outgoing=raw.out if hasattr(raw, "out") else False,
            reply_to_message_id=raw.reply_to.reply_to_msg_id if raw.reply_to else None,
            forward_from_chat_id=getattr(raw.fwd_from, "from_id", None),
            forward_from_message_id=getattr(raw.fwd_from, "channel_post", None),
            media_type=media_type,
            media_caption=media_caption,
            media_file_name=media_file_name,
            is_edited=raw.edit_date is not None if hasattr(raw, "edit_date") else False,
            raw_data=None,  # 需要时可序列化原始数据
        )

    @staticmethod
    def _convert_dialog(dialog) -> ChatInfo:
        """Telethon Dialog -> ChatInfo"""
        entity = dialog.entity
        return TelegramSkill._convert_entity_to_chat(entity, dialog)

    @staticmethod
    def _convert_entity_to_chat(entity, dialog=None) -> ChatInfo:
        """Telethon Entity -> ChatInfo"""
        chat_type = ChatType.PRIVATE
        title = ""
        username = None
        member_count = None
        unread = getattr(dialog, "unread_count", 0) if dialog else 0
        last_msg_id = getattr(dialog, "top_message", None) if dialog else None
        last_msg_time = None

        if isinstance(entity, tl_types.User):
            chat_type = ChatType.BOT if entity.bot else ChatType.PRIVATE
            title = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
            username = entity.username
        elif isinstance(entity, tl_types.Chat):
            chat_type = ChatType.GROUP
            title = entity.title or ""
            member_count = getattr(entity, "participants_count", None)
        elif isinstance(entity, tl_types.Channel):
            chat_type = ChatType.CHANNEL if entity.broadcast else ChatType.GROUP
            title = entity.title or ""
            username = entity.username
            member_count = getattr(entity, "participants_count", None)

        return ChatInfo(
            chat_id=entity.id,
            type=chat_type,
            title=title,
            username=username,
            unread_count=unread,
            last_message_id=last_msg_id,
            last_message_time=last_msg_time,
            member_count=member_count,
            is_muted=getattr(dialog, "is_user", False) and getattr(dialog, "dialog", {}).get("notify_settings", {}).get("silent", False) if dialog else False,
            is_pinned=getattr(dialog, "pinned", False) if dialog else False,
        )

    @staticmethod
    def _convert_user(entity) -> UserProfile:
        """Telethon User -> UserProfile"""
        if isinstance(entity, tl_types.User):
            return UserProfile(
                user_id=entity.id,
                username=entity.username,
                first_name=entity.first_name or "",
                last_name=entity.last_name or "",
                phone=entity.phone,
                bio=getattr(entity, "about", None),
                photo_url=None,  # Telethon 需要额外下载
                is_bot=entity.bot,
                is_verified=entity.verified,
                is_premium=getattr(entity, "premium", False),
                language_code=getattr(entity, "lang_code", None),
            )
        return UserProfile(user_id=entity.id, first_name=str(entity.id))
