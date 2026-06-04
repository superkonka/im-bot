# Telegram Skill

基于 [Telethon](https://github.com/LonamiWebs/Telethon) (MTProto) 的 Telegram 对话能力封装。

## 与现有 `src/platforms/telegram.py` 的区别

| 维度 | `platforms/telegram.py` (旧) | `skills/telegram/` (新) |
|------|-----------------------------|------------------------|
| 协议 | 浏览器自动化 (Playwright) | MTProto 原生协议 |
| 稳定性 | 依赖 DOM，易失效 | 协议层，稳定可靠 |
| 延迟 | 高（截图+视觉分析） | 低（原生 API） |
| 资源占用 | 高（完整浏览器） | 低（纯 Python） |
| 适用场景 | 快速原型、无 API 依赖 | 生产环境、7×24 运行 |

## 快速开始

### 1. 获取 API 凭证

访问 https://my.telegram.org/apps 创建应用，获得：
- `api_id` (整数)
- `api_hash` (字符串)

### 2. 环境变量配置

```bash
export TELEGRAM_API_ID=12345678
export TELEGRAM_API_HASH="your_api_hash_here"
export TELEGRAM_PHONE="+8613800138000"
```

### 3. 运行示例

```bash
python -m src.skills.telegram.demo
```

首次运行会要求输入验证码，Session 会自动保存在 `data/telegram_sessions/`。

## 核心接口

### 启动与停止

```python
skill = TelegramSkill(session_name="my_bot")

await skill.start(
    api_id=API_ID,
    api_hash=API_HASH,
    phone="+8613800138000",
    code_callback=lambda: input("验证码: "),
)

# ... 使用 skill ...

await skill.stop()
```

### 监听新消息

```python
async def handle_new_message(event: MessageEvent):
    print(f"[{event.chat.display_name}] {event.sender.display_name}: {event.message.text}")
    # Agent 决策逻辑在这里...

skill.on_new_message(handle_new_message)
```

### 发送消息

```python
result = await skill.send_message(
    chat_id=123456789,
    text="你好！👋",
    reply_to=msg_id,  # 可选：引用回复
)
```

### 获取聊天列表

```python
# 所有聊天
chats = await skill.list_chats(limit=50)

# 仅未读
unread = await skill.list_chats(unread_only=True)
```

### 获取历史消息

```python
messages = await skill.get_messages(chat_id=123456789, limit=20)
for msg in messages:
    print(f"{msg.sender_id}: {msg.text}")
```

## 数据类型

### MessageEvent（Agent 消费的核心对象）

```python
@dataclass
class MessageEvent:
    message: Message      # 消息内容
    chat: ChatInfo        # 聊天信息
    sender: UserProfile   # 发送者资料
    is_mention: bool      # 是否在群聊中被 @
    is_first_contact: bool # 是否首次联系
    session_context: dict # 会话级上下文（Agent 维护）
```

### 媒体识别

Skill 会自动识别消息中的媒体类型：
- `MediaType.PHOTO` / `VIDEO` / `AUDIO`
- `MediaType.VOICE`（语音消息）
- `MediaType.DOCUMENT` / `STICKER`
- `MediaType.LOCATION` / `CONTACT` / `POLL`

## 架构位置

```
Agent Layer (Multi-Agent 编排)
       │
       ▼
  Skill Layer (TelegramSkill)
       │
       ▼
 SessionManager (Telethon Client)
       │
       ▼
  Telegram MTProto Server
```

## 注意事项

1. **合规风险**：Telegram ToS 禁止自动化个人账号。请评估封号风险。
2. **频率限制**：Telethon 内部有自动限流，但仍建议控制回复频率。
3. **Session 安全**：`.session` 文件包含登录凭证，请勿提交到 Git。
4. **两步验证**：如果账号开启 2FA，需要提供 `password_callback`。
