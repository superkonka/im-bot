# 🤖 IM Bot

基于 Telegram 和 WhatsApp 的自动化消息工具集，提供 Web DOM 操作、MTProto 协议和 MCP Server 多种能力。

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
│  whatsapp_web/  ←── Playwright (独立 Chromium) ⭐ 新增 │
├─────────────────────────────────────────────────────────┤
│  核心层 (src/core/)                                      │
│  config.py      ←── 配置管理                            │
│  logger.py      ←── 日志                                │
├─────────────────────────────────────────────────────────┤
│  数据层 (data/)                                          │
│  telegram_web_state/  ←── 浏览器状态                    │
│  whatsapp_web_state/  ←── WhatsApp storage_state ⭐ 新增│
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
// ~/Library/Application Support/Claude/claude_desktop_config.json
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

重启 Claude 后，直接说话：
- "帮我看看 Telegram 有什么新消息"
- "读取我和小波的聊天记录"
- "回复小波说项目进度正常"
- "看看 WhatsApp 有什么新消息"
- "通过 WhatsApp 给小波发消息"

### 方式二：本地 CLI

```bash
# 运行 Skill 演示（浏览器登录 + 收发消息）
.venv/bin/python src/skills/telegram_web/demo.py

# 提取 Web Session → Telethon StringSession
.venv/bin/python src/skills/telegram_web/session_extractor.py

# 启动对话引擎
.venv/bin/python main.py agent

# WhatsApp Web Skill 演示 ⭐ 新增
.venv/bin/python src/skills/whatsapp_web/demo.py
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
├── src/                       # 源码
│   ├── config.py              # 配置管理
│   ├── logger.py              # 日志
│   ├── helpers.py             # 通用工具
│   ├── chatbot.py             # 对话引擎
│   ├── runtime_control.py     # 运行时控制
│   │
│   └── skills/                # 技能层
│       ├── telegram/          # MTProto 方案
│       │   ├── skill.py
│       │   ├── session_manager.py
│       │   └── types.py
│       ├── telegram_web/      # Web DOM 方案 (Telegram)
│       │   ├── skill.py
│       │   ├── telegram_mcp_server.py
│       │   ├── session_extractor.py
│       │   ├── crawler_loop.py
│       │   └── demo.py
│       └── whatsapp_web/      # Web DOM 方案 (WhatsApp) ⭐ 新增
│           ├── __init__.py
│           ├── skill.py
│           ├── whatsapp_mcp_server.py  ←── MCP 工具注册 ⭐ 新增
│           └── demo.py
│
└── data/                      # 运行时数据（gitignored）
    ├── telegram_web_state/    # 浏览器登录状态
    ├── whatsapp_web_state/    # WhatsApp 登录状态 ⭐ 新增
    └── telegram_sessions/     # Telethon Session
```

---

## 🗂️ 项目状态

当前版本：**v2.3.0 MVP** — 功能可用，持续迭代中。

查看详细待办清单和改进计划 → [**TODO.md**](TODO.md)

---

## 🔧 核心能力

| 能力 | 路径 | 说明 |
|------|------|------|
| **Web 扫码登录** | `telegram_web/demo.py` | 浏览器打开 Telegram Web，扫码即可 |
| **Session 提取** | `telegram_web/session_extractor.py` | Web 登录态 → Telethon StringSession |
| **MCP 工具集** | `telegram_web/telegram_mcp_server.py` | Claude/Cursor 调用，共 15 个工具 |
| **MTProto 技能** | `telegram/skill.py` | Telethon 原生协议 |
| **对话引擎** | `agent/chatbot.py` | LLM + 策略约束 + 长期记忆 |
| **WhatsApp Web** | `whatsapp_web/skill.py` ⭐ | Playwright 独立实例，扫码登录、消息收发、群链接加入 |

---

## 🛠️ MCP 工具集详情

配置到 Claude Desktop 后，可直接通过自然语言调用：

### Telegram 工具

#### 读取类工具（安全，推荐常用）

| 工具 | 功能 | 示例指令 |
|------|------|----------|
| `get_chat_list` | 获取聊天列表 | "看看我最近有哪些聊天" |
| `get_messages` | 获取指定聊天的消息 | "读取我和小波的最近消息" |
| `get_unread_summary` | 获取未读消息摘要 | "有什么新消息吗" |
| `get_chat_info` | 获取聊天详情（成员数、类型等） | "这个群有多少人" |
| `search_chat` | 搜索聊天或联系人 | "搜索小波的聊天" |
| `get_contacts` | 获取联系人列表 | "列出我的联系人" |
| `get_message_by_keyword` | 按关键词搜索消息 | "找一下关于项目的消息" |
| `get_contact_info` | 获取当前账号信息 | "我登录的是哪个账号" |

#### 写入类工具（需谨慎使用）

| 工具 | 功能 | 示例指令 |
|------|------|----------|
| `send_message` | 发送消息 | "回复小波说项目进度正常" |
| `reply_to_message` | 回复特定消息 | "回复小波刚才那条消息" |
| `forward_message` | 转发消息 | "把这条消息转发到工作群" |
| `delete_message` | 删除自己发送的消息 | "删掉我刚才发的那条" |
| `mark_as_read` | 标记已读 | "把这些消息标为已读" |
| `pin_chat` | 置顶/取消置顶聊天 | "置顶这个群" |
| `archive_chat` | 归档聊天 | "归档这个聊天" |

### WhatsApp 工具 ⭐ 新增

| 工具 | 功能 | 示例指令 |
|------|------|----------|
| `get_chat_list` | 获取聊天列表 | "看看我的 WhatsApp 有哪些聊天" |
| `get_messages` | 获取指定聊天的消息 | "读取 WhatsApp 上小波的消息" |
| `get_unread_summary` | 获取未读消息摘要 | "WhatsApp 有什么新消息吗" |
| `send_message` | 发送消息 | "用 WhatsApp 给小波发消息" |
| `search_chat` | 搜索聊天或联系人 | "在 WhatsApp 搜索小波" |
| `join_group_link` | 通过链接加入群组 | "加入这个 WhatsApp 群" |
| `get_contact_info` | 获取当前账号信息 | "我登录的是哪个 WhatsApp 账号" |

---

## 🛡️ 安全提示

1. **Session 文件** (`data/telegram_sessions/` 和 `data/telegram_web_state/`) 包含登录凭证，**请勿提交到 Git**
2. **发送消息** 会实际发送到真实联系人，MCP Server 默认只读，发送需显式授权
3. **Telegram 风控**：自动化个人账号存在封号风险，请控制发送频率

---

## 📝 更新日志

### v2.3.0 (2025-06)
- **WhatsApp MCP Server** ⭐
  - 新增 `whatsapp_mcp_server.py`，7 个 MCP 工具
  - `mcp_server.py` 支持 `telegram` / `whatsapp` 双平台参数
  - Claude Desktop 可配置双服务独立运行
  - 与现有 Telegram MCP Server 完全隔离，互不干扰

### v2.2.0 (2025-06)
- **新增 WhatsApp Web Skill** ⭐
  - 基于 Playwright 独立 Chromium 实例
  - 支持扫码登录、状态持久化（storage_state）
  - 支持聊天列表读取、消息收发
  - 支持群链接加入（`join_group_link`）
  - 解决 WebBridge 无法点击 WhatsApp Web React 元素的问题
- **双平台架构**：Telegram + WhatsApp（均为 Playwright）

### v2.1.0 (2025-06)
- **MCP Server 增强**：从 5 个工具扩展到 13 个
  - 新增 `search_chat` — 搜索聊天/联系人
  - 新增 `reply_to_message` — 回复特定消息
  - 新增 `forward_message` — 转发消息
  - 新增 `delete_message` — 删除自己发送的消息
  - 新增 `mark_as_read` — 标记已读
  - 新增 `get_chat_info` — 获取聊天详情（成员数、类型、描述等）
  - 新增 `pin_chat` / `unpin_chat` — 置顶/取消置顶
  - 新增 `archive_chat` — 归档聊天
  - 新增 `get_contacts` — 获取联系人列表
  - 新增 `get_message_by_keyword` — 按关键词搜索消息
- **底层 Skill 增强**：`TelegramWebSkill` 新增 8 个操作方法

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
