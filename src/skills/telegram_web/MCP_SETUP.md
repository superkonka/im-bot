# Telegram Web MCP Server 配置指南

把你的 Telegram Web Skill 变成 AI 可以调用的工具，小波（或其他用户）只需要在 Claude Desktop 里说话，AI 就会自动操作 Telegram。

---

## ✅ 已验证功能

| 工具 | 功能 | 测试状态 |
|------|------|---------|
| `get_chat_list` | 获取聊天列表 | ✅ |
| `get_messages` | 读取指定聊天消息 | ✅ |
| `send_message` | 发送消息 | ✅ |
| `get_unread_summary` | 获取未读消息摘要 | ✅ |
| `get_contact_info` | 获取账号信息 | ✅ |

---

## 🚀 配置到 Claude Desktop

### 1. 编辑配置文件

打开 Claude Desktop 的 MCP 配置文件：

```bash
# macOS
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### 2. 添加 Telegram MCP Server

```json
{
  "mcpServers": {
    "telegram": {
      "command": "/Users/konka/im-bot/.venv/bin/python",
      "args": [
        "-m",
        "src.skills.telegram_web.telegram_mcp_server"
      ]
    }
  }
}
```

### 3. 重启 Claude Desktop

完全退出再重新打开 Claude Desktop，AI 会自动识别 `telegram` 工具集。

---

## 💬 使用示例

配置完成后，小波可以直接在 Claude Desktop 里说：

| 小波说的话 | AI 自动执行 |
|-----------|-----------|
| "帮我看看 Telegram 有什么新消息" | `get_unread_summary` |
| "读取我和小波的最近聊天记录" | `get_messages(chat_title="小波")` |
| "给我列出所有 Telegram 聊天" | `get_chat_list` |
| "回复小波说：好的，我正在处理" | `send_message(chat_title="小波", text="好的，我正在处理")` |

---

## 🔧 高级：配置到 Cursor

Cursor 也支持 MCP，编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "telegram": {
      "command": "/Users/konka/im-bot/.venv/bin/python",
      "args": ["-m", "src.skills.telegram_web.telegram_mcp_server"]
    }
  }
}
```

---

## ⚠️ 注意事项

1. **登录状态**：MCP Server 依赖已保存的浏览器状态（`data/telegram_web_state/`）。如果状态过期，需要重新运行 `demo.py` 登录。

2. **无头模式**：MCP Server 默认以无头模式（headless）运行，不显示浏览器窗口。

3. **发送消息**：`send_message` 工具会实际发送消息到真实联系人，AI 会自动提醒用户确认。

4. **安全性**：Session 文件包含登录凭证，请勿上传到 Git 或分享给他人。

---

## 📁 文件位置

```
src/skills/telegram_web/
├── telegram_mcp_server.py    # ⭐ MCP Server 主文件
├── skill.py                   # Web Skill 核心
├── demo.py                    # 登录演示
└── MCP_SETUP.md              # 本配置文档
```

---

## 🎯 给小波的交付清单

✅ **你提供给他：**
1. 项目路径：`/Users/konka/im-bot/`
2. 配置文件：`MCP_SETUP.md`
3. 已登录状态：`data/telegram_web_state/`（无需重新扫码）

✅ **他需要做：**
1. 安装 Claude Desktop
2. 复制上面的 JSON 配置
3. 重启 Claude
4. 开始用自然语言操作 Telegram

---

## 🔍 故障排查

**问题**：Claude 说找不到工具
**解决**：检查 `claude_desktop_config.json` 路径和 Python 解释器路径是否正确

**问题**：工具返回"未登录"
**解决**：运行 `.venv/bin/python src/skills/telegram_web/demo.py` 重新登录

**问题**：消息读取为空
**解决**：页面加载需要时间，AI 会自动重试，或手动增加 `asyncio.sleep`
