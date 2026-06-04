#!/usr/bin/env python3
"""
Telegram Session 管理器

负责 Telethon 客户端的生命周期、Session 持久化、首次登录交互。
Session 文件保存在 data/telegram_sessions/ 目录下。
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable, Optional

from telethon import TelegramClient
from telethon.sessions import StringSession

try:
    from config import DATA_DIR
except ImportError:
    import sys
    from pathlib import Path
    # 独立运行时回退到项目根目录
    _project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(_project_root / "src"))
    from config import DATA_DIR

# Session 文件存放目录
SESSION_DIR = DATA_DIR / "telegram_sessions"
SESSION_DIR.mkdir(exist_ok=True)


class SessionManager:
    """
    管理 Telethon 客户端连接和登录状态。

    用法:
        mgr = SessionManager("my_account")
        client = await mgr.connect(api_id=12345, api_hash="xxx")
        # 使用 client...
        await mgr.disconnect()
    """

    def __init__(self, session_name: str = "default"):
        self.session_name = session_name
        self.session_path = SESSION_DIR / f"{session_name}.session"
        self.client: Optional[TelegramClient] = None
        self._connected = False

    # ────────────────────────────── 连接管理 ──────────────────────────────

    async def connect(
        self,
        api_id: int,
        api_hash: str,
        phone: Optional[str] = None,
        code_callback: Optional[Callable[[], str]] = None,
        password_callback: Optional[Callable[[], str]] = None,
        proxy: Optional[tuple] = None,
        timeout: float = 60.0,
    ) -> TelegramClient:
        """
        连接到 Telegram，必要时引导登录。

        参数:
            api_id: 从 https://my.telegram.org/apps 获取
            api_hash: 同上
            phone: 手机号，如 "+8613800138000"
            code_callback: 验证码回调函数，返回用户输入的验证码字符串
            password_callback: 两步密码回调函数（如有）
            proxy: 代理，格式 ("socks5", "host", port) 或 ("http", "host", port)
            timeout: 登录交互超时

        返回:
            已连接且已授权的 TelegramClient 实例
        """
        if self._connected and self.client:
            return self.client

        self.client = TelegramClient(
            str(self.session_path),
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy,
        )

        await self.client.connect()

        if not await self.client.is_user_authorized():
            if not phone:
                raise RuntimeError(
                    "Session 未授权且未提供手机号。"
                    "请提供 phone 参数进行首次登录。"
                )

            # 发送验证码
            await self.client.send_code_request(phone)
            print(f"[SessionManager] 验证码已发送至 {phone}")

            if not code_callback:
                raise RuntimeError("需要提供 code_callback 来处理验证码输入")

            # 等待验证码（带超时）
            code = await asyncio.wait_for(
                asyncio.to_thread(code_callback),
                timeout=timeout,
            )

            try:
                await self.client.sign_in(phone, code)
            except Exception as exc:
                # 可能是两步验证
                if "password" in str(exc).lower() or "2fa" in str(exc).lower():
                    if not password_callback:
                        raise RuntimeError("账号启用了两步验证，需要提供 password_callback")
                    password = await asyncio.wait_for(
                        asyncio.to_thread(password_callback),
                        timeout=timeout,
                    )
                    await self.client.sign_in(password=password)
                else:
                    raise

        self._connected = True
        me = await self.client.get_me()
        print(f"[SessionManager] 已连接: {me.first_name} (@{me.username or 'N/A'})")
        return self.client

    async def disconnect(self) -> None:
        """安全断开连接"""
        if self.client:
            await self.client.disconnect()
            self.client = None
        self._connected = False
        print("[SessionManager] 已断开")

    async def __aenter__(self) -> SessionManager:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    # ────────────────────────────── 便捷方法 ──────────────────────────────

    def is_connected(self) -> bool:
        return self._connected and self.client is not None

    def get_session_file_path(self) -> Path:
        return self.session_path

    def get_string_session(self) -> Optional[str]:
        """
        导出 StringSession（便于部署到其他机器）。
        需要在已连接状态下调用。
        """
        if not self.client or not self._connected:
            return None
        return StringSession.save(self.client.session)

    @classmethod
    def from_string_session(
        cls,
        session_string: str,
        api_id: int,
        api_hash: str,
        proxy: Optional[tuple] = None,
    ) -> TelegramClient:
        """
        从 StringSession 快速创建客户端（无需本地 session 文件）。
        """
        client = TelegramClient(
            StringSession(session_string),
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy,
        )
        return client
