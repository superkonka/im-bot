# 🚀 MCP Server 部署指南

## 架构说明

```
Claude Desktop / Cursor
        │
        ▼  stdio (JSON-RPC)
┌─────────────────┐
│  mcp_server.py  │  ← 入口文件
│  (FastMCP)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ TelegramWebSkill│  ← Playwright 操作 Telegram Web
│  (headless=True)│     加载保存的登录态
└────────┬────────┘
         │
         ▼
   https://web.telegram.org/k/
```

**关键设计**：MCP Server 以 **无头模式**（headless）运行，依赖预先保存的浏览器登录状态。因此首次部署需要先通过 **有头模式** 登录一次。

---

## 一、环境准备

### 1. 系统要求

| 项目 | 要求 |
|------|------|
| Python | 3.9+ |
| 系统 | macOS / Linux / Windows WSL |
| 浏览器 | Chromium（Playwright 自动安装）|
| 网络 | 能访问 `web.telegram.org` |

### 2. 安装依赖

```bash
cd /Users/konka/im-bot

# 创建虚拟环境（如尚未创建）
python3 -m venv .venv

# 安装 Python 依赖
.venv/bin/pip install -r requirements.txt

# 安装 Playwright 浏览器（仅首次）
.venv/bin/playwright install chromium
```

### 3. 验证安装

```bash
# 检查 Python 包
.venv/bin/python -c "import fastmcp, playwright, telethon; print('OK')"

# 检查浏览器
.venv/bin/playwright show-browsers
```

---

## 二、首次登录（关键步骤 ⚠️）

MCP Server 以无头模式运行，**无法显示二维码或输入验证码**。必须先通过有头模式登录一次，保存状态。

### 方式 A：二维码登录（推荐）

```bash
.venv/bin/python src/skills/telegram_web/demo.py
```

流程：
1. 自动打开 Chromium 浏览器，显示 Telegram Web 登录页
2. 等待二维码渲染（约 3 秒）
3. 终端提示：
   ```
   📱 请用手机 Telegram App 扫描二维码
      步骤:
      1. 打开手机 Telegram
      2. 点击设置 → 设备 → 链接桌面设备
      3. 对准浏览器中的二维码扫描
   ```
4. 手机扫码 → 自动登录 → 显示聊天列表
5. 按 `Ctrl+C` 退出，状态自动保存到 `data/telegram_web_state/telegram_web_state.json`

### 方式 B：手机号登录

编辑 `demo.py` 修改手机号：
```python
PHONE = "+86138xxxx1234"  # 你的手机号（带国家码）
```

然后运行：
```bash
.venv/bin/python -c "
import asyncio, sys
from pathlib import Path
sys.path.insert(0, 'src')
from skills.telegram_web.skill import TelegramWebSkill

async def main():
    skill = TelegramWebSkill(headless=False)
    await skill.start()
    if not await skill.is_logged_in():
        await skill.login(
            phone='+86138xxxx1234',
            code_callback=lambda: input('验证码: ')
        )
    print('登录成功，按 Ctrl+C 退出')
    await asyncio.sleep(9999)

asyncio.run(main())
"
```

### 验证登录状态

```bash
# 检查状态文件是否存在
ls -la data/telegram_web_state/telegram_web_state.json

# 检查文件大小（正常应 > 5KB）
wc -c data/telegram_web_state/telegram_web_state.json
```

> ⚠️ **重要**：`data/telegram_web_state/` 包含登录凭证，**切勿提交到 Git**，已加入 `.gitignore`。

---

## 三、配置 Claude Desktop

### macOS

编辑配置文件：

```bash
# 创建/编辑 Claude Desktop 配置
mkdir -p ~/Library/Application\ Support/Claude
vim ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

写入以下内容：

```json
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
```

### Linux

```bash
mkdir -p ~/.config/claude
vim ~/.config/claude/claude_desktop_config.json
```

内容同上，路径适配。

### Windows

文件位置：
```
%APPDATA%\Claude\claude_desktop_config.json
```

```json
{
  "mcpServers": {
    "telegram": {
      "command": "C:\\Users\\<用户名>\\im-bot\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\<用户名>\\im-bot\\mcp_server.py", "telegram"]
    },
    "whatsapp": {
      "command": "C:\\Users\\<用户名>\\im-bot\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\<用户名>\\im-bot\\mcp_server.py", "whatsapp"]
    }
  }
}
```

---

## 四、启动与验证

### 1. 重启 Claude Desktop

完全退出 Claude Desktop（菜单栏图标也要退出），然后重新打开。

### 2. 验证 MCP Server 加载

打开 Claude Desktop，点击左下角 🔧 图标 → "MCP Servers"，应看到：

```
✅ telegram — connected
   Tools: 15 available
✅ whatsapp — connected
   Tools: 7 available
```

### 3. 测试对话

在 Claude 中输入：

```
看看我的 Telegram 有什么新消息
```

Claude 会自动调用 `get_unread_summary` 工具。

其他测试指令：
- `"搜索小波的聊天"` → `search_chat`
- `"读取我和小波的最近5条消息"` → `get_messages`
- `"回复小波说收到了"` → `send_message`

---

## 五、手动启动 MCP Server（调试）

不通过 Claude Desktop，直接命令行启动：

```bash
# 方式 1：stdio 模式（Claude Desktop 的调用方式）
.venv/bin/python mcp_server.py

# 方式 2：SSE 模式（供 HTTP 客户端调用）
.venv/bin/python -c "
import sys
sys.path.insert(0, 'src')
from skills.telegram_web.telegram_mcp_server import mcp
mcp.run(transport='sse', port=6277)
"
```

> 注：FastMCP 默认使用 `stdio` 传输，适合 Claude Desktop 的进程间通信。`sse` 模式适合 Web 应用调用。

---

## 六、故障排查

### 问题 1：Claude 显示 "telegram — disconnected"

**排查步骤：**

```bash
# 1. 检查 Python 路径是否正确
/Users/konka/im-bot/.venv/bin/python --version

# 2. 手动运行 MCP Server 看报错
.venv/bin/python mcp_server.py
# 正常应无输出挂起（等待 stdio 输入）

# 3. 检查日志
# Claude Desktop 日志位置：
# macOS: ~/Library/Logs/Claude/mcp*.log
```

### 问题 2："Telegram Web 未登录"

**原因**：状态文件丢失或过期。

**解决**：
```bash
# 重新运行有头模式登录
.venv/bin/python src/skills/telegram_web/demo.py
# 扫码/验证后按 Ctrl+C 退出，状态自动保存
```

### 问题 3：工具调用超时

**原因**：Telegram Web 加载慢或网络问题。

**解决**：
- 检查网络连接
- 查看 `data/telegram_web_state/` 下的截图排查

### 问题 4：消息发送失败

**排查**：
```bash
# 手动测试发送
.venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from skills.telegram_web.skill import TelegramWebSkill

async def test():
    skill = TelegramWebSkill(headless=False)
    await skill.start()
    chats = await skill.get_chat_list()
    print([c.title for c in chats[:5]])
    await skill.stop()

asyncio.run(test())
"
```

---

## 七、生产环境部署（高级）

### Docker 部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .
# 预先挂载登录状态文件
VOLUME ["/app/data/telegram_web_state"]

CMD [".venv/bin/python", "mcp_server.py"]
```

### 注意事项

| 问题 | 建议 |
|------|------|
| Session 过期 | Telegram Web 状态通常持久，若失效需重新登录 |
| 多实例冲突 | 同一账号同时只能有一个浏览器实例登录 Telegram Web |
| 风控风险 | 频繁操作可能触发 Telegram 风控，建议控制调用频率 |
| 隐私安全 | `data/telegram_web_state/` 包含敏感凭证，严格限制访问权限 |

---

## 八、更新与维护

### 更新 MCP 工具

```bash
cd /Users/konka/im-bot
git pull  # 如有更新
.venv/bin/pip install -r requirements.txt
```

### 重置登录状态

```bash
rm data/telegram_web_state/telegram_web_state.json
# 然后重新执行「首次登录」步骤
```

---

## 快速检查清单

部署前确认：

- [ ] Python 3.9+ 已安装
- [ ] `.venv` 虚拟环境已创建
- [ ] `requirements.txt` 依赖已安装
- [ ] Playwright Chromium 已安装
- [ ] 已运行 `demo.py` 完成首次登录
- [ ] `data/telegram_web_state/telegram_web_state.json` 存在且 > 5KB
- [ ] Claude Desktop 配置已写入
- [ ] Claude Desktop 已重启
- [ ] MCP Servers 面板显示 "telegram — connected"
