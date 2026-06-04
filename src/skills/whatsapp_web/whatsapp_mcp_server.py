#!/usr/bin/env python3
"""
WhatsApp Web MCP Server

将 WhatsApp Web Skill 封装为 MCP (Model Context Protocol) Server，
使 Claude Desktop、Cursor 等 AI 客户端可以直接调用。

用法:
    .venv/bin/python src/skills/whatsapp_web/whatsapp_mcp_server.py

配置到 Claude Desktop:
    编辑 ~/Library/Application Support/Claude/claude_desktop_config.json
    {
      "mcpServers": {
        "whatsapp": {
          "command": "/Users/konka/im-bot/.venv/bin/python",
          "args": ["/Users/konka/im-bot/src/skills/whatsapp_web/whatsapp_mcp_server.py"]
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastmcp import FastMCP
from skills.whatsapp_web.skill import WhatsAppWebSkill

# ── 初始化 MCP Server ──
mcp = FastMCP("whatsapp-web")

# ── 全局 Skill 实例（懒加载）─
_skill: Optional[WhatsAppWebSkill] = None
_skill_lock = asyncio.Lock()


async def _get_skill() -> WhatsAppWebSkill:
    """获取或初始化 Skill"""
    global _skill
    if _skill is None:
        async with _skill_lock:
            if _skill is None:
                _skill = WhatsAppWebSkill(headless=True)
                await _skill.start()
                if not await _skill.is_logged_in():
                    raise RuntimeError(
                        "WhatsApp Web 未登录。请先运行 demo.py 完成登录:\n"
                        "  .venv/bin/python src/skills/whatsapp_web/demo.py"
                    )
    return _skill


@mcp.tool()
async def get_chat_list(limit: int = 20) -> str:
    """
    获取 WhatsApp 聊天列表。

    返回最近的聊天会话，包括标题、最后消息、未读数等。

    Args:
        limit: 最多返回多少个聊天，默认 20
    """
    skill = await _get_skill()
    await asyncio.sleep(2)

    chats = await skill.get_chat_list(limit=limit)

    if not chats:
        return "暂无聊天数据，页面可能还在加载中。"

    lines = [f"共 {len(chats)} 个会话：\n"]
    for i, c in enumerate(chats):
        unread = f" 🔴 {c.unread_count} 未读" if c.unread_count > 0 else ""
        pinned = " 📌 置顶" if c.is_pinned else ""
        lines.append(f"{i}. {c.title}{pinned}{unread}")
        if c.last_message:
            lines.append(f"   └─ {c.last_message[:60]}")

    return "\n".join(lines)


@mcp.tool()
async def get_messages(chat_title: str, limit: int = 20) -> str:
    """
    获取指定 WhatsApp 聊天的最近消息。

    通过聊天标题匹配并进入聊天，提取最近的消息内容。

    Args:
        chat_title: 聊天标题（模糊匹配，如"小波"）
        limit: 最多返回多少条消息，默认 20
    """
    skill = await _get_skill()

    # 打开聊天
    success = await skill.open_chat_by_title(chat_title)
    if not success:
        return f"未找到标题包含 '{chat_title}' 的聊天。"

    await asyncio.sleep(2)

    # 提取消息
    messages = await skill.get_messages(limit=limit)

    if not messages:
        return "该聊天暂无消息。"

    lines = [f"📂 聊天: {chat_title}\n最近 {len(messages)} 条消息:\n"]
    for m in messages:
        direction = "📤 我" if m.is_outgoing else "📨 对方"
        time = m.timestamp or ""
        sender = m.sender_name or "Unknown"
        text = m.text or ""
        lines.append(f"{direction} [{time}] {sender}: {text}")

    return "\n".join(lines)


@mcp.tool()
async def send_message(chat_title: str, text: str) -> str:
    """
    向指定 WhatsApp 聊天发送消息。

    注意：此操作会实际发送消息到真实联系人，请谨慎使用。

    Args:
        chat_title: 聊天标题（模糊匹配）
        text: 要发送的消息内容
    """
    skill = await _get_skill()

    # 打开聊天
    success = await skill.open_chat_by_title(chat_title)
    if not success:
        return f"未找到标题包含 '{chat_title}' 的聊天。"

    await asyncio.sleep(2)

    # 发送消息
    result = await skill.send_message(text)
    if result.success:
        return f"✅ 消息已发送到 '{chat_title}': {text[:50]}"
    else:
        return f"❌ 发送失败: {result.error}"


@mcp.tool()
async def get_unread_summary() -> str:
    """
    获取所有 WhatsApp 未读消息的摘要。

    返回每个有未读消息的聊天的标题和未读数量。
    """
    skill = await _get_skill()
    await asyncio.sleep(2)

    chats = await skill.get_chat_list(limit=50)
    unread_chats = [c for c in chats if c.unread_count > 0]

    if not unread_chats:
        return "✅ 所有消息已读，没有未读消息。"

    total = sum(c.unread_count for c in unread_chats)
    lines = [f"🔴 共 {len(unread_chats)} 个聊天有未读消息，总计 {total} 条：\n"]
    for c in unread_chats:
        lines.append(f"• {c.title}: {c.unread_count} 未读")

    return "\n".join(lines)


@mcp.tool()
async def search_chat(query: str, limit: int = 10) -> str:
    """
    搜索 WhatsApp 聊天或联系人。

    通过 WhatsApp Web 搜索框搜索，返回匹配的聊天列表。

    Args:
        query: 搜索关键词（如"小波"）
        limit: 最多返回多少个结果，默认 10
    """
    skill = await _get_skill()

    try:
        results = await skill.search_chat(query)
    except Exception as e:
        return f"❌ 搜索失败: {e}"

    if not results:
        return f"未找到与 '{query}' 相关的聊天或联系人。"

    lines = [f"🔍 搜索 '{query}'，找到 {len(results)} 个结果：\n"]
    for i, chat in enumerate(results[:limit]):
        lines.append(f"{i + 1}. {chat.title}")
        if chat.last_message:
            lines.append(f"   └─ {chat.last_message[:60]}")

    return "\n".join(lines)


@mcp.tool()
async def join_group_link(group_link: str) -> str:
    """
    通过链接加入 WhatsApp 群组。

    支持处理需要管理员批准的群组。

    Args:
        group_link: 群链接，如 "https://chat.whatsapp.com/XXXX"
    """
    skill = await _get_skill()

    if not group_link.startswith("https://chat.whatsapp.com/"):
        return "❌ 无效的 WhatsApp 群链接，必须以 https://chat.whatsapp.com/ 开头"

    try:
        result = await skill.join_group_link(group_link)
        if result.status == "joined":
            return f"✅ 已成功加入群组"
        elif result.status == "pending_approval":
            return f"⏳ 已发送加入请求，等待管理员批准"
        elif result.status == "already_member":
            return f"ℹ️ 你已经是该群成员"
        else:
            return f"❌ 加入失败: {result.error}"
    except Exception as e:
        return f"❌ 加入异常: {e}"


@mcp.tool()
async def get_contact_info() -> str:
    """
    获取当前登录的 WhatsApp 账号信息。
    """
    skill = await _get_skill()
    await asyncio.sleep(1)

    info = await skill.page.evaluate("""
        () => {
            const title = document.title;
            return {title};
        }
    """)

    return f"当前 WhatsApp Web 页面: {info.get('title', 'Unknown')}\n状态: 已登录"


# ── 启动入口 ──
if __name__ == "__main__":
    mcp.run()
