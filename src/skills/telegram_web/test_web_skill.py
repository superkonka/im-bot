#!/usr/bin/env python3
"""
Telegram Web Skill 功能测试

使用已保存的登录状态，测试所有核心功能：
1. 启动浏览器 + 恢复登录状态
2. 获取聊天列表
3. 进入聊天 + 读取消息
4. 发送测试消息（可选）

用法:
    .venv/bin/python src/skills/telegram_web/test_web_skill.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

from skills.telegram_web.skill import TelegramWebSkill


async def test_start_and_login():
    """测试 1: 启动并验证登录状态"""
    print("\n" + "=" * 60)
    print(" 测试 1: 启动浏览器 + 恢复登录状态")
    print("=" * 60)

    skill = TelegramWebSkill(headless=False)
    await skill.start()

    is_logged = await skill.is_logged_in()
    print(f"登录状态: {'✅ 已登录' if is_logged else '❌ 未登录'}")

    if not is_logged:
        print("⚠️  未检测到登录状态，可能 session 已过期")
        await skill.stop()
        return None

    return skill


async def test_chat_list(skill: TelegramWebSkill):
    """测试 2: 获取聊天列表"""
    print("\n" + "=" * 60)
    print(" 测试 2: 获取聊天列表")
    print("=" * 60)

    chats = await skill.get_chat_list(limit=15)
    print(f"共找到 {len(chats)} 个聊天:")
    print()

    for i, chat in enumerate(chats):
        unread = f" 🔴 {chat.unread_count} 未读" if chat.unread_count > 0 else ""
        print(f"  {i+1:2d}. {chat.title[:30]:30s}{unread}")
        if chat.last_message:
            preview = chat.last_message[:40].replace("\n", " ")
            print(f"      └─ {preview}...")

    return chats


async def test_read_messages(skill: TelegramWebSkill, chats: list):
    """测试 3: 进入聊天并读取消息"""
    print("\n" + "=" * 60)
    print(" 测试 3: 读取聊天消息")
    print("=" * 60)

    # 优先选择有未读消息的聊天
    target = None
    for chat in chats:
        if chat.unread_count > 0:
            target = chat
            break

    # 如果没有未读，选第一个
    if not target and chats:
        target = chats[0]

    if not target:
        print("⚠️  没有可用的聊天")
        return

    print(f"打开聊天: {target.title} (ID: {target.chat_id})")
    success = await skill.open_chat(target.chat_id)

    if not success:
        print("❌ 无法打开聊天")
        return

    print("✅ 聊天已打开，读取最近 10 条消息...")
    messages = await skill.get_messages(limit=10)

    print(f"\n最近 {len(messages)} 条消息:")
    print("-" * 50)
    for msg in messages:
        direction = "📤 我" if msg.is_outgoing else "📨 对方"
        sender = msg.sender_name[:15] if not msg.is_outgoing else "我"
        text = msg.text[:60].replace("\n", " ") if msg.text else "[空消息/媒体]"
        print(f"  {direction:6s} | {sender:15s} | {text}")
    print("-" * 50)

    return target


async def test_send_message(skill: TelegramWebSkill, chat_id: str):
    """测试 4: 发送消息（需要用户确认）"""
    print("\n" + "=" * 60)
    print(" 测试 4: 发送消息")
    print("=" * 60)

    print("⚠️  此测试会向真实聊天发送消息！")
    # 非交互环境，默认跳过发送测试
    print("⏭️  跳过发送测试（避免打扰真实联系人）")
    print("    如需测试发送，手动执行:")
    print(f"    await skill.send_message('测试消息')")
    return


async def test_screenshot(skill: TelegramWebSkill):
    """测试 5: 截图调试"""
    print("\n" + "=" * 60)
    print(" 测试 5: 页面截图")
    print("=" * 60)

    path = await skill.take_screenshot()
    print(f"✅ 截图已保存: {path}")


async def main():
    print("=" * 60)
    print(" Telegram Web Skill 功能测试")
    print("=" * 60)

    # 测试 1: 启动
    skill = await test_start_and_login()
    if not skill:
        print("\n❌ 测试中止：未登录")
        return 1

    try:
        # 测试 2: 聊天列表
        chats = await test_chat_list(skill)

        # 测试 3: 读取消息
        if chats:
            await test_read_messages(skill, chats)

        # 测试 4: 发送消息（跳过）
        # await test_send_message(skill, "")

        # 测试 5: 截图
        await test_screenshot(skill)

        print("\n" + "=" * 60)
        print(" ✅ 所有测试完成")
        print("=" * 60)

        # 保持浏览器打开一会儿，方便用户查看
        print("\n浏览器将保持打开 30 秒，方便查看...")
        print("按 Ctrl+C 提前结束")
        await asyncio.sleep(30)

    except KeyboardInterrupt:
        print("\n\n用户中断")
    finally:
        await skill.stop()
        print("\n已清理退出")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
