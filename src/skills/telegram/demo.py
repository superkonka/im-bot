#!/usr/bin/env python3
"""
Telegram Skill 使用示例

运行前:
1. 安装依赖: pip install telethon
2. 到 https://my.telegram.org/apps 创建应用，获取 api_id 和 api_hash
3. 首次运行会要求输入手机号和验证码

用法:
    python -m src.skills.telegram.demo
"""
from __future__ import annotations

import asyncio
import os

try:
    from .skill import TelegramSkill
    from .types import MessageEvent
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from skills.telegram.skill import TelegramSkill
    from skills.telegram.types import MessageEvent


# 从环境变量读取（推荐）
API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
PHONE = os.getenv("TELEGRAM_PHONE", "")


async def main():
    if not API_ID or not API_HASH:
        print("请设置环境变量 TELEGRAM_API_ID 和 TELEGRAM_API_HASH")
        print("获取地址: https://my.telegram.org/apps")
        return

    skill = TelegramSkill(session_name="demo")

    # ── 启动 ──
    print("正在连接 Telegram...")
    await skill.start(
        api_id=API_ID,
        api_hash=API_HASH,
        phone=PHONE or None,
        code_callback=lambda: input("请输入验证码: "),
        password_callback=lambda: input("请输入两步验证密码（如无直接回车）: ") or None,
    )

    # ── 获取当前账号信息 ──
    me = await skill.get_me()
    print(f"\n当前账号: {me.display_name} (@{me.username or '无'})")

    # ── 列出有未读消息的聊天 ──
    print("\n--- 有未读消息的聊天 ---")
    unread_chats = await skill.list_chats(unread_only=True)
    for chat in unread_chats[:5]:
        print(f"  [{chat.unread_count}未读] {chat.display_name} (ID: {chat.chat_id})")

    # ── 监听新消息 ──
    print("\n--- 开始监听新消息（按 Ctrl+C 停止）---")

    async def on_message(event: MessageEvent):
        chat_name = event.chat.display_name
        sender_name = event.sender.display_name
        text = event.message.text[:50] + "..." if len(event.message.text) > 50 else event.message.text

        print(f"\n📨 [{chat_name}] {sender_name}: {text}")

        # 自动回复示例（谨慎使用！）
        if event.is_first_contact:
            reply = f"你好 {sender_name}！👋 我已收到你的消息，稍后回复你。"
            await skill.send_typing(event.chat.chat_id, duration=1.5)
            result = await skill.send_message(event.chat.chat_id, reply)
            if result.success:
                print(f"   ✅ 自动回复已发送 (msg_id={result.message_id})")
            else:
                print(f"   ❌ 发送失败: {result.error}")

    skill.on_new_message(on_message)

    # 保持运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\n正在停止...")

    await skill.stop()
    print("已断开连接")


if __name__ == "__main__":
    asyncio.run(main())
