#!/usr/bin/env python3
"""
Telegram Web Skill - 核心实现

基于 Playwright 直接操作 Telegram Web DOM，无需 Vision Agent。
支持登录状态持久化、消息收发、聊天列表获取。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
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
STATE_DIR = DATA_DIR / "telegram_web_state"
STATE_DIR.mkdir(exist_ok=True)

DEFAULT_STATE_FILE = STATE_DIR / "telegram_web_state.json"


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


class TelegramWebSkill:
    """
    Telegram Web Skill - 基于 Playwright DOM 操作

    用法:
        skill = TelegramWebSkill()
        await skill.start()

        # 登录（首次）
        if not await skill.is_logged_in():
            await skill.login("+8613580541293", code_callback=lambda: input("验证码: "))

        # 获取聊天列表
        chats = await skill.get_chat_list()

        # 进入聊天并发送消息
        await skill.open_chat(chat_id)
        await skill.send_message("你好！")

        await skill.stop()
    """

    URL = "https://web.telegram.org/k/"

    # ── DOM 选择器（多版本兼容） ──
    SELECTORS = {
        # 登录相关
        "phone_input": [
            'input[type="tel"]',
            'input[name="phone"]',
            '.input-field-phone input',
        ],
        "next_button": [
            'button:has-text("Next")',
            'button:has-text("NEXT")',
            'button:has-text("下一步")',
            'button[type="submit"]',
            '.btn-primary',
        ],
        "code_input": [
            'input[type="text"]',
            'input[inputmode="numeric"]',
            '.input-field-code input',
        ],
        "confirm_code_button": [
            'button:has-text("Next")',
            'button:has-text("Confirm")',
            'button[type="submit"]',
        ],
        # 二维码登录
        "qr_code_tab": [
            'button:has-text("QR CODE")',
            'button:has-text("QR Code")',
            'button:has-text("qr code")',
            'a:has-text("QR")',
            '[class*="qr"]',
        ],
        "qr_code_image": [
            'canvas',
        ],
        "qr_code_container": [
            'canvas',
            '[class*="auth-form"]',
            '[class*="qr"]',
        ],
        # 主界面 (Telegram Web K 版实际 DOM)
        "chat_list_container": [
            '.chatlist-container',
            '.sidebar-left',
            '.sidebar-content',
            '[class*="chatlist-container"]',
        ],
        "chat_item": [
            '.chatlist-chat',
            '[class*="chatlist-chat"]',
            '.row-clickable',
            '.dialog',
        ],
        "unread_badge": [
            '.badge',
            '[class*="dialog-subtitle-badge"]',
            '[class*="badge"]',
        ],
        "message_bubble": [
            '.bubble',
            '.bubble-content-wrapper',
            '[class*="bubble"]',
        ],
        "message_input": [
            '#editable-message-text',
            'div[contenteditable="true"]',
            '.composer-input',
            '[class*="input-message-input"]',
        ],
        "send_button": [
            '.btn-send',
            '.btn-icon.send',
            'button[aria-label*="Send"]',
        ],
        "loading_spinner": [
            '.progress-spinner',
            '[class*="spinner"]',
            '.progress',
        ],
        "login_phone_page": [
            'input[type="tel"]',
            '.login-header',
        ],
        "login_code_page": [
            'input[inputmode="numeric"]',
            '.login-header:has-text("code")',
        ],
    }

    def __init__(
        self,
        state_file: Optional[Path] = None,
        headless: bool = False,
    ):
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._logged_in = False
        self._current_chat_id: Optional[str] = None
        self._handlers: List[Callable] = []

    # ────────────────────────────── 生命周期 ──────────────────────────────

    async def start(self) -> None:
        """启动浏览器并打开 Telegram Web"""
        self._playwright = await async_playwright().start()

        # 如果有保存的状态，先加载
        storage_state = None
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    storage_state = json.load(f)
                print(f"[TelegramWebSkill] 已加载状态: {self.state_file}")
            except Exception as exc:
                print(f"[TelegramWebSkill] 加载状态失败: {exc}")

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            storage_state=storage_state,
        )

        self._page = await self._context.new_page()
        await self._page.goto(self.URL, wait_until="domcontentloaded")

        # 等待加载完成
        await asyncio.sleep(3)
        print(f"[TelegramWebSkill] 页面已打开: {self._page.url}")

    async def stop(self) -> None:
        """停止并保存状态"""
        await self._save_state()

        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        print("[TelegramWebSkill] 已停止")

    async def _save_state(self) -> None:
        """保存浏览器状态（cookies + localStorage）"""
        if not self._context:
            return
        try:
            state = await self._context.storage_state()
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"[TelegramWebSkill] 状态已保存: {self.state_file}")
        except Exception as exc:
            print(f"[TelegramWebSkill] 保存状态失败: {exc}")

    # ────────────────────────────── 登录流程 ──────────────────────────────

    async def is_logged_in(self, timeout_ms: int = 5000) -> bool:
        """检查是否已登录（主界面可见）"""
        if not self._page:
            return False

        try:
            # 方法 1: 检查 body class (已登录时通常有 is-left-column-shown)
            body = await self._page.query_selector("body")
            if body:
                body_class = await body.get_attribute("class") or ""
                if "is-left-column-shown" in body_class:
                    return True

            # 方法 2: 检查左侧聊天列表是否存在且可见
            for selector in self.SELECTORS["chat_list_container"]:
                elem = await self._page.query_selector(selector)
                if elem and await elem.is_visible():
                    return True

            # 方法 3: 检查是否在登录页
            phone_visible = await self._is_any_visible(self.SELECTORS["phone_input"], 1000)
            if phone_visible:
                return False

            code_visible = await self._is_any_visible(self.SELECTORS["code_input"], 1000)
            if code_visible:
                return False

            return False
        except Exception:
            return False

    async def login(
        self,
        phone: str,
        code_callback: Optional[Callable[[], str]] = None,
        password_callback: Optional[Callable[[], str]] = None,
        timeout: float = 120.0,
    ) -> bool:
        """
        执行登录流程。

        参数:
            phone: 手机号，如 "+8613580541293"
            code_callback: 验证码回调，返回 5 位数字字符串
            password_callback: 两步验证密码回调（如有）
            timeout: 总超时（秒）
        """
        if not self._page:
            raise RuntimeError("Skill 未启动，请先调用 start()")

        start_time = time.time()

        # 步骤 1: 输入手机号
        print(f"[Login] 正在输入手机号: {phone}")
        phone_input = await self._find_first_visible(self.SELECTORS["phone_input"])
        if not phone_input:
            print("[Login] 未找到手机号输入框，可能已登录或页面未加载")
            return await self.is_logged_in()

        await phone_input.click()
        await phone_input.fill(phone)
        await asyncio.sleep(0.5)

        # 点击下一步
        next_btn = await self._find_first_visible(self.SELECTORS["next_button"])
        if next_btn:
            await next_btn.click()
            print("[Login] 已点击 Next，等待验证码页面...")
        else:
            # 尝试按回车
            await self._page.keyboard.press("Enter")
            print("[Login] 已按回车，等待验证码页面...")

        await asyncio.sleep(2)

        # 步骤 2: 等待验证码输入框出现
        print("[Login] 等待验证码输入框...")
        while time.time() - start_time < timeout:
            code_input = await self._find_first_visible(self.SELECTORS["code_input"])
            if code_input:
                break
            await asyncio.sleep(1)
        else:
            print("[Login] 超时: 未出现验证码输入框")
            return False

        # 步骤 3: 获取验证码
        if not code_callback:
            raise RuntimeError("需要提供 code_callback 来处理验证码")

        # 提示用户
        print("\n" + "=" * 50)
        print("📱 请在已登录的 Telegram 设备上查看验证码")
        print("   或等待短信验证码")
        print("=" * 50)

        code = await asyncio.to_thread(code_callback)
        code = code.strip()
        print(f"[Login] 收到验证码: {code}")

        # 步骤 4: 输入验证码
        await code_input.fill(code)
        await asyncio.sleep(0.5)

        # 点击确认
        confirm_btn = await self._find_first_visible(self.SELECTORS["confirm_code_button"])
        if confirm_btn:
            await confirm_btn.click()
        else:
            await self._page.keyboard.press("Enter")

        print("[Login] 已提交验证码，等待登录完成...")

        # 步骤 5: 等待登录完成（主界面出现）
        while time.time() - start_time < timeout:
            if await self.is_logged_in(timeout_ms=2000):
                print("[Login] ✅ 登录成功!")
                self._logged_in = True
                await self._save_state()
                return True

            # 检查是否需要两步验证密码
            password_input = await self._page.query_selector('input[type="password"]')
            if password_input and await password_input.is_visible():
                print("[Login] 检测到两步验证")
                if not password_callback:
                    raise RuntimeError("需要提供 password_callback 来处理两步验证")
                password = await asyncio.to_thread(password_callback)
                await password_input.fill(password.strip())
                await self._page.keyboard.press("Enter")
                await asyncio.sleep(2)

            await asyncio.sleep(1)

        print("[Login] ❌ 超时: 登录未完成")
        return False

    async def login_by_qr_code(
        self,
        timeout: float = 120.0,
        qr_wait_prompt: bool = True,
    ) -> bool:
        """
        通过二维码扫码登录（有头浏览器模式下推荐）。

        流程:
            1. 检测当前是否在登录页
            2. 点击 "QR CODE" 切换到二维码登录
            3. 等待二维码渲染完成
            4. 提示用户用手机 Telegram App 扫码
            5. 轮询检测登录是否成功

        参数:
            timeout: 扫码后等待登录完成的超时（秒）
            qr_wait_prompt: 是否在终端打印提示信息
        """
        if not self._page:
            raise RuntimeError("Skill 未启动，请先调用 start()")

        # 检查是否已经在主界面（已登录）
        if await self.is_logged_in(timeout_ms=3000):
            print("[QR Login] ✅ 已经是登录状态")
            self._logged_in = True
            return True

        start_time = time.time()

        # 步骤 1: 如果当前是手机号输入页，先切换到 QR Code
        phone_input = await self._find_first_visible(self.SELECTORS["phone_input"])
        if phone_input:
            print("[QR Login] 当前是手机号登录页，尝试切换到 QR Code...")
            qr_tab = await self._find_first_visible(self.SELECTORS["qr_code_tab"])
            if qr_tab:
                await qr_tab.click()
                print("[QR Login] 已点击 QR CODE 标签")
                await asyncio.sleep(2)
            else:
                print("[QR Login] ⚠️ 未找到 QR CODE 切换按钮，可能页面已直接显示二维码")
        else:
            print("[QR Login] 未在手机号登录页，检查是否已有二维码显示...")

        # 步骤 2: 等待二维码渲染
        print("[QR Login] 等待二维码渲染...")
        qr_visible = False
        while time.time() - start_time < 15:  # 二维码渲染通常很快
            # 直接检测页面是否有可见的 canvas（Telegram Web K 版用 canvas 绘制二维码）
            try:
                canvases = await self._page.query_selector_all("canvas")
                for c in canvases:
                    if await c.is_visible():
                        # 进一步检查 canvas 尺寸（二维码 canvas 通常大于 100x100）
                        box = await c.bounding_box()
                        if box and box["width"] > 100 and box["height"] > 100:
                            qr_visible = True
                            break
                if qr_visible:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if not qr_visible:
            print("[QR Login] ❌ 未检测到二维码，可能页面结构不符")
            # 截图供调试
            debug_path = await self.take_screenshot(str(STATE_DIR / "qr_debug.png"))
            print(f"[QR Login] 已保存调试截图: {debug_path}")
            return False

        # 步骤 3: 提示用户扫码
        if qr_wait_prompt:
            print("\n" + "=" * 60)
            print("📱 请用手机 Telegram App 扫描二维码")
            print("   步骤:")
            print("   1. 打开手机 Telegram")
            print("   2. 点击设置 → 设备 → 链接桌面设备")
            print("   3. 对准浏览器中的二维码扫描")
            print("=" * 60)

            if self.headless:
                print("\n⚠️  无头模式下无法显示二维码，建议改用有头模式")
                return False
            else:
                print("\n🖥️  二维码已显示在浏览器窗口中，请扫码")
                print("   (将在 {timeout} 秒内自动检测登录状态)".format(timeout=int(timeout)))

        # 给二维码页面一点稳定时间
        await asyncio.sleep(3)

        # 步骤 4: 轮询检测登录成功
        print("[QR Login] 等待登录完成...")
        poll_start = time.time()
        while time.time() - poll_start < timeout:
            if await self.is_logged_in(timeout_ms=2000):
                print("[QR Login] ✅ 登录成功!")
                self._logged_in = True
                await self._save_state()
                return True
            await asyncio.sleep(2)

        print("[QR Login] ❌ 超时: 扫码后未完成登录")
        return False

    # ────────────────────────────── 聊天操作 ──────────────────────────────

    async def get_chat_list(self, limit: int = 50) -> List[ChatItem]:
        """获取聊天列表"""
        if not self._page:
            return []

        chats: List[ChatItem] = []

        for selector in self.SELECTORS["chat_item"]:
            elements = await self._page.query_selector_all(selector)
            if elements:
                for idx, elem in enumerate(elements[:limit]):
                    try:
                        # 尝试获取标题
                        title = ""
                        for title_sel in ['.chat-title', '.title', '[class*="title"]']:
                            title_el = await elem.query_selector(title_sel)
                            if title_el:
                                title = await title_el.inner_text() or ""
                                title = title.strip()
                                if title:
                                    break

                        # 尝试获取最后消息
                        last_msg = ""
                        for msg_sel in ['.chat-subtitle', '.last-message', '[class*="subtitle"]']:
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

                        # 获取 chat_id（通过 data 属性或索引）
                        chat_id = await elem.get_attribute("data-peer-id") or f"index_{idx}"

                        chats.append(ChatItem(
                            chat_id=chat_id,
                            title=title or f"Chat {idx}",
                            last_message=last_msg,
                            unread_count=unread,
                        ))
                    except Exception as exc:
                        print(f"[get_chat_list] 解析聊天项失败: {exc}")
                        continue

                break  # 找到匹配的选择器就停止

        return chats

    async def open_chat(self, chat_id: str) -> bool:
        """打开指定聊天"""
        if not self._page:
            return False

        # 尝试通过 data-peer-id 点击
        chat_elem = await self._page.query_selector(f'[data-peer-id="{chat_id}"]')
        if chat_elem:
            await chat_elem.click()
            self._current_chat_id = chat_id
            await asyncio.sleep(1.5)
            return True

        # 回退：按索引点击
        try:
            if chat_id.startswith("index_"):
                idx = int(chat_id.split("_")[1])
                for selector in self.SELECTORS["chat_item"]:
                    elements = await self._page.query_selector_all(selector)
                    if idx < len(elements):
                        await elements[idx].click()
                        self._current_chat_id = chat_id
                        await asyncio.sleep(1.5)
                        return True
        except (ValueError, IndexError):
            pass

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
                        for sender_sel in ['.name', '.sender-name', '[class*="name"]']:
                            sender_el = await elem.query_selector(sender_sel)
                            if sender_el:
                                sender = await sender_el.inner_text() or ""
                                sender = sender.strip()
                                if sender:
                                    break

                        # 消息文本
                        text = ""
                        for text_sel in ['.message-text', '.text', '[class*="text"]']:
                            text_el = await elem.query_selector(text_sel)
                            if text_el:
                                text = await text_el.inner_text() or ""
                                text = text.strip()
                                if text:
                                    break

                        # 如果是 outgoing 消息
                        is_outgoing = False
                        outgoing_sel = await elem.query_selector('[class*="outgoing"], [class*="is-out"], .out')
                        if outgoing_sel:
                            is_outgoing = True

                        # 消息 ID
                        msg_id = await elem.get_attribute("data-mid") or ""

                        messages.append(WebMessage(
                            message_id=msg_id,
                            chat_id=self._current_chat_id or "",
                            sender_name=sender or "Unknown",
                            text=text,
                            is_outgoing=is_outgoing,
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
