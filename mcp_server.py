#!/usr/bin/env python3
"""
Telegram MCP Server 入口

Claude Desktop、Cursor 等 AI 客户端通过此文件调用 Telegram 工具。

配置:
    编辑 ~/.config/claude/claude_desktop_config.json:
    {
      "mcpServers": {
        "telegram": {
          "command": "/Users/konka/im-bot/.venv/bin/python",
          "args": ["/Users/konka/im-bot/mcp_server.py"]
        }
      }
    }

启动:
    .venv/bin/python mcp_server.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from skills.telegram_web.telegram_mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
