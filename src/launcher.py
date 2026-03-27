#!/usr/bin/env python3
"""
统一启动入口
"""
from typing import Optional

from .config import get_app_config, validate_config, validate_telegram_user_config
from .im_bot import IMBot
from .free_web_bot import FreeWebBot
from .telegram_userbot import TelegramUserBot, validate_telegram_user_settings


def resolve_telegram_transport(requested_transport: str = "auto", config: Optional[dict] = None) -> str:
    """解析 Telegram 启动方式"""
    cfg = config or get_app_config()
    if requested_transport != "auto":
        return requested_transport
    return cfg.get("telegram_user", {}).get("transport", "user")


def launch_platform(
    platform: str,
    max_steps: Optional[int] = None,
    step_delay: Optional[int] = None,
    headless: Optional[bool] = None,
    transport: str = "auto",
    url: Optional[str] = None,
    goal: Optional[str] = None,
    record_mode: bool = False,
    workflow_name: Optional[str] = None,
    workflow_file: Optional[str] = None,
    workflow_params: Optional[dict] = None,
) -> str:
    """
    统一启动平台

    Returns:
        实际使用的启动路径: telegram_user / legacy_web / free_web
    """
    app_config = get_app_config()
    runtime_config = app_config["runtime"]

    validate_config(app_config)

    # 自由网页操控模式
    if platform == "free_web":
        bot = FreeWebBot(
            url=url or "https://www.google.com",
            goal=goal or "探索网页",
            max_steps=max_steps if max_steps is not None else runtime_config["max_steps"],
            step_delay=step_delay if step_delay is not None else runtime_config["step_delay"],
            headless=headless,
            record_mode=record_mode,
            workflow_name=workflow_name,
            workflow_file=workflow_file,
            workflow_params=workflow_params or {},
        )
        bot.start()
        return "free_web"

    resolved_transport = resolve_telegram_transport(transport, app_config)
    if platform == "telegram" and resolved_transport == "user":
        validate_telegram_user_config(app_config)
        validate_telegram_user_settings(app_config)
        TelegramUserBot().run()
        return "telegram_user"

    bot = IMBot(
        platform=platform,
        max_steps=max_steps if max_steps is not None else runtime_config["max_steps"],
        step_delay=step_delay if step_delay is not None else runtime_config["step_delay"],
        headless=headless,
    )
    bot.start()
    return "legacy_web"
