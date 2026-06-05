# 🏗️ IM Bot 项目架构解析

> 一份帮助你从零理解这个项目的文档。
> 读完本文档后，你将知道：这个项目是什么、怎么运作、模块如何协作、以及它的设计取舍。

---

## 一、项目定位：一句话概括

**IM Bot 是一个让 AI（Claude/Cursor）能够通过自然语言操作 Telegram 和 WhatsApp 的桥梁。**

它的核心价值是：用户不需要学习任何 API，直接对 AI 说"帮我看看 Telegram 有什么新消息"，AI 就会自动调用工具完成操作。

---

## 二、整体架构（三层模型）

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           第一层：用户接口层                               │
│                                                                          │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│   │ Claude Desktop│  │    Cursor    │  │   命令行      │                  │
│   │   (MCP 协议)  │  │  (MCP 协议)  │  │  (main.py)   │                  │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
└──────────┼─────────────────┼─────────────────┼──────────────────────────┘
           │                 │                 │
           ▼                 ▼                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           第二层：协议适配层                               │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    mcp_server.py (统一入口)                      │   │
│   │         python mcp_server.py telegram  → Telegram MCP           │   │
│   │         python mcp_server.py whatsapp  → WhatsApp MCP           │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   ┌──────────────────────┐    ┌──────────────────────┐                │
│   │ telegram_mcp_server  │    │ whatsapp_mcp_server  │                │
│   │    (FastMCP 框架)    │    │    (FastMCP 框架)    │                │
│   │    13 个 Tools       │    │     7 个 Tools       │                │
│   └──────────┬───────────┘    └──────────┬───────────┘                │
└──────────────┼────────────────────────────┼────────────────────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           第三层：技能实现层                               │
│                                                                          │
│   ┌──────────────────────┐    ┌──────────────────────┐                 │
│   │  TelegramWebSkill    │    │  WhatsAppWebSkill    │                 │
│   │  (Playwright DOM)    │    │  (Playwright DOM)    │                 │
│   │                      │    │                      │                 │
│   │  ┌────────────────┐  │    │  ┌────────────────┐  │                 │
│   │  │ Chromium 实例  │──┼────┼──►│ Chromium 实例  │  │                 │
│   │  │ (独立浏览器)   │  │    │  │ (持久化上下文) │  │                 │
│   │  └────────────────┘  │    │  └────────────────┘  │                 │
│   └──────────────────────┘    └──────────────────────┘                 │
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │                    chatbot.py (TelegramUserBot)                   │  │
│   │                    独立运行的自动对话引擎                          │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │  │
│   │  │ 事件监听 │──►│ LLM 决策 │──►│ 安全审核 │──►│ 消息发送 │         │  │
│   │  │(Telethon)│  │(Kimi API)│  │(二次审核)│  │(Telethon)│         │  │
│   │  └──────────┘  └──────────┘  └──────────┘  └──────────┘         │  │
│   └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 关键认知

- **MCP 协议**：Model Context Protocol，Anthropic 推出的标准，让 AI 客户端（Claude）能调用外部工具
- **stdio 传输**：MCP Server 通过标准输入输出与 Claude Desktop 通信（JSON-RPC 2.0）
- **Skill 模式**：每个平台封装为独立的 Skill 类，提供 `start()` / `stop()` / 操作接口

---

## 三、模块详解

### 3.1 入口文件

#### `mcp_server.py` — MCP 统一入口

```python
# 启动方式
python mcp_server.py telegram   # 启动 Telegram MCP Server
python mcp_server.py whatsapp   # 启动 WhatsApp MCP Server
```

**为什么需要统一入口？**
- Claude Desktop 配置中，每个 MCP Server 是一个独立的进程
- 用户只需要改一个参数就能切换平台，不需要维护多个入口文件

#### `main.py` — CLI 入口

当前只是占位符，提供三种模式的提示：
- `skill` → 运行演示
- `agent` → 启动对话引擎
- `extract` → 提取 Session

### 3.2 MCP Server 层

#### `telegram_mcp_server.py` — 15 个工具

```
读取类（安全）
├── get_chat_list          # 获取聊天列表
├── get_messages           # 获取指定聊天消息
├── get_unread_summary     # 未读消息摘要
├── get_chat_info          # 聊天详情（成员数、类型）
├── search_chat            # 搜索聊天/联系人
├── get_contacts           # 联系人列表
├── get_message_by_keyword # 关键词搜索消息
└── get_contact_info       # 当前账号信息

写入类（需谨慎）
├── send_message           # 发送消息
├── reply_to_message       # 回复特定消息
├── forward_message        # 转发消息
├── delete_message         # 删除自己的消息
├── mark_as_read           # 标记已读
├── pin_chat               # 置顶/取消置顶
└── archive_chat           # 归档聊天
```

#### `whatsapp_mcp_server.py` — 7 个工具

```
├── get_chat_list          # 获取聊天列表
├── get_messages           # 获取指定聊天消息
├── send_message           # 发送消息
├── get_unread_summary     # 未读消息摘要
├── search_chat            # 搜索聊天
├── join_group_link        # 通过链接加入群组（WhatsApp 特色）
└── get_contact_info       # 当前账号信息
```

**懒加载机制**：
```python
_skill = None

async def _get_skill():
    if _skill is None:
        async with _skill_lock:       # 防止并发初始化
            if _skill is None:
                _skill = TelegramWebSkill(headless=True)
                await _skill.start()
                if not await _skill.is_logged_in():
                    raise RuntimeError("未登录")
    return _skill
```

### 3.3 Skill 层

#### `TelegramWebSkill` vs `WhatsAppWebSkill` 对比

| 维度 | TelegramWebSkill | WhatsAppWebSkill |
|------|------------------|------------------|
| 浏览器启动 | `browser.new_context()` | `launch_persistent_context()` |
| 状态保存 | 手动 `storage_state.json` | 自动持久化到 `chromium_profile/` |
| 登录方式 | 手机号+验证码 / 二维码 | 仅二维码 |
| DOM 策略 | CSS class + data 属性 | `data-testid` 属性为主 |
| 特色功能 | 回复、转发、删除、置顶 | 群链接加入 |
| 代码量 | ~780 行 | ~940 行 |

**共同的底层能力**：
```python
# 两者都有这些方法
async def get_chat_list(self, limit=50) -> List[ChatItem]
async def open_chat(self, chat_id: str) -> bool
async def get_messages(self, limit=20) -> List[WebMessage]
async def send_message(self, text: str) -> SendResult
async def search_chat(self, query: str) -> List[ChatItem]
```

#### 登录态持久化原理

**Telegram**（手动保存）：
```
启动 → 检查 storage_state.json → 有则加载 cookies + localStorage
      → 打开 web.telegram.org/k/ → 页面自动恢复登录态
      → stop() 时保存 storage_state.json
```

**WhatsApp**（自动持久化）：
```
启动 → launch_persistent_context(user_data_dir="chromium_profile/")
      → 所有数据（cookies + localStorage + IndexedDB）自动保存到该目录
      → 下次启动自动恢复
```

> ⚠️ **关键区别**：WhatsApp 的密钥存储在 IndexedDB 中，必须使用持久化上下文才能恢复。Telegram 的登录态主要在 cookies 中，手动保存即可。

### 3.4 自动对话引擎（chatbot.py）

这是项目中**最复杂**的模块，独立运行，不通过 MCP。

```
┌────────────────────────────────────────────────────────────┐
│                    TelegramUserBot                          │
│                                                             │
│  ┌─────────────┐                                           │
│  │ 事件处理器  │ ◄── 新消息事件（Telethon）                 │
│  └──────┬──────┘                                           │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │ _worker_    │    │ _scheduler_ │    │ _operator_  │   │
│  │ _loop()     │    │ _loop()     │    │ _loop()     │   │
│  │ 串行处理    │    │ 定时主动    │    │ 操作员命令  │   │
│  │ 回复任务    │    │ 发起对话    │    │ 轮询        │   │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘   │
│         │                   │                   │          │
│         └───────────────────┼───────────────────┘          │
│                             ▼                               │
│              ┌─────────────────────────┐                   │
│              │ TelegramLLMOrchestrator │                   │
│              │ 构建 Prompt → Kimi API  │                   │
│              │ → 解析 JSON 决策        │                   │
│              └───────────┬─────────────┘                   │
│                          ▼                                  │
│              ┌─────────────────────────┐                   │
│              │  ConversationGuard      │                   │
│              │  频率/时间/话题/边界控制  │                   │
│              └───────────┬─────────────┘                   │
│                          ▼                                  │
│              ┌─────────────────────────┐                   │
│              │ TelegramSafetyReviewer  │                   │
│              │ LLM 二次安全审核         │                   │
│              └───────────┬─────────────┘                   │
│                          ▼                                  │
│              ┌─────────────────────────┐                   │
│              │    发送 / 存入草稿       │                   │
│              └─────────────────────────┘                   │
└────────────────────────────────────────────────────────────┘
```

**三层安全机制**：

1. **Guard（规则层）**：频率限制（每小时最多主动发起 N 次）、时间窗口（避免深夜打扰）、话题白名单/黑名单、消息去重
2. **Reviewer（模型层）**：LLM 二次审核，检查是否有不当内容、是否符合人设、是否冒犯对方
3. **Operator（人工层）**：高风险消息存入 `pending_draft`，等待人工审批

---

## 四、数据流：一次完整的请求链路

### 场景：用户说"帮我给小波发消息说晚上吃饭"

```
用户输入
    │
    ▼
Claude Desktop (本地 LLM 推理)
    │
    ├── 识别意图：send_message
    ├── 提取参数：chat_title="小波", text="晚上吃饭"
    └── 决定调用工具
    │
    ▼
stdio JSON-RPC
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "send_message",
    "arguments": {
      "chat_title": "小波",
      "text": "晚上吃饭"
    }
  }
}
    │
    ▼
mcp_server.py (接收 stdio)
    │
    ├── 判断 platform=telegram
    └── 转发到 telegram_mcp_server.py
    │
    ▼
telegram_mcp_server.py
    │
    ├── 调用 _get_skill() (懒加载)
    │   ├── 首次：启动 Chromium (headless)
    │   ├── 加载 storage_state.json
    │   └── 检查 is_logged_in()
    │
    ├── 查找聊天：page.locator('.chatlist-chat').filter(has_text="小波")
    ├── 点击进入：.click()
    ├── 等待加载：asyncio.sleep(2)
    ├── 输入消息：input.fill("晚上吃饭")
    ├── 点击发送：send_btn.click()
    └── 返回结果："✅ 消息已发送到 '小波': 晚上吃饭"
    │
    ▼
格式化文本返回给 Claude Desktop
    │
    ▼
Claude 展示给用户："已经给小波发送了消息：晚上吃饭"
```

**耗时分析**：
- Claude 推理：~1-3 秒
- MCP 调用 + Skill 初始化（首次）：~5-10 秒（启动浏览器）
- MCP 调用（已初始化）：~2-5 秒
- 总计（首次）：~8-15 秒
- 总计（后续）：~3-8 秒

---

## 五、三种技术方案的设计取舍

### 方案 A：Telegram Web (Playwright) — 用于 MCP

**为什么选择？**
- 不需要 `api_id` / `api_hash`（Telegram 官方 API 需要的凭证）
- 用户只需要扫码或手机号登录，门槛最低
- 直接操作 Web 界面，AI 理解更直观

**代价？**
- 依赖 DOM 结构，Telegram 更新前端可能失效
- 无头模式下某些操作不稳定
- 消息监听只能轮询，不是实时推送

### 方案 B：Telegram API (Telethon) — 用于 chatbot.py

**为什么选择？**
- 稳定、实时、功能完整
- 事件驱动（NewMessage 事件），无需轮询
- 不受前端更新影响

**代价？**
- 需要 `api_id` / `api_hash`（需要去 Telegram 开发者平台申请）
- 无法通过 MCP 暴露（需要长期运行的客户端连接）

### 方案 C：WhatsApp Web (Playwright) — 用于 MCP

**为什么选择？**
- WhatsApp 没有官方 API（Business API 需要 Facebook 审核）
- Playwright 是唯一可行的自动化方案

**代价？**
- 与 Telegram Web 相同：DOM 脆弱、轮询监听
- 每次只能在一个浏览器实例中登录

---

## 六、关键设计决策

### 决策 1：为什么用两个独立的 MCP Server？

```json
{
  "telegram": { "args": ["mcp_server.py", "telegram"] },
  "whatsapp": { "args": ["mcp_server.py", "whatsapp"] }
}
```

而不是一个 Server 包含所有工具？

**原因**：
- 两个平台都需要启动独立的 Chromium 实例
- 如果合并，一个失败会导致整个 Server 不可用
- Claude Desktop 中两个服务独立显示，更容易排查问题

### 决策 2：为什么 WhatsApp 用 `launch_persistent_context`，Telegram 用 `new_context`？

**WhatsApp**：
- 密钥存储在 IndexedDB 中，必须使用持久化上下文才能保留
- `launch_persistent_context` 自动保存所有浏览器数据

**Telegram**：
- 登录态主要在 cookies 中
- 使用 `storage_state` 手动保存更可控，便于备份和迁移

### 决策 3：为什么 chatbot.py 不通过 MCP 暴露？

**原因**：
- chatbot.py 需要长期运行（7×24 小时监听消息）
- MCP 协议是请求-响应模式，不适合事件驱动
- chatbot.py 有自己的安全审核和审批流程，不适合直接暴露给 AI

---

## 七、数据目录结构

```
data/
├── app_config.json              # 应用配置（API 密钥、人设、规则）
├── telegram_web_state/
│   ├── telegram_web_state.json  # 浏览器 cookies + localStorage
│   └── screenshot.png           # 调试用截图
├── whatsapp_web_state/
│   ├── chromium_profile/        # 持久化浏览器数据（IndexedDB 等）
│   ├── whatsapp_web_state.json  # 额外的状态文件
│   └── login_debug.png          # 调试用截图
├── telegram_sessions/
│   └── *.session                # Telethon 会话文件
└── telegram_crawl/              # 爬取的历史数据（JSON）
```

---

## 八、阅读代码的建议顺序

如果你是新加入的开发者，建议按这个顺序阅读：

```
1. README.md                    # 了解项目全貌
2. 本文档 (ARCHITECTURE.md)     # 理解架构设计
3. mcp_server.py                # 入口（最简单，50 行）
4. src/skills/telegram_web/telegram_mcp_server.py  # 看 Tool 如何定义
5. src/skills/telegram_web/skill.py                # 看底层 Skill 实现
6. src/skills/whatsapp_web/skill.py                # 对比两个 Skill
7. src/config.py                # 了解配置体系
8. src/chatbot.py               # 最复杂，放到最后
```

---

## 九、当前状态与演进路线

```
v1.0 (2025-03) ──► 初始版本：视觉驱动 WhatsApp + Telegram
         │
v1.1 (2025-03) ──► 用户账号模式 + 工作流录制回放
         │
v2.0 (2025-06) ──► 架构重构：Skills + Agent 分层，引入 MCP Server
         │
v2.1 (2025-06) ──► Telegram MCP 工具从 5 个扩展到 13 个
         │
v2.2 (2025-06) ──► 新增 WhatsApp Web Skill（Playwright）
         │
v2.3 (2025-06) ──► WhatsApp MCP Server（7 个工具），双平台统一入口
         │
    [当前]         ──► 功能完整的 MVP，20 个 MCP 工具
```

### 已验证的能力

| 能力 | Telegram | WhatsApp |
|------|----------|----------|
| 获取聊天列表 | ✅ | ✅ |
| 获取消息 | ✅ | ✅ |
| 发送消息 | ✅ | ✅ |
| 未读摘要 | ✅ | ✅ |
| 搜索聊天 | ✅ | ✅ |
| 回复消息 | ✅ | ❌ |
| 转发消息 | ✅ | ❌ |
| 删除消息 | ✅ | ❌ |
| 标记已读 | ✅ | ❌ |
| 置顶聊天 | ✅ | ❌ |
| 归档聊天 | ✅ | ❌ |
| 获取联系人 | ✅ | ❌ |
| 关键词搜索 | ✅ | ❌ |
| 加入群链接 | ❌ | ✅ |

---

## 十、常见问题 FAQ

**Q1: 为什么 WhatsApp 的工具比 Telegram 少？**
> WhatsApp Web 的 DOM 结构更复杂（React 组件化），部分操作（如转发、回复）的实现难度更高。可以后续逐步补齐。

**Q2: Telegram 和 WhatsApp 能同时运行吗？**
> 可以。Claude Desktop 配置中分别启动两个 MCP Server，每个有独立的 Chromium 实例。但 WhatsApp 限制同一账号只能在 **一个浏览器实例** 中登录，不能同时在桌面 Chrome 和 Playwright 中登录。

**Q3: chatbot.py 和 MCP Server 是什么关系？**
> 没有关系。chatbot.py 是独立运行的自动对话引擎（Telethon），MCP Server 是 Claude Desktop 的工具集（Playwright）。两者使用不同的技术方案，服务于不同的场景。

**Q4: 如果 Telegram 更新了前端，DOM 选择器失效怎么办？**
> 需要人工更新选择器。这是 Playwright 方案的固有限制。长期来看，建议添加选择器版本管理（TODO.md 中 P0 任务）。

**Q5: 这个项目能部署到服务器吗？**
> 可以，但有限制：
> - 需要图形环境（Chromium 需要 X11 或 xvfb）
> - 需要提前在有头模式下登录，保存状态
> - 建议使用 Docker（TODO.md 中 P2 任务）

---

*文档版本: v1.0 | 对应代码版本: v2.3.0*
