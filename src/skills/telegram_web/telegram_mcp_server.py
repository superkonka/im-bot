#!/usr/bin/env python3
"""
Telegram Web MCP Server

将 Telegram Web Skill 封装为 MCP (Model Context Protocol) Server，
使 Claude Desktop、Cursor 等 AI 客户端可以直接调用。

用法:
    .venv/bin/python src/skills/telegram_web/telegram_mcp_server.py

配置到 Claude Desktop:
    编辑 ~/Library/Application Support/Claude/claude_desktop_config.json
    {
      "mcpServers": {
        "telegram": {
          "command": "/Users/konka/im-bot/.venv/bin/python",
          "args": ["-m", "src.skills.telegram_web.telegram_mcp_server"]
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastmcp import FastMCP
from skills.telegram_web.skill import TelegramWebSkill

# ── 初始化 MCP Server ──
mcp = FastMCP("telegram-web")

# ── 全局 Skill 实例（懒加载）─
_skill: Optional[TelegramWebSkill] = None
_skill_lock = asyncio.Lock()


async def _get_skill() -> TelegramWebSkill:
    """获取或初始化 Skill"""
    global _skill
    if _skill is None:
        async with _skill_lock:
            if _skill is None:
                _skill = TelegramWebSkill(headless=True)
                await _skill.start()
                if not await _skill.is_logged_in():
                    # 尝试扫码登录流程（无头模式下会失败，需要提前登录）
                    raise RuntimeError(
                        "Telegram Web 未登录。请先运行 demo.py 完成登录，"
                        "状态会自动保存。"
                    )
    return _skill


@mcp.tool()
async def get_chat_list(limit: int = 20) -> str:
    """
    获取 Telegram 聊天列表。

    返回最近的聊天会话，包括标题、最后消息、未读数等。

    Args:
        limit: 最多返回多少个聊天，默认 20
    """
    skill = await _get_skill()

    # 等待页面加载
    await asyncio.sleep(3)

    chats = await skill.page.evaluate(f"""
        () => {{
            const results = [];
            const items = document.querySelectorAll('.chatlist-chat, .row-clickable');
            items.forEach((el, idx) => {{
                if (idx >= {limit}) return;
                const titleEl = el.querySelector('.dialog-title, .row-title');
                const subtitleEl = el.querySelector('.dialog-subtitle, .row-subtitle');
                const badgeEl = el.querySelector('.badge:not(.is-badge-empty)');
                const pinnedEl = el.querySelector('.dialog-subtitle-badge-pinned');

                let title = titleEl ? titleEl.innerText.trim() : '';
                let subtitle = subtitleEl ? subtitleEl.innerText.trim() : '';
                let unread = badgeEl ? (parseInt(badgeEl.innerText.trim()) || 0) : 0;
                let isPinned = !!pinnedEl;

                if (title && !title.includes('Never miss') && !title.includes('Enable notifications')) {{
                    results.push({{idx, title, subtitle: subtitle.slice(0, 60), unread, isPinned}});
                }}
            }});
            return results;
        }}
    """)

    if not chats:
        return "暂无聊天数据，页面可能还在加载中。"

    lines = [f"共 {len(chats)} 个会话：\n"]
    for c in chats:
        unread = f" 🔴 {c['unread']} 未读" if c.get("unread", 0) > 0 else ""
        pinned = " 📌 置顶" if c.get("isPinned") else ""
        lines.append(f"{c['idx']}. {c['title']}{pinned}{unread}")
        lines.append(f"   └─ {c['subtitle']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def get_messages(chat_title: str, limit: int = 20) -> str:
    """
    获取指定聊天的最近消息。

    通过聊天标题匹配并进入聊天，提取最近的消息内容。

    Args:
        chat_title: 聊天标题（模糊匹配，如"小波"）
        limit: 最多返回多少条消息，默认 20
    """
    skill = await _get_skill()

    # 点击聊天
    try:
        locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(
            has_text=chat_title
        )
        if await locator.count() > 0:
            await locator.first.click()
        else:
            return f"未找到标题包含 '{chat_title}' 的聊天。"
    except Exception as e:
        return f"进入聊天失败: {e}"

    await asyncio.sleep(2)

    # 提取消息
    messages = await skill.page.evaluate(f"""
        () => {{
            const results = [];
            const bubbles = document.querySelectorAll('.bubble');
            const msgs = Array.from(bubbles).slice(-{limit});
            msgs.forEach((el, idx) => {{
                if (el.classList.contains('is-date')) {{
                    results.push({{sender: 'System', text: '[日期: ' + el.innerText.trim() + ']', time: ''}});
                    return;
                }}

                let sender = '';
                const nameEl = el.querySelector('.name, .peer-title, .post-author');
                if (nameEl) sender = nameEl.innerText.trim();

                let text = '';
                const textEl = el.querySelector('.bubble-content, .service-msg');
                if (textEl) {{
                    text = textEl.innerText.trim();
                }} else {{
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('.message-time, .time, .message-status').forEach(e => e.remove());
                    text = clone.innerText.trim();
                }}

                const isOutgoing = el.classList.contains('is-out') || el.classList.contains('own');
                let time = '';
                const timeEl = el.querySelector('.message-time, .time');
                if (timeEl) time = timeEl.innerText.trim();

                results.push({{
                    sender: sender || (isOutgoing ? 'Me' : 'Unknown'),
                    text: text.slice(0, 200),
                    time: time,
                    is_me: isOutgoing,
                }});
            }});
            return results;
        }}
    """)

    if not messages:
        return "该聊天暂无消息。"

    lines = [f"📂 聊天: {chat_title}\n最近 {len(messages)} 条消息:\n"]
    for m in messages:
        direction = "📤 我" if m.get("is_me") else "📨 对方"
        time = m.get("time", "")
        sender = m.get("sender", "Unknown")
        text = m.get("text", "")
        lines.append(f"{direction} [{time}] {sender}: {text}")

    return "\n".join(lines)


@mcp.tool()
async def send_message(chat_title: str, text: str) -> str:
    """
    向指定聊天发送消息。

    注意：此操作会实际发送消息到真实联系人，请谨慎使用。

    Args:
        chat_title: 聊天标题（模糊匹配）
        text: 要发送的消息内容
    """
    skill = await _get_skill()

    # 点击聊天
    try:
        locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(
            has_text=chat_title
        )
        if await locator.count() > 0:
            await locator.first.click()
        else:
            return f"未找到标题包含 '{chat_title}' 的聊天。"
    except Exception as e:
        return f"进入聊天失败: {e}"

    await asyncio.sleep(2)

    # 输入并发送
    try:
        input_selector = '#editable-message-text, div[contenteditable="true"]'
        input_el = skill.page.locator(input_selector).first
        await input_el.fill(text)
        await asyncio.sleep(0.5)

        # 点击发送按钮或按回车
        send_btn = skill.page.locator('.btn-send, button[aria-label*="Send"]').first
        if await send_btn.count() > 0:
            await send_btn.click()
        else:
            await skill.page.keyboard.press("Enter")

        return f"✅ 消息已发送到 '{chat_title}': {text[:50]}"
    except Exception as e:
        return f"❌ 发送失败: {e}"


@mcp.tool()
async def get_unread_summary() -> str:
    """
    获取所有未读消息的摘要。

    返回每个有未读消息的聊天的标题和未读数量。
    """
    skill = await _get_skill()
    await asyncio.sleep(3)

    chats = await skill.page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('.chatlist-chat, .row-clickable').forEach(el => {
                const titleEl = el.querySelector('.dialog-title, .row-title');
                const badgeEl = el.querySelector('.badge:not(.is-badge-empty)');
                let title = titleEl ? titleEl.innerText.trim() : '';
                let unread = badgeEl ? (parseInt(badgeEl.innerText.trim()) || 0) : 0;
                if (title && unread > 0 && !title.includes('Never miss')) {
                    results.push({title, unread});
                }
            });
            return results;
        }
    """)

    if not chats:
        return "✅ 所有消息已读，没有未读消息。"

    total = sum(c["unread"] for c in chats)
    lines = [f"🔴 共 {len(chats)} 个聊天有未读消息，总计 {total} 条：\n"]
    for c in chats:
        lines.append(f"• {c['title']}: {c['unread']} 未读")

    return "\n".join(lines)


@mcp.tool()
async def get_contact_info() -> str:
    """
    获取当前登录的 Telegram 账号信息。
    """
    skill = await _get_skill()
    await asyncio.sleep(2)

    info = await skill.page.evaluate("""
        () => {
            // 尝试从页面标题或设置中获取用户信息
            const title = document.title;
            const avatar = document.querySelector('.sidebar-header-avatar');
            return {title};
        }
    """)

    return f"当前 Telegram Web 页面: {info.get('title', 'Unknown')}\n状态: 已登录"


# ── 启动入口 ──
if __name__ == "__main__":
    mcp.run()
