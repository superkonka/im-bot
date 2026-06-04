#!/usr/bin/env python3
"""
Telegram Web 持续爬取循环

用法:
    .venv/bin/python src/skills/telegram_web/crawler_loop.py

功能:
    - 持续监控聊天列表
    - 检测未读消息
    - 进入聊天并提取消息（通过 JavaScript，绕过 CSS 选择器问题）
    - 保存数据到 data/telegram_crawl/
    - 支持 graceful shutdown
"""
from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.telegram_web.skill import TelegramWebSkill

# 数据保存目录
CRAWL_DIR = Path(__file__).parent.parent.parent.parent / "data" / "telegram_crawl"
CRAWL_DIR.mkdir(exist_ok=True)

# 全局停止标志
_should_stop = False


def _handle_sigint(signum, frame):
    global _should_stop
    print("\n[Loop] 收到停止信号，正在优雅退出...")
    _should_stop = True


signal.signal(signal.SIGINT, _handle_sigint)


def _save_json(data: dict, filename: str):
    # 清理文件名中的非法字符
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "-_.")
    if not safe_filename:
        safe_filename = "unnamed"
    path = CRAWL_DIR / safe_filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


async def crawl_chat_list(skill: TelegramWebSkill) -> List[dict]:
    """爬取聊天列表"""
    if not skill.page:
        return []

    # 用 JavaScript 直接读取 DOM，比 CSS 选择器更可靠
    chats = await skill.page.evaluate("""
        () => {
            const results = [];
            const chatItems = document.querySelectorAll('.chatlist-chat, .row-clickable');
            chatItems.forEach((el, idx) => {
                // 标题
                let title = '';
                const titleEl = el.querySelector('.dialog-title, .row-title');
                if (titleEl) title = titleEl.innerText.trim();

                // 最后消息
                let lastMsg = '';
                const msgEl = el.querySelector('.dialog-subtitle, .row-subtitle');
                if (msgEl) lastMsg = msgEl.innerText.trim();

                // 未读数
                let unread = 0;
                const badgeEl = el.querySelector('.badge:not(.is-badge-empty), .dialog-subtitle-badge-unread');
                if (badgeEl) {
                    const txt = badgeEl.innerText.trim();
                    unread = parseInt(txt) || 0;
                }

                // 是否 pinned
                const isPinned = el.querySelector('.dialog-subtitle-badge-pinned') !== null;

                // 是否 muted
                const isMuted = el.classList.contains('is-muted');

                results.push({
                    index: idx,
                    title: title,
                    last_message: lastMsg,
                    unread_count: unread,
                    is_pinned: isPinned,
                    is_muted: isMuted,
                });
            });
            return results;
        }
    """)
    return chats or []


async def crawl_messages(skill: TelegramWebSkill, limit: int = 20) -> List[dict]:
    """爬取当前聊天的消息"""
    if not skill.page:
        return []

    messages = await skill.page.evaluate(f"""
        () => {{
            const results = [];
            // Telegram Web K 版消息气泡使用 .bubble 类
            const bubbles = document.querySelectorAll('.bubble');
            const msgs = Array.from(bubbles).slice(-{limit});
            msgs.forEach((el, idx) => {{
                // 跳过日期分隔线
                if (el.classList.contains('is-date')) {{
                    const dateText = el.innerText.trim();
                    results.push({{
                        index: idx,
                        sender: 'System',
                        text: `[日期: ${{dateText}}]`,
                        is_outgoing: false,
                        timestamp: dateText,
                        is_date: true,
                    }});
                    return;
                }}

                // 发送者名称
                let sender = '';
                const nameEl = el.querySelector('.name, .peer-title, .sender-name, .post-author');
                if (nameEl) sender = nameEl.innerText.trim();

                // 消息文本
                let text = '';
                // 优先查找 .bubble-content 或 .service-msg
                const textEl = el.querySelector('.bubble-content, .service-msg, .message-text');
                if (textEl) {{
                    text = textEl.innerText.trim();
                }} else {{
                    // 回退：克隆节点并移除时间/状态元素
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('.message-time, .time, .message-status, .post-author, .name').forEach(e => e.remove());
                    text = clone.innerText.trim();
                }}

                // 是否是自己发出的
                const isOutgoing = el.classList.contains('is-out') ||
                                   el.classList.contains('own') ||
                                   el.classList.contains('out');

                // 时间
                let timestamp = '';
                const timeEl = el.querySelector('.message-time, .time');
                if (timeEl) timestamp = timeEl.innerText.trim();

                // 媒体类型检测
                let media = '';
                if (el.querySelector('img, video')) media = 'media';
                if (el.querySelector('.audio')) media = 'audio';
                if (el.querySelector('.voice')) media = 'voice';

                results.push({{
                    index: idx,
                    sender: sender || (isOutgoing ? 'Me' : 'Unknown'),
                    text: text,
                    is_outgoing: isOutgoing,
                    timestamp: timestamp,
                    media: media,
                }});
            }});
            return results;
        }}
    """)
    return messages or []


async def main_loop():
    skill = TelegramWebSkill(headless=False)

    print("=" * 60)
    print(" Telegram Web 持续爬取循环")
    print("=" * 60)
    print(f"数据保存目录: {CRAWL_DIR}")
    print("按 Ctrl+C 停止")
    print()

    await skill.start()

    if not await skill.is_logged_in():
        print("❌ 未登录，无法爬取")
        await skill.stop()
        return 1

    print("✅ 已登录，开始爬取循环\n")

    iteration = 0
    previous_chats: Dict[str, dict] = {}

    try:
        while not _should_stop:
            iteration += 1
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            print(f"\n--- 第 {iteration} 轮爬取 [{ts}] ---")

            # 1. 爬取聊天列表
            chats = await crawl_chat_list(skill)
            print(f"📋 聊天列表: {len(chats)} 个")

            # 保存聊天列表
            _save_json({
                "timestamp": ts,
                "iteration": iteration,
                "chats": chats,
            }, f"chats_{ts}.json")

            # 2. 检测未读消息（过滤掉系统提示和归档）
            def _is_valid_chat(c: dict) -> bool:
                title = c.get("title", "")
                skip_keywords = ["archived", "never miss", "enable notifications", " Telegram"]
                return title and not any(kw.lower() in title.lower() for kw in skip_keywords)

            unread_chats = [c for c in chats if c.get("unread_count", 0) > 0 and _is_valid_chat(c)]
            if unread_chats:
                print(f"🔴 未读聊天: {len(unread_chats)} 个")
                for c in unread_chats:
                    print(f"   • {c.get('title', 'Unknown')}: {c.get('unread_count')} 未读")

                # 3. 进入第一个有效未读聊天，提取消息
                target = unread_chats[0]
                chat_title = target.get("title", "Unknown")

                print(f"\n📂 进入聊天: {chat_title}")

                # 使用 Playwright locator 点击（更可靠）
                success = False
                chat_idx = target.get("index", 0)
                try:
                    # 先尝试通过文本精确匹配
                    short_title = chat_title.split('\n')[0][:15]
                    locator = skill.page.locator('.chatlist-chat, .row-clickable').filter(has_text=short_title)
                    if await locator.count() > 0:
                        await locator.first.click()
                        success = True
                    else:
                        # 回退：通过索引点击
                        success = await skill.page.evaluate(f"""
                            () => {{
                                const items = document.querySelectorAll('.chatlist-chat, .row-clickable');
                                if (items[{chat_idx}]) {{
                                    items[{chat_idx}].click();
                                    return true;
                                }}
                                return false;
                            }}
                        """)
                except Exception as e:
                    print(f"⚠️  点击失败: {e}")
                    success = False

                if success:
                    await asyncio.sleep(2)  # 等待消息加载

                    msgs = await crawl_messages(skill, limit=20)
                    print(f"📝 提取到 {len(msgs)} 条消息")

                    # 打印最近 3 条
                    for m in msgs[-3:]:
                        sender = "📤 我" if m.get("is_outgoing") else "📨 对方"
                        text = m.get("text", "")[:50].replace("\n", " ")
                        print(f"   {sender} | {text}...")

                    # 保存消息
                    _save_json({
                        "timestamp": ts,
                        "iteration": iteration,
                        "chat_title": chat_title,
                        "chat_index": chat_idx,
                        "messages": msgs,
                    }, f"messages_{chat_title[:20]}_{ts}.json")
                else:
                    print("⚠️  无法点击进入聊天")

            else:
                print("✅ 没有新的未读消息")

            # 4. 截图（每 5 轮一次）
            if iteration % 5 == 0:
                shot_path = await skill.take_screenshot(str(CRAWL_DIR / f"screenshot_{ts}.png"))
                print(f"📸 截图已保存: {shot_path}")

            # 5. 保存会话状态（每 10 轮一次）
            if iteration % 10 == 0:
                await skill._save_state()
                print("💾 会话状态已保存")

            # 等待下一轮
            print("\n⏳ 等待 10 秒...")
            for _ in range(10):
                if _should_stop:
                    break
                await asyncio.sleep(1)

    except Exception as e:
        print(f"\n❌ 循环异常: {e}")
    finally:
        await skill.stop()
        print(f"\n✅ 爬取结束，共 {iteration} 轮")
        print(f"📁 数据保存在: {CRAWL_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_loop()))
