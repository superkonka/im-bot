#!/usr/bin/env python3
"""
IM Bot 统一入口

用法:
    # MCP Server（AI 客户端调用）⭐ 推荐
    .venv/bin/python mcp_server.py

    # 本地 CLI
    .venv/bin/python main.py skill            # 运行 Skill 演示
    .venv/bin/python main.py agent            # 运行对话引擎
    .venv/bin/python main.py extract          # 提取 Web Session
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def _skill_demo():
    """运行 Telegram Web Skill 演示"""
    print("启动 Telegram Web Skill 演示...")
    print("用法: .venv/bin/python src/skills/telegram_web/demo.py")


def _agent_demo():
    """运行对话引擎"""
    print("启动对话引擎...")
    print("用法: from agent.chatbot import TelegramUserBot")


def _extract_session():
    """提取 Web Session"""
    print("提取 Telegram Web Session...")
    print("用法: .venv/bin/python src/skills/telegram_web/session_extractor.py")


def main():
    parser = argparse.ArgumentParser(
        description="IM Bot - Telegram 自动化工具集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式说明:
  skill    - 测试 Telegram Web Skill（登录、收发消息）
  agent    - 启动对话引擎（TelegramUserBot）
  extract  - 从浏览器提取 Session 并转换为 Telethon 格式

推荐入口:
  .venv/bin/python mcp_server.py   # MCP Server（AI 客户端调用）
        """
    )
    parser.add_argument(
        "mode",
        choices=["skill", "agent", "extract"],
        help="运行模式"
    )
    args = parser.parse_args()

    if args.mode == "skill":
        _skill_demo()
    elif args.mode == "agent":
        _agent_demo()
    elif args.mode == "extract":
        _extract_session()


if __name__ == "__main__":
    main()
