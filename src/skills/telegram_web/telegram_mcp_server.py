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


@mcp.tool()
async def search_chat(query: str, limit: int = 10) -> str:
    """
    搜索 Telegram 聊天或联系人。

    通过 Telegram Web 搜索框搜索，返回匹配的聊天列表。
    支持搜索聊天标题、用户名、手机号等。

    Args:
        query: 搜索关键词（如"小波"、"@username"）
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
async def reply_to_message(chat_title: str, target_message_text: str, reply_text: str) -> str:
    """
    回复聊天中的特定消息。

    在指定聊天中查找包含 target_message_text 的消息，并回复它。
    支持模糊匹配，优先匹配最近的消息。

    Args:
        chat_title: 聊天标题（模糊匹配）
        target_message_text: 要回复的目标消息文本（部分匹配即可）
        reply_text: 回复内容
    """
    skill = await _get_skill()

    # 进入聊天
    try:
        locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(
            has_text=chat_title
        )
        if await locator.count() > 0:
            await locator.first.click()
        else:
            # 尝试搜索
            search_results = await skill.search_chat(chat_title)
            if search_results:
                await skill.open_chat(search_results[0].chat_id)
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"
    except Exception as e:
        return f"❌ 进入聊天失败: {e}"

    await asyncio.sleep(2)

    # 回复消息
    try:
        result = await skill.reply_to_message(target_message_text, reply_text)
        if result.success:
            return f"✅ 已回复 '{chat_title}' 的消息: {reply_text[:50]}"
        else:
            return f"❌ 回复失败: {result.error}"
    except Exception as e:
        return f"❌ 回复异常: {e}"


@mcp.tool()
async def forward_message(chat_title: str, target_message_text: str, to_chat_title: str) -> str:
    """
    转发消息到另一个聊天。

    在源聊天中查找包含 target_message_text 的消息，转发到目标聊天。
    只能转发自己可见的消息。

    Args:
        chat_title: 源聊天标题（消息所在聊天）
        target_message_text: 要转发的消息文本（部分匹配）
        to_chat_title: 目标聊天标题（模糊匹配）
    """
    skill = await _get_skill()

    # 进入源聊天
    try:
        locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(
            has_text=chat_title
        )
        if await locator.count() > 0:
            await locator.first.click()
        else:
            search_results = await skill.search_chat(chat_title)
            if search_results:
                await skill.open_chat(search_results[0].chat_id)
            else:
                return f"❌ 未找到源聊天 '{chat_title}'。"
    except Exception as e:
        return f"❌ 进入源聊天失败: {e}"

    await asyncio.sleep(2)

    # 查找目标聊天的 chat_id
    try:
        target_results = await skill.search_chat(to_chat_title)
        if not target_results:
            return f"❌ 未找到目标聊天 '{to_chat_title}'。"
        target_chat_id = target_results[0].chat_id

        result = await skill.forward_message(target_message_text, target_chat_id)
        if result.success:
            return f"✅ 已将 '{chat_title}' 中的消息转发到 '{to_chat_title}'"
        else:
            return f"❌ 转发失败: {result.error}"
    except Exception as e:
        return f"❌ 转发异常: {e}"


@mcp.tool()
async def delete_message(chat_title: str, message_text: str) -> str:
    """
    删除自己发送的消息。

    在指定聊天中查找包含 message_text 的自己发送的消息并删除。
    只能删除自己（Me）发送的消息，无法删除对方的消息。
    支持模糊匹配，优先删除最近的消息。

    Args:
        chat_title: 聊天标题（模糊匹配）
        message_text: 要删除的消息文本（部分匹配即可）
    """
    skill = await _get_skill()

    # 进入聊天
    try:
        locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(
            has_text=chat_title
        )
        if await locator.count() > 0:
            await locator.first.click()
        else:
            search_results = await skill.search_chat(chat_title)
            if search_results:
                await skill.open_chat(search_results[0].chat_id)
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"
    except Exception as e:
        return f"❌ 进入聊天失败: {e}"

    await asyncio.sleep(2)

    try:
        result = await skill.delete_message(message_text)
        if result:
            return f"✅ 已删除 '{chat_title}' 中包含 '{message_text[:30]}' 的消息。"
        else:
            return f"⚠️ 未找到可删除的消息。只能删除自己发送的消息。"
    except Exception as e:
        return f"❌ 删除失败: {e}"


@mcp.tool()
async def mark_as_read(chat_title: str) -> str:
    """
    将指定聊天标记为已读。

    清除该聊天的未读消息标记。

    Args:
        chat_title: 聊天标题（模糊匹配）
    """
    skill = await _get_skill()

    # 获取聊天列表找到 chat_id
    try:
        chats = await skill.get_chat_list(limit=50)
        target_chat = None
        for chat in chats:
            if chat_title.lower() in chat.title.lower() or chat.title.lower() in chat_title.lower():
                target_chat = chat
                break

        if not target_chat:
            # 尝试搜索
            search_results = await skill.search_chat(chat_title)
            if search_results:
                target_chat = search_results[0]
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"

        result = await skill.mark_as_read(target_chat.chat_id)
        if result:
            return f"✅ 已将 '{target_chat.title}' 标记为已读。"
        else:
            return f"⚠️ 标记已读操作未生效（可能已经是已读状态或操作被拦截）。"
    except Exception as e:
        return f"❌ 标记已读失败: {e}"


@mcp.tool()
async def get_chat_info(chat_title: str) -> str:
    """
    获取指定聊天的详细信息。

    包括聊天标题、类型（私聊/群组/频道）、成员数、描述、用户名等。

    Args:
        chat_title: 聊天标题（模糊匹配）
    """
    skill = await _get_skill()

    # 获取聊天列表找到 chat_id
    try:
        chats = await skill.get_chat_list(limit=50)
        target_chat = None
        for chat in chats:
            if chat_title.lower() in chat.title.lower() or chat.title.lower() in chat_title.lower():
                target_chat = chat
                break

        if not target_chat:
            search_results = await skill.search_chat(chat_title)
            if search_results:
                target_chat = search_results[0]
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"

        info = await skill.get_chat_info(target_chat.chat_id)

        lines = [f"📂 聊天信息: {info.get('title', target_chat.title)}\n"]
        lines.append(f"类型: {info.get('type', 'unknown')}")
        if info.get('member_count'):
            lines.append(f"成员数: {info['member_count']}")
        if info.get('description'):
            lines.append(f"描述: {info['description']}")
        if info.get('username'):
            lines.append(f"用户名: @{info['username']}")
        if info.get('link'):
            lines.append(f"链接: {info['link']}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取聊天信息失败: {e}"


@mcp.tool()
async def pin_chat(chat_title: str, pin: bool = True) -> str:
    """
    置顶或取消置顶聊天。

    Args:
        chat_title: 聊天标题（模糊匹配）
        pin: True 表示置顶，False 表示取消置顶
    """
    skill = await _get_skill()

    try:
        chats = await skill.get_chat_list(limit=50)
        target_chat = None
        for chat in chats:
            if chat_title.lower() in chat.title.lower() or chat.title.lower() in chat_title.lower():
                target_chat = chat
                break

        if not target_chat:
            search_results = await skill.search_chat(chat_title)
            if search_results:
                target_chat = search_results[0]
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"

        result = await skill.pin_chat(target_chat.chat_id, pin=pin)
        action = "置顶" if pin else "取消置顶"
        if result:
            return f"✅ 已将 '{target_chat.title}' {action}。"
        else:
            return f"⚠️ {action}操作未生效。"
    except Exception as e:
        return f"❌ {('置顶' if pin else '取消置顶')}失败: {e}"


@mcp.tool()
async def archive_chat(chat_title: str) -> str:
    """
    归档指定聊天。

    将聊天移入归档文件夹，不再显示在主聊天列表中。

    Args:
        chat_title: 聊天标题（模糊匹配）
    """
    skill = await _get_skill()

    try:
        chats = await skill.get_chat_list(limit=50)
        target_chat = None
        for chat in chats:
            if chat_title.lower() in chat.title.lower() or chat.title.lower() in chat_title.lower():
                target_chat = chat
                break

        if not target_chat:
            search_results = await skill.search_chat(chat_title)
            if search_results:
                target_chat = search_results[0]
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"

        result = await skill.archive_chat(target_chat.chat_id)
        if result:
            return f"✅ 已将 '{target_chat.title}' 归档。"
        else:
            return f"⚠️ 归档操作未生效。"
    except Exception as e:
        return f"❌ 归档失败: {e}"


@mcp.tool()
async def get_contacts(limit: int = 50) -> str:
    """
    获取 Telegram 联系人列表。

    返回所有已保存联系人的用户名和最后上线时间。

    Args:
        limit: 最多返回多少个联系人，默认 50
    """
    skill = await _get_skill()
    await asyncio.sleep(2)

    # 通过侧边栏菜单进入 Contacts
    try:
        # 点击菜单按钮
        menu_btn = await skill.page.query_selector('.sidebar-header .btn-menu, button[aria-label="Menu"]')
        if menu_btn:
            await menu_btn.click()
            await asyncio.sleep(0.5)

            # 点击 Contacts
            contacts_selectors = [
                'text-is("Contacts")',
                'text-is("联系人")',
                '.menu-item:has-text("Contacts")',
            ]
            for sel in contacts_selectors:
                try:
                    contacts_btn = await skill.page.wait_for_selector(sel, timeout=1000)
                    if contacts_btn:
                        await contacts_btn.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue

        # 提取联系人列表
        contacts = await skill.page.evaluate(f"""
            () => {{
                const results = [];
                document.querySelectorAll('.chatlist-chat, .row-clickable').forEach(el => {{
                    const titleEl = el.querySelector('.chat-title, .title, .row-title');
                    const statusEl = el.querySelector('.chat-subtitle, .status, .row-subtitle');
                    let title = titleEl ? titleEl.innerText.trim() : '';
                    let status = statusEl ? statusEl.innerText.trim() : '';
                    if (title) {{
                        results.push({{title, status}});
                    }}
                }});
                return results.slice(0, {limit});
            }}
        """)

        if not contacts:
            # 返回聊天列表页
            await skill.page.goto(skill.URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            return "未获取到联系人列表，可能页面结构不符。"

        lines = [f"👥 联系人列表（共 {len(contacts)} 人）：\n"]
        for c in contacts:
            status = f" ({c.get('status', '')})" if c.get('status') else ""
            lines.append(f"• {c['title']}{status}")

        # 返回聊天列表页
        await skill.page.goto(skill.URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取联系人失败: {e}"


@mcp.tool()
async def get_message_by_keyword(chat_title: str, keyword: str, limit: int = 20) -> str:
    """
    在指定聊天中搜索包含关键词的消息。

    获取聊天消息并筛选出包含关键词的消息。

    Args:
        chat_title: 聊天标题（模糊匹配）
        keyword: 搜索关键词
        limit: 最多检查多少条消息，默认 20
    """
    skill = await _get_skill()

    # 进入聊天
    try:
        locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(
            has_text=chat_title
        )
        if await locator.count() > 0:
            await locator.first.click()
        else:
            search_results = await skill.search_chat(chat_title)
            if search_results:
                await skill.open_chat(search_results[0].chat_id)
            else:
                return f"❌ 未找到标题包含 '{chat_title}' 的聊天。"
    except Exception as e:
        return f"❌ 进入聊天失败: {e}"

    await asyncio.sleep(2)

    # 提取所有消息并筛选
    messages = await skill.page.evaluate(f"""
        () => {{
            const results = [];
            const bubbles = document.querySelectorAll('.bubble');
            const msgs = Array.from(bubbles).slice(-{limit});
            msgs.forEach((el) => {{
                let text = '';
                const textEl = el.querySelector('.message-text, .text');
                if (textEl) {{
                    text = textEl.innerText.trim();
                }} else {{
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('.message-time, .time, .message-status').forEach(e => e.remove());
                    text = clone.innerText.trim();
                }}

                if (text.toLowerCase().includes('{keyword.lower()}')) {{
                    let sender = '';
                    const nameEl = el.querySelector('.name, .peer-title');
                    if (nameEl) sender = nameEl.innerText.trim();
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
                }}
            }});
            return results;
        }}
    """)

    if not messages:
        return f"📂 聊天: {chat_title}\n在最近 {limit} 条消息中未找到包含 '{keyword}' 的消息。"

    lines = [f"📂 聊天: {chat_title}\n搜索 '{keyword}'，找到 {len(messages)} 条相关消息：\n"]
    for m in messages:
        direction = "📤 我" if m.get("is_me") else "📨 对方"
        time = m.get("time", "")
        sender = m.get("sender", "Unknown")
        text = m.get("text", "")
        lines.append(f"{direction} [{time}] {sender}: {text}")

    return "\n".join(lines)


# ── 启动入口 ──
if __name__ == "__main__":
    mcp.run()
