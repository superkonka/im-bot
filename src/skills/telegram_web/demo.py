#!/usr/bin/env python3
"""
Telegram Web Skill 演示

用法:
    .venv/bin/python src/skills/telegram_web/demo.py

支持两种登录方式:
    1. 手机号 + 验证码（适合无头模式）
    2. 二维码扫码（推荐有头浏览器，无需等短信）
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

from skills.telegram_web.skill import TelegramWebSkill

PHONE = os.environ.get("TELEGRAM_PHONE", "")


async def choose_login_method(skill: TelegramWebSkill, use_qr: bool = True) -> bool:
    """选择并执行登录方式"""
    if use_qr:
        print("\n[登录] 使用二维码扫码方式...")
        return await skill.login_by_qr_code(timeout=120.0)
    else:
        print("\n[登录] 使用手机号验证码方式...")
        return await skill.login(
            phone=PHONE,
            code_callback=lambda: input("\n请输入验证码（5位数字）: "),
            password_callback=lambda: input("请输入两步验证密码（如无直接回车）: ") or None,
        )


async def main():
    skill = TelegramWebSkill(headless=False)

    print("=" * 50)
    print(" Telegram Web Skill 演示")
    print("=" * 50)

    try:
        # 1. 启动
        print("\n[1/4] 启动浏览器并打开 Telegram Web...")
        await skill.start()

        # 2. 检查登录状态
        print("\n[2/4] 检查登录状态...")
        if await skill.is_logged_in():
            print("✅ 已登录（从保存的状态恢复）")
        else:
            print("📝 未登录，需要登录...")
            success = await choose_login_method(skill, use_qr=True)
            if not success:
                print("❌ 登录失败")
                return

        # 3. 获取聊天列表
        print("\n[3/4] 获取聊天列表...")
        chats = await skill.get_chat_list(limit=10)
        print(f"找到 {len(chats)} 个聊天:")
        for i, chat in enumerate(chats):
            unread = f" [{chat.unread_count}未读]" if chat.unread_count > 0 else ""
            print(f"  {i+1}. {chat.title}{unread}")
            if chat.last_message:
                print(f"     最后消息: {chat.last_message[:40]}...")

        # 4. 打开第一个有未读的聊天，显示最近消息
        unread_chats = [c for c in chats if c.unread_count > 0]
        if unread_chats:
            chat = unread_chats[0]
            print(f"\n[4/4] 打开聊天: {chat.title}")
            await skill.open_chat(chat.chat_id)

            messages = await skill.get_messages(limit=5)
            print(f"最近 {len(messages)} 条消息:")
            for msg in messages:
                direction = "📤" if msg.is_outgoing else "📨"
                print(f"  {direction} {msg.sender_name}: {msg.text[:60]}")

            # 可选：发送测试消息
            # await skill.send_message("你好！这是自动化测试消息。")
            # print("✅ 测试消息已发送")

        else:
            print("\n[4/4] 没有未读消息，跳过消息展示")

        # 5. 开始轮询新消息
        print("\n--- 开始轮询新消息（按 Ctrl+C 停止）---")
        await skill.poll_new_messages(interval=5.0)

    except KeyboardInterrupt:
        print("\n\n用户中断")
    finally:
        await skill.stop()
        print("\n已清理退出")


if __name__ == "__main__":
    asyncio.run(main())
