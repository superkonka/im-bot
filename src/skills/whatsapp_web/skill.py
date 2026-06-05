#!/usr/bin/env python3
"""
WhatsApp Web Skill - 核心实现

基于 Playwright 直接操作 WhatsApp Web DOM，使用独立浏览器实例。
支持扫码登录、状态持久化、消息收发、聊天列表获取、群链接加入。

与 WebBridge 方案的区别：
- 使用独立 Chromium 实例（非用户现有浏览器）
- Playwright 原生 API 可正确处理 React 合成事件
- 支持保存/恢复 storage_state 实现登录态持久化
- 支持有头模式扫码登录

用法:
    skill = WhatsAppWebSkill(headless=False)  # 首次登录用有头模式
    await skill.start()

    # 登录（首次）
    if not await skill.is_logged_in():
        print("请用手机 WhatsApp App 扫码登录")
        await skill.wait_for_login(timeout=120)

    # 获取聊天列表
    chats = await skill.get_chat_list()

    # 进入聊天并发送消息
    await skill.open_chat_by_title("小波")
    await skill.send_message("你好！")

    # 加入群聊
    await skill.join_group_link("https://chat.whatsapp.com/XXXX")

    await skill.stop()
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# 兼容独立运行
try:
    from config import DATA_DIR
except ImportError:
    import sys
    _project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(_project_root / "src"))
    from config import DATA_DIR

# 状态保存目录
STATE_DIR = DATA_DIR / "whatsapp_web_state"
STATE_DIR.mkdir(exist_ok=True)

DEFAULT_STATE_FILE = STATE_DIR / "whatsapp_web_state.json"


@dataclass
class ChatItem:
    """聊天列表项"""
    chat_id: str
    title: str
    last_message: str = ""
    unread_count: int = 0
    is_pinned: bool = False
    is_muted: bool = False
    timestamp: Optional[str] = None


@dataclass
class WebMessage:
    """Web 端消息"""
    message_id: str
    chat_id: str
    sender_name: str
    text: str
    is_outgoing: bool = False
    timestamp: Optional[str] = None
    raw_html: str = ""


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    error: Optional[str] = None


@dataclass
class JoinGroupResult:
    """加入群聊结果"""
    success: bool
    status: str = ""  # "joined", "pending_approval", "already_member", "failed"
    error: Optional[str] = None


class WhatsAppWebSkill:
    """
    WhatsApp Web Skill - 基于 Playwright DOM 操作

    用法:
        skill = WhatsAppWebSkill(headless=False)
        await skill.start()

        # 登录（首次）
        if not await skill.is_logged_in():
            print("请用手机 WhatsApp App 扫码登录")
            await skill.wait_for_login(timeout=120)

        # 获取聊天列表
        chats = await skill.get_chat_list()

        # 进入聊天并发送消息
        await skill.open_chat_by_title("小波")
        await skill.send_message("你好！")

        # 加入群聊
        result = await skill.join_group_link("https://chat.whatsapp.com/XXXX")

        await skill.stop()
    """

    URL = "https://web.whatsapp.com/"

    # ── DOM 选择器（基于实际测试，多版本兼容） ──
    SELECTORS = {
        # 登录相关
        "qr_code": [
            'canvas',
            '[data-testid="qr-code"]',
            '.qr-code',
        ],
        "loading_spinner": [
            '[data-testid="loading"]',
            '.progressbar',
            '.progress-spinner',
        ],
        # 主界面
        "chat_list": [
            '[data-testid="chat-list"]',
            '[data-testid="cell-frame-container"]',
            '.chat-list',
        ],
        "chat_item": [
            '[data-testid="list-item"]',  # 主要选择器（匹配 list-item-0, list-item-1 等）
            '[role="row"]',  # 备选
            '[data-testid="cell-frame-container"]',  # 旧版备选
        ],
        "chat_title": [
            '[data-testid="conversation-info-header"]',
            '.chat-title',
            '[title]',
            'span[dir="auto"]',
        ],
        "last_message": [
            '[data-testid="last-msg-status"]',
            '[data-testid="msg-meta"]',
            '.message-preview',
        ],
        "unread_badge": [
            '[data-testid="icon-unread-count"]',
            '.unread-count',
            '[aria-label*="unread"]',
        ],
        "message_bubble": [
            '[data-testid="msg-container"]',
            '.message-in',
            '.message-out',
        ],
        "message_text": [
            '[data-testid="msg-text"]',
            '.selectable-text',
        ],
        "message_sender": [
            '[data-testid="msg-meta"] .message-sender',
            '.message-sender',
        ],
        "message_time": [
            '[data-testid="msg-meta"]',
            '.message-time',
        ],
        "message_input": [
            '[data-testid="conversation-compose-box-input"]',
            'div[contenteditable="true"]',
        ],
        "send_button": [
            '[data-testid="send"]',
            '[data-icon="send"]',
        ],
        "search_input": [
            '[data-testid="chat-list-search-container"] input',
            '[placeholder*="Search"]',
            '[placeholder*="搜索"]',
        ],
        "conversation_header": [
            '[data-testid="conversation-header-title"]',
            '.chat-title',
        ],
        # 群链接相关
        "join_group_button": [
            'button:has-text("Join Group")',
            'button:has-text("加入群组")',
            'button:has-text("请求加入")',
            '[data-testid="join-group"]',
        ],
        "group_invite_title": [
            'h1',
            'h2',
            '.group-name',
            '[data-testid="group-info"]',
        ],
        "continue_to_web": [
            'a:has-text("继续前往")',
            'a:has-text("WhatsApp 网页版")',
        ],
    }

    def __init__(
        self,
        headless: bool = False,
    ):
        self.headless = headless
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._logged_in = False
        self._current_chat_id: Optional[str] = None
        self._handlers: List[Callable] = []

    # ────────────────────────────── 生命周期 ──────────────────────────────

    async def start(self) -> None:
        """启动浏览器并打开 WhatsApp Web"""
        self._playwright = await async_playwright().start()

        # 使用持久化上下文，所有数据（cookies + localStorage + IndexedDB）自动保存
        user_data_dir = STATE_DIR / "chromium_profile"
        user_data_dir.mkdir(exist_ok=True)

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        # 检查是否已有页面，没有则新建
        pages = self._context.pages
        if pages:
            self._page = pages[0]
            await self._page.goto(self.URL, wait_until="domcontentloaded")
        else:
            self._page = await self._context.new_page()
            await self._page.goto(self.URL, wait_until="domcontentloaded")

        # 等待加载完成（WhatsApp Web 二维码需要更长时间渲染）
        await asyncio.sleep(5)
        print(f"[WhatsAppWebSkill] 页面已打开: {self._page.url}")

    async def stop(self) -> None:
        """停止（持久化上下文自动保存所有数据）"""
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._context = None
        print("[WhatsAppWebSkill] 已停止（数据已持久化）")

    async def _save_state(self) -> None:
        """持久化上下文自动保存，此方法保留用于兼容性"""
        pass

    # ────────────────────────────── 登录流程 ──────────────────────────────

    async def is_logged_in(self, timeout_ms: int = 5000) -> bool:
        """检查是否已登录（聊天列表可见）"""
        if not self._page:
            return False

        try:
            # 方法 1: 检查聊天列表是否存在
            for selector in self.SELECTORS["chat_list"]:
                elem = await self._page.query_selector(selector)
                if elem and await elem.is_visible():
                    return True

            # 方法 2: 检查是否有聊天项
            for selector in self.SELECTORS["chat_item"]:
                elems = await self._page.query_selector_all(selector)
                if len(elems) > 0:
                    return True

            # 方法 3: 检查是否在二维码页面
            qr_visible = await self._is_any_visible(self.SELECTORS["qr_code"], 1000)
            if qr_visible:
                return False

            return False
        except Exception:
            return False

    async def wait_for_login(self, timeout: float = 120.0) -> bool:
        """
        等待扫码登录完成。

        流程:
            1. 检测当前是否在二维码页面
            2. 提示用户用手机 WhatsApp App 扫码
            3. 轮询检测登录是否成功

        参数:
            timeout: 扫码后等待登录完成的超时（秒）
        """
        if not self._page:
            raise RuntimeError("Skill 未启动，请先调用 start()")

        # 检查是否已经在主界面（已登录）
        if await self.is_logged_in(timeout_ms=3000):
            print("[WhatsApp Login] 已经是登录状态")
            self._logged_in = True
            await self._save_state()
            return True

        # 等待二维码渲染（可能需要额外时间）
        print("[WhatsApp Login] 等待二维码渲染...")
        await asyncio.sleep(3)

        # 检查是否有二维码
        qr_visible = await self._is_any_visible(self.SELECTORS["qr_code"], 5000)
        if not qr_visible:
            print("[WhatsApp Login] 未检测到二维码，可能页面结构不符或已登录")
            # 再次检查登录状态
            if await self.is_logged_in(timeout_ms=3000):
                print("[WhatsApp Login] 检测到已登录")
                self._logged_in = True
                await self._save_state()
                return True
            # 截图供调试
            debug_path = await self.take_screenshot(str(STATE_DIR / "login_debug.png"))
            print(f"[WhatsApp Login] 已保存调试截图: {debug_path}")
            return False

        print("\n" + "=" * 60)
        print("📱 请用手机 WhatsApp App 扫描二维码")
        print("   步骤:")
        print("   1. 打开手机 WhatsApp")
        print("   2. 点击设置 → 已关联设备 → 关联新设备")
        print("   3. 对准浏览器中的二维码扫描")
        print("=" * 60)

        if self.headless:
            print("\n⚠️  无头模式下无法显示二维码，建议改用有头模式")
            return False
        else:
            print(f"\n🖥️  二维码已显示在浏览器窗口中，请扫码")
            print(f"   (将在 {int(timeout)} 秒内自动检测登录状态)")

        # 给二维码页面一点稳定时间
        await asyncio.sleep(3)

        # 轮询检测登录成功
        print("[WhatsApp Login] 等待登录完成...")
        poll_start = time.time()
        while time.time() - poll_start < timeout:
            if await self.is_logged_in(timeout_ms=2000):
                print("[WhatsApp Login] ✅ 登录成功!")
                self._logged_in = True
                await self._save_state()
                return True
            await asyncio.sleep(2)

        print("[WhatsApp Login] ❌ 超时: 扫码后未完成登录")
        return False

    # ────────────────────────────── 聊天操作 ──────────────────────────────

    async def get_chat_list(self, limit: int = 50) -> List[ChatItem]:
        """获取聊天列表"""
        if not self._page:
            return []

        chats: List[ChatItem] = []
        seen_titles = set()

        for selector in self.SELECTORS["chat_item"]:
            elements = await self._page.query_selector_all(selector)
            if elements:
                for idx, elem in enumerate(elements):
                    if len(chats) >= limit:
                        break
                    try:
                        # 尝试获取标题
                        title = ""
                        for title_sel in self.SELECTORS["chat_title"]:
                            title_el = await elem.query_selector(title_sel)
                            if title_el:
                                title = await title_el.get_attribute("title") or await title_el.inner_text() or ""
                                title = title.strip()
                                if title:
                                    break

                        # 跳过系统通知和重复项
                        if not title or title in seen_titles or title == "WhatsApp" or "用投票" in title:
                            continue
                        seen_titles.add(title)

                        # 尝试获取最后消息
                        last_msg = ""
                        for msg_sel in self.SELECTORS["last_message"]:
                            msg_el = await elem.query_selector(msg_sel)
                            if msg_el:
                                last_msg = await msg_el.inner_text() or ""
                                last_msg = last_msg.strip()
                                if last_msg:
                                    break

                        # 未读数
                        unread = 0
                        for badge_sel in self.SELECTORS["unread_badge"]:
                            badge = await elem.query_selector(badge_sel)
                            if badge:
                                badge_text = await badge.inner_text()
                                try:
                                    unread = int(badge_text.strip())
                                except ValueError:
                                    pass
                                break

                        # 获取 chat_id（通过 data-testid 或索引）
                        chat_id = await elem.get_attribute("data-testid") or f"index_{idx}"

                        chats.append(ChatItem(
                            chat_id=chat_id,
                            title=title,
                            last_message=last_msg,
                            unread_count=unread,
                        ))
                    except Exception as exc:
                        print(f"[get_chat_list] 解析聊天项失败: {exc}")
                        continue

        return chats

    async def open_chat(self, chat_id: str) -> bool:
        """通过索引或 data-testid 打开指定聊天"""
        if not self._page:
            return False

        # 尝试通过 data-testid 点击
        try:
            if chat_id.startswith("list-item-"):
                elem = await self._page.query_selector(f'[data-testid="{chat_id}"]')
                if elem:
                    await elem.click()
                    self._current_chat_id = chat_id
                    await asyncio.sleep(2)
                    return True
        except Exception:
            pass

        # 回退：按索引点击
        try:
            if chat_id.startswith("index_"):
                idx = int(chat_id.split("_")[1])
                for selector in self.SELECTORS["chat_item"]:
                    elements = await self._page.query_selector_all(selector)
                    if idx < len(elements):
                        await elements[idx].click()
                        self._current_chat_id = chat_id
                        await asyncio.sleep(2)
                        return True
        except (ValueError, IndexError):
            pass

        return False

    async def open_chat_by_title(self, title_query: str) -> bool:
        """通过标题模糊匹配打开聊天"""
        if not self._page:
            return False

        chats = await self.get_chat_list(limit=50)
        for chat in chats:
            if title_query.lower() in chat.title.lower() or chat.title.lower() in title_query.lower():
                return await self.open_chat(chat.chat_id)

        # 如果没找到，尝试搜索
        search_results = await self.search_chat(title_query)
        if search_results:
            return await self.open_chat(search_results[0].chat_id)

        return False

    async def get_messages(self, limit: int = 20) -> List[WebMessage]:
        """获取当前聊天窗口的消息"""
        if not self._page:
            return []

        messages: List[WebMessage] = []

        for selector in self.SELECTORS["message_bubble"]:
            elements = await self._page.query_selector_all(selector)
            if elements:
                # 取最后 N 条
                for elem in elements[-limit:]:
                    try:
                        # 发送者
                        sender = ""
                        for sender_sel in self.SELECTORS["message_sender"]:
                            sender_el = await elem.query_selector(sender_sel)
                            if sender_el:
                                sender = await sender_el.inner_text() or ""
                                sender = sender.strip()
                                if sender:
                                    break

                        # 消息文本
                        text = ""
                        for text_sel in self.SELECTORS["message_text"]:
                            text_el = await elem.query_selector(text_sel)
                            if text_el:
                                text = await text_el.inner_text() or ""
                                text = text.strip()
                                if text:
                                    break

                        # 如果是 outgoing 消息
                        is_outgoing = False
                        class_attr = await elem.get_attribute("class") or ""
                        if "message-out" in class_attr:
                            is_outgoing = True
                        data_testid = await elem.get_attribute("data-testid") or ""
                        if "out" in data_testid:
                            is_outgoing = True

                        # 消息 ID
                        msg_id = await elem.get_attribute("data-id") or ""

                        # 时间
                        time_str = ""
                        for time_sel in self.SELECTORS["message_time"]:
                            time_el = await elem.query_selector(time_sel)
                            if time_el:
                                time_str = await time_el.inner_text() or ""
                                time_str = time_str.strip()
                                if time_str:
                                    break

                        messages.append(WebMessage(
                            message_id=msg_id,
                            chat_id=self._current_chat_id or "",
                            sender_name=sender or ("Me" if is_outgoing else "Unknown"),
                            text=text,
                            is_outgoing=is_outgoing,
                            timestamp=time_str,
                        ))
                    except Exception as exc:
                        print(f"[get_messages] 解析消息失败: {exc}")
                        continue

                break

        return messages

    async def send_message(self, text: str) -> SendResult:
        """在当前聊天窗口发送消息"""
        if not self._page:
            return SendResult(success=False, error="Skill 未启动")

        if not self._current_chat_id:
            return SendResult(success=False, error="未打开聊天，请先调用 open_chat()")

        try:
            # 找到输入框
            input_elem = await self._find_first_visible(self.SELECTORS["message_input"])
            if not input_elem:
                return SendResult(success=False, error="未找到消息输入框")

            await input_elem.click()
            await asyncio.sleep(0.3)

            # 输入文本
            await input_elem.fill(text)
            await asyncio.sleep(0.5)

            # 点击发送按钮或按回车
            send_btn = await self._find_first_visible(self.SELECTORS["send_button"])
            if send_btn:
                await send_btn.click()
            else:
                await self._page.keyboard.press("Enter")

            await asyncio.sleep(1)
            return SendResult(success=True)

        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    async def send_message_to_chat(self, chat_id: str, text: str) -> SendResult:
        """打开聊天并发送消息（快捷方法）"""
        if not await self.open_chat(chat_id):
            return SendResult(success=False, error=f"无法打开聊天: {chat_id}")
        return await self.send_message(text)

    # ────────────────────────────── 搜索 ──────────────────────────────

    async def search_chat(self, query: str) -> List[ChatItem]:
        """
        在 WhatsApp Web 中搜索聊天或联系人。

        流程:
            1. 点击搜索框
            2. 输入查询关键词
            3. 等待搜索结果
            4. 提取结果列表

        参数:
            query: 搜索关键词（聊天标题、联系人名等）

        返回:
            匹配的聊天列表（最多 10 个）
        """
        if not self._page:
            return []

        # 步骤 1: 点击搜索框
        search_input = await self._find_first_visible(self.SELECTORS["search_input"])
        if not search_input:
            print("[search_chat] 未找到搜索框")
            return []

        await search_input.click()
        await asyncio.sleep(0.5)

        # 步骤 2: 输入关键词
        await search_input.fill(query)
        await asyncio.sleep(1.5)  # 等待搜索完成

        # 步骤 3: 提取搜索结果
        results: List[ChatItem] = []
        result_selectors = [
            '[data-testid="cell-frame-container"]',
            '[data-testid="list-item"]',
            '[role="row"]',
        ]

        for selector in result_selectors:
            elements = await self._page.query_selector_all(selector)
            if elements:
                for idx, elem in enumerate(elements[:10]):
                    try:
                        title = ""
                        for title_sel in self.SELECTORS["chat_title"]:
                            title_el = await elem.query_selector(title_sel)
                            if title_el:
                                title = (await title_el.get_attribute("title") or await title_el.inner_text() or "").strip()
                                if title:
                                    break

                        subtitle = ""
                        for sub_sel in self.SELECTORS["last_message"]:
                            sub_el = await elem.query_selector(sub_sel)
                            if sub_el:
                                subtitle = (await sub_el.inner_text() or "").strip()
                                if subtitle:
                                    break

                        chat_id = await elem.get_attribute("data-testid") or f"search_{idx}"

                        results.append(ChatItem(
                            chat_id=chat_id,
                            title=title or f"Result {idx}",
                            last_message=subtitle,
                        ))
                    except Exception:
                        continue
                break

        # 清除搜索框（按 Escape）
        await self._page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

        return results

    # ────────────────────────────── 群链接操作 ──────────────────────────────

    async def join_group_link(self, group_link: str, timeout: float = 30.0) -> JoinGroupResult:
        """
        通过群链接加入 WhatsApp 群组。

        流程:
            1. 导航到群链接页面
            2. 点击"继续前往 WhatsApp 网页版"
            3. 在 WhatsApp Web 中处理加入请求
            4. 等待加入完成或管理员批准

        参数:
            group_link: 群链接，如 "https://chat.whatsapp.com/XXXX"
            timeout: 等待加入完成的超时（秒）

        返回:
            JoinGroupResult 对象
        """
        if not self._page:
            return JoinGroupResult(success=False, error="Skill 未启动")

        # 确保已登录
        if not await self.is_logged_in():
            return JoinGroupResult(success=False, error="未登录，请先完成登录")

        try:
            # 步骤 1: 导航到群链接
            print(f"[join_group_link] 导航到: {group_link}")
            await self._page.goto(group_link, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # 步骤 2: 检查页面内容并点击"继续前往"
            body_text = await self._page.evaluate("() => document.body.innerText")
            current_url = await self._page.evaluate("() => window.location.href")
            print(f"[join_group_link] 当前页面: {current_url}")
            print(f"[join_group_link] 页面内容: {body_text[:100]}")

            if "群聊邀请" in body_text or "Group invite" in body_text or "继续前往" in body_text:
                print("[join_group_link] 检测到群邀请页面")

                # 直接导航到 accept URL（比点击链接更可靠）
                accept_url = None
                links = await self._page.query_selector_all('a')
                for link in links:
                    href = await link.get_attribute('href')
                    if href and 'accept?code=' in href:
                        accept_url = href
                        break
                
                if accept_url:
                    print(f"[join_group_link] 直接导航到: {accept_url}")
                    await self._page.goto(accept_url, wait_until="domcontentloaded")
                    await asyncio.sleep(5)
                    clicked = True
                else:
                    return JoinGroupResult(success=False, error="未找到 accept URL")

            # 步骤 3: 检查跳转后的页面状态
            current_url = await self._page.evaluate("() => window.location.href")
            body_text = await self._page.evaluate("() => document.body.innerText")
            print(f"[join_group_link] 跳转后页面: {current_url}")
            print(f"[join_group_link] 跳转后内容: {body_text[:150]}")

            # 检查是否需要加入
            if "请求加入" in body_text or "Join Group" in body_text or "Request to join" in body_text or "加入群组" in body_text:
                print("[join_group_link] 需要请求加入")

                # 点击加入按钮
                for selector in self.SELECTORS["join_group_button"]:
                    try:
                        btn = await self._page.wait_for_selector(selector, timeout=5000)
                        if btn:
                            await btn.click()
                            print("[join_group_link] 已点击加入按钮")
                            await asyncio.sleep(3)

                            # 检查是否需要管理员批准
                            body_text = await self._page.evaluate("() => document.body.innerText")
                            if "管理员" in body_text or "admin" in body_text.lower() or "pending" in body_text.lower() or "等待" in body_text:
                                return JoinGroupResult(
                                    success=True,
                                    status="pending_approval",
                                    error="已发送加入请求，等待管理员批准"
                                )

                            # 检查是否已成功加入
                            if await self.is_logged_in():
                                chats = await self.get_chat_list(limit=50)
                                # 群聊列表中出现新群，说明已成功加入
                                return JoinGroupResult(success=True, status="joined")

                            return JoinGroupResult(success=True, status="joined")
                    except Exception:
                        continue

                return JoinGroupResult(success=False, error="未找到加入按钮")

            # 检查是否已经是成员
            if "你已加入" in body_text or "You are already" in body_text or "already a member" in body_text.lower():
                return JoinGroupResult(success=True, status="already_member")

            # 检查群是否已满或链接失效
            if "已满" in body_text or "full" in body_text.lower() or "group is full" in body_text.lower():
                return JoinGroupResult(success=False, error="群组已满")
            if "失效" in body_text or "invalid" in body_text.lower() or "expired" in body_text.lower() or "revoked" in body_text.lower():
                return JoinGroupResult(success=False, error="链接已失效")

            # 如果页面显示聊天列表，可能已经加入成功
            if await self.is_logged_in():
                return JoinGroupResult(success=True, status="joined")

            return JoinGroupResult(success=False, error=f"未知页面状态: {body_text[:150]}")

        except Exception as exc:
            return JoinGroupResult(success=False, error=str(exc))

    # ────────────────────────────── 事件监听（轮询模式） ──────────────────────────────

    async def poll_new_messages(
        self,
        interval: float = 3.0,
        chat_filter: Optional[List[str]] = None,
    ) -> None:
        """
        轮询新消息（简单实现，后续可替换为 WebSocket 监听）。

        参数:
            interval: 轮询间隔（秒）
            chat_filter: 只监听指定 chat_id 列表，None 表示监听所有
        """
        if not self._page:
            return

        print(f"[poll_new_messages] 开始轮询，间隔 {interval}s...")
        last_counts: Dict[str, int] = {}

        try:
            while True:
                chats = await self.get_chat_list()
                for chat in chats:
                    if chat_filter and chat.chat_id not in chat_filter:
                        continue

                    prev = last_counts.get(chat.chat_id, 0)
                    if chat.unread_count > prev:
                        # 有未读消息
                        print(f"[poll] 新消息: [{chat.title}] {chat.unread_count - prev} 条")
                        if await self.open_chat(chat_id=chat.chat_id):
                            msgs = await self.get_messages(limit=chat.unread_count)
                            for msg in msgs:
                                if not msg.is_outgoing:
                                    print(f"  📨 {msg.sender_name}: {msg.text[:50]}")

                    last_counts[chat.chat_id] = chat.unread_count

                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            print("[poll_new_messages] 轮询已停止")

    # ────────────────────────────── 工具方法 ──────────────────────────────

    async def _is_any_visible(self, selectors: List[str], timeout_ms: int = 1000) -> bool:
        """任一选择器匹配的元素可见"""
        if not self._page:
            return False
        for selector in selectors:
            try:
                elem = await self._page.wait_for_selector(
                    selector, timeout=timeout_ms, state="visible"
                )
                if elem:
                    return True
            except Exception:
                continue
        return False

    async def _find_first_visible(self, selectors: List[str]):
        """找到第一个可见的匹配元素"""
        if not self._page:
            return None
        for selector in selectors:
            try:
                elem = await self._page.query_selector(selector)
                if elem and await elem.is_visible():
                    return elem
            except Exception:
                continue
        return None

    async def take_screenshot(self, path: Optional[str] = None) -> str:
        """截图（调试用）"""
        if not self._page:
            return ""
        path = path or str(STATE_DIR / "screenshot.png")
        await self._page.screenshot(path=path)
        return path

    @property
    def page(self) -> Optional[Page]:
        """暴露原始 Page 对象（高级用法）"""
        return self._page


# ── 启动入口（测试用） ──
async def main():
    """WhatsApp Web Skill 测试入口"""
    skill = WhatsAppWebSkill(headless=False)
    await skill.start()

    # 检查登录状态
    if not await skill.is_logged_in():
        print("请用手机 WhatsApp App 扫码登录...")
        logged_in = await skill.wait_for_login(timeout=120)
        if not logged_in:
            print("登录超时")
            await skill.stop()
            return

    # 获取聊天列表
    chats = await skill.get_chat_list()
    print(f"\n共 {len(chats)} 个聊天:")
    for c in chats:
        unread = f" 🔴 {c.unread_count} 未读" if c.unread_count > 0 else ""
        print(f"  • {c.title}{unread}")
        print(f"    └─ {c.last_message}")

    # 测试加入群聊（可选）
    # result = await skill.join_group_link("https://chat.whatsapp.com/IQIaQjDG7EgEsJaG2jWv5C")
    # print(f"\n加入群聊结果: {result}")

    await skill.stop()


if __name__ == "__main__":
    asyncio.run(main())
