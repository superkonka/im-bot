#!/usr/bin/env python3
"""
IM Bot MCP Server 统一入口

Claude Desktop、Cursor 等 AI 客户端通过此文件调用 Telegram / WhatsApp 工具。

配置:
    编辑 ~/Library/Application Support/Claude/claude_desktop_config.json:
    {
      "mcpServers": {
        "telegram": {
          "command": "/Users/konka/im-bot/.venv/bin/python",
          "args": ["/Users/konka/im-bot/mcp_server.py", "telegram"]
        },
        "whatsapp": {
          "command": "/Users/konka/im-bot/.venv/bin/python",
          "args": ["/Users/konka/im-bot/mcp_server.py", "whatsapp"]
        }
      }
    }

启动:
    .venv/bin/python mcp_server.py telegram    # 启动 Telegram MCP Server
    .venv/bin/python mcp_server.py whatsapp   # 启动 WhatsApp MCP Server
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def main():
    if len(sys.argv) < 2:
        print("用法: python mcp_server.py <telegram|whatsapp>")
        print("")
        print("示例:")
        print("  python mcp_server.py telegram   # 启动 Telegram MCP Server")
        print("  python mcp_server.py whatsapp   # 启动 WhatsApp MCP Server")
        sys.exit(1)

    platform = sys.argv[1].lower()

    if platform == "telegram":
        from skills.telegram_web.telegram_mcp_server import mcp
        mcp.run()
    elif platform == "whatsapp":
        from skills.whatsapp_web.whatsapp_mcp_server import mcp
        mcp.run()
    else:
        print(f"❌ 未知平台: {platform}")
        print("支持的平台: telegram, whatsapp")
        sys.exit(1)


if __name__ == "__main__":
    main()
