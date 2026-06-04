# 🤖 IM Bot

基于 Telegram 的自动化消息工具集，提供 Web DOM 操作、MTProto 协议和 MCP Server 三种能力。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  入口层                                                  │
│  mcp_server.py  ←── Claude/Cursor 等 AI 客户端调用      │
│  main.py        ←── 本地 CLI                            │
├─────────────────────────────────────────────────────────┤
│  应用层 (src/agent/)                                     │
│  chatbot.py     ←── Telegram 对话引擎                   │
│  runtime_control.py  ←── 运行时控制面板                 │
├─────────────────────────────────────────────────────────┤
│  技能层 (src/skills/)                                    │
│  telegram/      ←── Telethon (MTProto)                 │
│  telegram_web/  ←── Playwright (Web DOM)               │
│  └─ telegram_mcp_server.py  ←── MCP 工具注册          │
├─────────────────────────────────────────────────────────┤
│  核心层 (src/core/)                                      │
│  config.py      ←── 配置管理                            │
│  logger.py      ←── 日志                                │
├─────────────────────────────────────────────────────────┤
│  数据层 (data/)                                          │
│  telegram_web_state/  ←── 浏览器状态                    │
│  telegram_sessions/   ←── Telethon Session             │
└─────────────────────────────────────────────────────────┘
```

---

## 安装

```bash
# 克隆
git clone https://github.com/superkonka/im-bot.git
cd im-bot

# 安装依赖
.venv/bin/pip install -r requirements.txt
```

**环境变量**:
```bash
export KIMI_API_KEY="sk-your-key"
export TELEGRAM_API_ID="12345678"
export TELEGRAM_API_HASH="your-hash"
```

---

## 🚀 快速开始

### 方式一：MCP Server（推荐）

配置到 Claude Desktop：

```json
// ~/.config/claude/claude_desktop_config.json
{
  "mcpServers": {
    "telegram": {
      "command": "/Users/konka/im-bot/.venv/bin/python",
      "args": ["/Users/konka/im-bot/mcp_server.py"]
    }
  }
}
```

重启 Claude 后，直接说话：
- "帮我看看 Telegram 有什么新消息"
- "读取我和小波的聊天记录"
- "回复小波说项目进度正常"

### 方式二：本地 CLI

```bash
# 运行 Skill 演示（浏览器登录 + 收发消息）
.venv/bin/python src/skills/telegram_web/demo.py

# 提取 Web Session → Telethon StringSession
.venv/bin/python src/skills/telegram_web/session_extractor.py

# 启动对话引擎
.venv/bin/python main.py agent
```

---

## 📁 目录结构

```
im-bot/
├── mcp_server.py              # ⭐ MCP Server 主入口
├── main.py                    # CLI 入口
├── requirements.txt
├── README.md                  # 本文档
│
├── src/
│   ├── core/                  # 基础设施
│   │   ├── config.py
│   │   └── logger.py
│   │
│   ├── skills/                # 技能层（工具）
│   │   ├── telegram/          # MTProto 方案
│   │   │   ├── skill.py
│   │   │   ├── session_manager.py
│   │   │   └── types.py
│   │   └── telegram_web/      # Web DOM 方案
│   │       ├── skill.py
│   │       ├── telegram_mcp_server.py
│   │       ├── session_extractor.py
│   │       ├── crawler_loop.py
│   │       └── demo.py
│   │
│   ├── agent/                 # 应用层（对话引擎）
│   │   ├── chatbot.py
│   │   └── runtime_control.py
│   │
│   └── utils/                 # 通用工具
│       └── helpers.py
│
└── data/                      # 运行时数据（gitignored）
    ├── telegram_web_state/    # 浏览器登录状态
    └── telegram_sessions/     # Telethon Session
```

---

## 🔧 核心能力

| 能力 | 路径 | 说明 |
|------|------|------|
| **Web 扫码登录** | `telegram_web/demo.py` | 浏览器打开 Telegram Web，扫码即可 |
| **Session 提取** | `telegram_web/session_extractor.py` | Web 登录态 → Telethon StringSession |
| **MCP 工具集** | `telegram_web/telegram_mcp_server.py` | Claude/Cursor 调用 |
| **MTProto 技能** | `telegram/skill.py` | Telethon 原生协议 |
| **对话引擎** | `agent/chatbot.py` | LLM + 策略约束 + 长期记忆 |

---

## 🛡️ 安全提示

1. **Session 文件** (`data/telegram_sessions/` 和 `data/telegram_web_state/`) 包含登录凭证，**请勿提交到 Git**
2. **发送消息** 会实际发送到真实联系人，MCP Server 默认只读，发送需显式授权
3. **Telegram 风控**：自动化个人账号存在封号风险，请控制发送频率

---

## 📝 更新日志

### v2.0.0 (2025-06)
- 重构架构，引入 Skills + Agent 分层
- 新增 MCP Server，支持 Claude Desktop 调用
- 新增 Web Session 提取器（浏览器扫码 → Telethon）
- 删除旧视觉驱动层（platforms/、im_bot.py 等）

### v1.1.0 (2025-03)
- Telegram 用户账号模式
- 工作流录制与回放

### v1.0.0 (2025-03)
- 初始版本：WhatsApp + Telegram Web 视觉自动化
