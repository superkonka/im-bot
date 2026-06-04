#!/usr/bin/env python3
"""
WhatsApp Web Skill 演示

用法:
    .venv/bin/python src/skills/whatsapp_web/demo.py

流程:
    1. 启动浏览器，打开 WhatsApp Web
    2. 检查登录状态（如有保存的状态则自动恢复）
    3. 如未登录，提示扫码
    4. 获取聊天列表
    5. 演示发送消息（可选）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.whatsapp_web.skill import WhatsAppWebSkill


async def main():
    print("=" * 60)
    print("🟢 WhatsApp Web Skill 演示")
    print("=" * 60)

    # 启动（有头模式，方便扫码）
    skill = WhatsAppWebSkill(headless=False)
    await skill.start()

    try:
        # 检查登录状态
        if await skill.is_logged_in():
            print("\n✅ 已登录（状态已恢复）")
        else:
            print("\n📱 未登录，请用手机 WhatsApp App 扫码")
            print("   步骤: 设置 → 已关联设备 → 关联新设备")
            logged_in = await skill.wait_for_login(timeout=120)
            if not logged_in:
                print("\n❌ 登录超时")
                return

        # 获取聊天列表
        print("\n📋 获取聊天列表...")
        chats = await skill.get_chat_list()
        print(f"\n共 {len(chats)} 个聊天:\n")
        for c in chats:
            unread = f" 🔴 {c.unread_count} 未读" if c.unread_count > 0 else ""
            print(f"  • {c.title}{unread}")
            if c.last_message:
                print(f"    └─ {c.last_message[:60]}")

        # 演示：进入第一个聊天并读取消息
        if chats:
            target = chats[0]
            print(f"\n📂 进入聊天: {target.title}")
            if await skill.open_chat(target.chat_id):
                msgs = await skill.get_messages(limit=10)
                print(f"最近 {len(msgs)} 条消息:")
                for m in msgs:
                    direction = "📤 我" if m.is_outgoing else "📨 对方"
                    print(f"  {direction} [{m.timestamp}] {m.sender_name}: {m.text[:50]}")
            else:
                print("⚠️ 进入聊天失败")

        # 演示：加入群聊（可选，取消注释使用）
        # group_link = "https://chat.whatsapp.com/IQIaQjDG7EgEsJaG2jWv5C"
        # print(f"\n🔗 尝试加入群聊: {group_link}")
        # result = await skill.join_group_link(group_link)
        # print(f"结果: {result.status} - {result.error or '成功'}")

        print("\n✅ 演示完成")
        input("\n按回车键退出...")

    finally:
        await skill.stop()


if __name__ == "__main__":
    asyncio.run(main())
