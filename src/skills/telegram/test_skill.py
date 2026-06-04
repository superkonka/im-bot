#!/usr/bin/env python3
"""
Telegram Skill 单元测试（无需真实 API 连接）

验证:
1. 类型转换函数正确性
2. 未连接时方法返回预期错误
3. 事件 handler 注册/移除
4. 数据模型序列化

用法:
    .venv/bin/python src/skills/telegram/test_skill.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# 兼容独立运行
_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

from telethon.tl import types as tl_types

from skills.telegram.skill import TelegramSkill
from skills.telegram.types import (
    ChatInfo,
    ChatType,
    MediaType,
    Message,
    MessageEvent,
    UserProfile,
)


# ────────────────────────────── 测试工具 ──────────────────────────────

_tests_passed = 0
_tests_failed = 0


def assert_eq(actual, expected, msg=""):
    global _tests_passed, _tests_failed
    if actual == expected:
        _tests_passed += 1
        print(f"  ✅ {msg or 'assert_eq'}")
    else:
        _tests_failed += 1
        print(f"  ❌ {msg or 'assert_eq'}: expected={expected}, got={actual}")


def assert_true(condition, msg=""):
    assert_eq(bool(condition), True, msg)


def assert_false(condition, msg=""):
    assert_eq(bool(condition), False, msg)


# ────────────────────────────── 测试用例 ──────────────────────────────

def test_user_profile():
    print("\n📋 test_user_profile")
    u = UserProfile(user_id=123, first_name="张", last_name="三", username="zhangsan")
    assert_eq(u.display_name, "张 三", "display_name 应组合 first + last name")

    u2 = UserProfile(user_id=456, username="anonymous")
    assert_eq(u2.display_name, "@anonymous", "无名字时应显示 username")

    u3 = UserProfile(user_id=789)
    assert_eq(u3.display_name, "User_789", "无名字无 username 时应 fallback")


def test_chat_info():
    print("\n📋 test_chat_info")
    c = ChatInfo(chat_id=100, type=ChatType.GROUP, title="测试群", unread_count=5)
    assert_eq(c.display_name, "测试群", "有 title 时应显示 title")
    assert_eq(c.unread_count, 5, "未读数应正确")

    c2 = ChatInfo(chat_id=200, type=ChatType.PRIVATE, username="testuser")
    assert_eq(c2.display_name, "@testuser", "无 title 时应显示 username")


def test_message_media_types():
    print("\n📋 test_message_media_types")
    # 无媒体
    m1 = Message(message_id=1, chat_id=1, sender_id=1, text="hello")
    assert_false(m1.is_media, "纯文本消息 is_media 应为 False")

    # 照片
    m2 = Message(message_id=2, chat_id=1, sender_id=1, media_type=MediaType.PHOTO)
    assert_true(m2.is_media, "照片消息 is_media 应为 True")


def test_convert_message_text_only():
    print("\n📋 test_convert_message_text_only")
    raw = MagicMock()
    raw.id = 42
    raw.chat_id = 100
    raw.sender_id = 200
    raw.text = "Hello World"
    raw.date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    raw.out = False
    raw.reply_to = None
    raw.fwd_from = None
    raw.media = None
    raw.edit_date = None

    msg = TelegramSkill._convert_message(raw)
    assert_eq(msg.message_id, 42, "message_id")
    assert_eq(msg.chat_id, 100, "chat_id")
    assert_eq(msg.sender_id, 200, "sender_id")
    assert_eq(msg.text, "Hello World", "text")
    assert_eq(msg.media_type, MediaType.NONE, "无媒体")
    assert_false(msg.is_outgoing, "不是自己发出的")


def test_convert_message_with_photo():
    print("\n📋 test_convert_message_with_photo")
    raw = MagicMock()
    raw.id = 43
    raw.chat_id = 100
    raw.sender_id = 200
    raw.text = "看这张图"
    raw.date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    raw.out = True
    raw.reply_to = None
    raw.fwd_from = None
    raw.media = tl_types.MessageMediaPhoto(photo=tl_types.PhotoEmpty(id=0))
    raw.edit_date = None

    msg = TelegramSkill._convert_message(raw)
    assert_eq(msg.media_type, MediaType.PHOTO, "应识别为照片")
    assert_true(msg.is_outgoing, "是自己发出的")


def test_convert_user():
    print("\n📋 test_convert_user")
    user = tl_types.User(
        id=12345,
        first_name="李",
        last_name="四",
        username="lisi",
        bot=False,
        verified=True,
    )
    profile = TelegramSkill._convert_user(user)
    assert_eq(profile.user_id, 12345, "user_id")
    assert_eq(profile.first_name, "李", "first_name")
    assert_eq(profile.username, "lisi", "username")
    assert_false(profile.is_bot, "不是 bot")
    assert_true(profile.is_verified, "已认证")


def test_skill_not_started():
    print("\n📋 test_skill_not_started")
    skill = TelegramSkill(session_name="test")
    assert_false(skill.is_running, "未启动时 is_running 为 False")

    # 发送消息应返回错误
    async def _test():
        result = await skill.send_message(chat_id=1, text="test")
        assert_false(result.success, "未启动时发送应失败")
        assert_eq(result.error, "Skill 未启动", "错误信息应正确")

    asyncio.run(_test())


def test_handler_register_and_remove():
    print("\n📋 test_handler_register_and_remove")
    skill = TelegramSkill(session_name="test")

    def handler1(event): pass
    async def handler2(event): pass

    skill.on_new_message(handler1)
    skill.on_new_message(handler2)
    assert_eq(len(skill._handlers), 2, "注册后应有 2 个 handler")

    skill.remove_handler(handler1)
    assert_eq(len(skill._handlers), 1, "移除后应有 1 个 handler")
    assert_eq(skill._handlers[0], handler2, "剩余的是 handler2")


def test_conversation_context():
    print("\n📋 test_conversation_context")
    from skills.telegram.types import ConversationContext

    ctx = ConversationContext(chat_id=100, user_id=200)
    ctx.notes = "VIP 客户"
    ctx.tags = ["高意向", "已下单"]

    # 添加消息历史
    for i in range(55):
        msg = Message(message_id=i, chat_id=100, sender_id=200, text=f"msg {i}")
        ctx.add_message(msg)

    assert_eq(len(ctx.message_history), 50, "历史应截断到 50 条")
    assert_eq(ctx.message_history[-1].text, "msg 54", "最后一条应保留")


# ────────────────────────────── 主函数 ──────────────────────────────

def main():
    print("=" * 50)
    print(" Telegram Skill 单元测试")
    print("=" * 50)

    test_user_profile()
    test_chat_info()
    test_message_media_types()
    test_convert_message_text_only()
    test_convert_message_with_photo()
    test_convert_user()
    test_skill_not_started()
    test_handler_register_and_remove()
    test_conversation_context()

    print("\n" + "=" * 50)
    total = _tests_passed + _tests_failed
    print(f" 总计: {total} | ✅ 通过: {_tests_passed} | ❌ 失败: {_tests_failed}")
    print("=" * 50)

    return 0 if _tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
