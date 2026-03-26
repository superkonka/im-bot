# 🤖 IM Bot

当前项目已经形成两条不同能力路径：

- `Telegram`：主路径，基于 `Telethon` 登录用户自己的账号，围绕指定聊天对象做受控的长期对话
- `WhatsApp Web`：保留的浏览器视觉实验路径，适合继续验证 Web 自动化场景

## ✨ 核心特性

| 特性 | 说明 |
|-----|------|
| 🤖 **Telegram 用户账号模式** | 用户登录自己的 Telegram 账号，而不是官方 Bot |
| 🧠 **受控 LLM 对话** | 回复和主动发起都结合人设、聊天历史、时间语义 |
| 🛡️ **双层安全约束** | 白名单话题、黑名单、发送前二次审核、主动频率限制 |
| 🧠 **长期记忆骨架** | 保存关系摘要、重要事实、未完话题、近期主题 |
| 📊 **完整日志** | 彩色控制台 + 文件日志 + 会话状态持久化 |
| 🧪 **Web 视觉实验路径** | 旧的 WhatsApp/Telegram Web 自动化仍可作为实验保留 |

---

## 📦 安装

### 1. 克隆/下载项目

```bash
cd /Users/konkapeng/im_bot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. Telegram 用户账号模式额外依赖

如果你主要使用 Telegram 用户账号模式，只需要 `requirements.txt` 中的 Python 依赖即可。

### 4. Browser Use CLI（仅 WhatsApp Web / 旧版 Telegram Web 需要）

```bash
# macOS / Linux
curl -fsSL https://browser-use.com/cli/install.sh | bash

# 验证
browser-use doctor
```

### 5. 配置 API Key

```bash
# 临时设置
export KIMI_API_KEY="sk-your-kimi-api-key"

# 永久设置 (推荐)
echo 'export KIMI_API_KEY=sk-your-api-key' >> ~/.zshrc  # 或 ~/.bashrc
source ~/.zshrc
```

获取 API Key: https://platform.moonshot.cn/

### 6. Telegram 用户账号模式所需凭据

需要从 Telegram 开发者平台获取：

```bash
export TELEGRAM_API_ID="your-api-id"
export TELEGRAM_API_HASH="your-api-hash"
```

也可以通过 `python config_center.py` 或交互式启动时按提示写入配置。

---

## 🚀 快速开始

### 方式一：交互式启动（推荐）

```bash
python run.py
```

按提示选择平台、配置参数。
如果选择 Telegram，默认会走用户账号模式，并在缺少配置时提示补齐 `API ID / API Hash / target_chat / persona`。

### 方式二：命令行启动

```bash
# WhatsApp
python main.py whatsapp

# Telegram 用户账号模式（推荐）
python main.py telegram --transport user

# Telegram 旧版 Web 实验路径
python main.py telegram --transport web

# 高级配置
python main.py whatsapp --steps 200 --delay 5 --debug
```

### 方式三：Python 代码

```python
from src.telegram_userbot import TelegramUserBot

bot = TelegramUserBot()
bot.run()
```

---

## 📱 平台使用指南

### WhatsApp Web

**登录方式**: 手机扫码

1. 启动后浏览器自动打开 web.whatsapp.com
2. **使用手机 WhatsApp 扫描二维码**
3. 扫码成功后机器人自动开始工作

**界面特点**:
- 左侧：聊天列表，带绿色未读角标
- 右侧：消息区域
- 底部：输入框 + 绿色发送按钮

### Telegram 用户账号模式

**登录方式**: 用户自己的 Telegram 账号 + Telethon session

1. 启动 `python run.py` 或 `python main.py telegram --transport user`
2. 首次运行时补齐 `TELEGRAM_API_ID`、`TELEGRAM_API_HASH`、`target_chat`、人设和允许话题
3. Telethon 会在终端中提示输入验证码；如果账号开启了二次密码，也会继续提示
4. 登录成功后，session 会保存在 `data/telegram_sessions/`
5. 机器人只监听指定聊天对象，并根据策略做被动回复和有限度的主动发起

**运行特点**:
- 不依赖浏览器截图来收发 Telegram 消息
- 会结合最近聊天记录、长期记忆和当前时间做决策
- 消息在真正发出前还会再过一次审核
- `target_chat` 支持用户名、ID，交互式启动时也可以尝试从最近聊天列表里选

### Telegram Web（旧实验路径）

仍可通过 `--transport web` 启动，但它是旧的视觉自动化路径，不再是推荐主方案。

---

## 📁 项目结构

```
im_bot/
├── main.py                  # 命令行入口
├── run.py                   # 交互式入口 ⭐推荐
├── requirements.txt         # 依赖
├── README.md               # 本文档
│
├── src/                    # 核心源码
│   ├── __init__.py
│   ├── config.py           # 全局配置
│   ├── im_bot.py           # 机器人主类
│   ├── launcher.py         # 统一启动分发
│   ├── telegram_userbot.py # Telegram 用户账号主链路
│   ├── browser_controller.py  # 浏览器控制
│   ├── vision_agent.py     # Kimi 视觉分析
│   │
│   ├── platforms/          # 平台适配
│   │   ├── __init__.py
│   │   ├── base.py         # 基类
│   │   ├── whatsapp.py     # WhatsApp 适配
│   │   └── telegram.py     # Telegram Web 适配（旧路径）
│   │
│   └── utils/              # 工具
│       ├── __init__.py
│       ├── logger.py       # 日志
│       └── helpers.py      # 辅助函数
│
├── tests/                  # 测试
│   ├── test_vision_agent.py
│   └── test_platforms.py
│
└── screenshots/            # 截图保存 (自动生成)
    └── logs/               # 日志文件
```

---

## ⚙️ 配置参数

### 命令行参数

| 参数 | 说明 | 默认值 |
|-----|------|-------|
| `platform` | 平台: whatsapp/telegram | - |
| `--steps` | 最大运行步数 | 500 |
| `--delay` | 每步间隔(秒) | 3 |
| `--headless` | 无头模式 | False |
| `--debug` | 调试日志 | False |
| `--transport` | Telegram: auto/user/web | auto |

### 环境变量

| 变量 | 说明 | 必需 |
|-----|------|-----|
| `KIMI_API_KEY` | Moonshot API Key | ✅ |
| `TELEGRAM_API_ID` | Telegram 用户账号 API ID | Telegram 用户模式必需 |
| `TELEGRAM_API_HASH` | Telegram 用户账号 API Hash | Telegram 用户模式必需 |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO) | ❌ |
| `BROWSER_HEADLESS` | 无头模式 | ❌ |

---

## 🔧 Telegram 用户账号模式怎么调

优先修改配置里的这些字段：

- `telegram_user.persona`
- `telegram_user.relationship_context`
- `telegram_user.response_style`
- `telegram_user.allowed_topics`
- `telegram_user.blocked_topics`
- `telegram_user.proactive`
- `telegram_user.safety_review`

如果只是想先观察效果，可以把 `telegram_user.dry_run` 设为 `true`，这样只会打印拟发送内容，不会真正发消息。

---

## ✅ 视觉用例校验

除了让 Kimi 决策下一步操作，也可以把它当成“视觉验收器”使用:

```python
from src.vision_agent import KimiVisionAgent
from src.use_cases import UseCaseDefinition

agent = KimiVisionAgent()

use_case = UseCaseDefinition(
    case_id="login_whatsapp",
    name="WhatsApp 登录完成",
    objective="确认用户已成功进入聊天主界面",
    pass_criteria=[
        "左侧出现聊天列表",
        "右侧出现消息区域",
        "底部出现消息输入框",
    ],
    fail_criteria=[
        "页面仍显示二维码",
        "出现登录失败或网络错误提示",
    ],
    allowed_next_actions=["proceed", "review", "retry"],
    step_name="post_login",
)

result = agent.validate_use_case(
    screenshot_path="screenshots/login_check.png",
    use_case=use_case,
)

print(result.to_dict())
```

典型返回:

```json
{
  "case_id": "login_whatsapp",
  "step_name": "post_login",
  "status": "pass",
  "confidence": 0.92,
  "matched_rules": ["左侧出现聊天列表", "底部出现消息输入框"],
  "failed_rules": [],
  "evidence": ["截图左侧有联系人列表", "底部可见消息输入区域"],
  "reason": "主聊天界面已经加载完成",
  "next_action": "proceed"
}
```

---

## 🧪 运行测试

```bash
# 运行所有测试
python -m unittest discover tests/

# 单独测试
python -m unittest tests.test_platforms
python -m unittest tests.test_vision_agent
```

---

## 🔍 工作原理

### Telegram 用户账号主链路

```
┌─────────────────────────────────────────────────────────────┐
│                    TelegramUserBot                         │
│                                                             │
│  Telethon 监听目标聊天  ──▶ 串行任务队列 ──▶ LLM 决策        │
│                                            │                │
│                                            ▼                │
│                                      长期记忆/策略守卫      │
│                                            │                │
│                                            ▼                │
│                                      发送前二次审核         │
│                                            │                │
│                                            ▼                │
│                                       send_message          │
└─────────────────────────────────────────────────────────────┘
```

### 旧版 Web 视觉路径

```
┌──────────────────────────────────────────────────────┐
│                    主循环 (IMBot)                     │
│                                                      │
│   ┌──────────────┐                                   │
│   │  Browser     │───打开网页────────────────────▶   │
│   │  Controller  │◀──等待登录────────────────────│   │
│   └──────┬───────┘                                   │
│          │                                           │
│          ▼                                           │
│   ┌──────────────┐     ┌──────────────┐             │
│   │  截图当前页  │────▶│ Kimi Vision  │             │
│   │  Screenshot  │     │   Agent      │             │
│   └──────────────┘     └──────┬───────┘             │
│                               │                      │
│                               ▼                      │
│   ┌──────────────┐     ┌──────────────┐             │
│   │  执行操作    │◀────│  分析+决策   │             │
│   │   Execute    │     │   Decide     │             │
│   └──────┬───────┘     └──────────────┘             │
│          │                                           │
│          └───────────────────────────────────────────┘
```

---

## 💰 费用说明

| 项目 | 费用 | 备注 |
|-----|------|-----|
| Kimi API | ~¥0.01-0.02/次 | 视觉模型按图片尺寸计费 |
| Browser Use | 免费 | 开源工具 |
| 估算 | ¥5-10/500步 | 取决于截图复杂度 |

---

## ⚠️ 注意事项

1. **Telegram 用户模式不是官方 Bot** - 它会登录你的真实账号，请务必谨慎设置允许话题和主动频率
2. **首次登录需要验证码** - Telethon 会在终端里提示输入
3. **WhatsApp 旧路径仍需手机连接** - 如果使用 Web 视觉方案，请保持手机在线
4. **网络环境** - Telegram 连接可能受网络环境影响
5. **API 额度** - 注意 Kimi API 余额

---

## 🛠️ 故障排查

### 浏览器打不开？
```bash
browser-use doctor
browser-use open https://www.google.com  # 测试
```

### Kimi API 错误？
- 检查 `KIMI_API_KEY` 是否设置
- 确认 API Key 有余额

### Telegram 用户模式登录失败？
- 检查 `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` 是否正确
- 确认终端里能正常输入验证码或二次密码
- 删除 `data/telegram_sessions/<session_name>*` 后重新登录

### 找不到目标聊天？
- 优先使用用户名或数值 ID
- 交互式启动时可尝试读取最近聊天列表后按编号选择
- 如果名称有歧义，程序会提示候选项

---

## 📝 更新日志

### v1.1.0 (2025-03)
- ✅ 重构为模块化架构
- ✅ 统一平台适配接口
- ✅ 改进视觉分析逻辑
- ✅ 优化日志系统

### v1.0.0 (2025-03)
- ✅ 初始版本
- ✅ WhatsApp + Telegram 支持

---

## 🤝 扩展更多平台

参考 `src/platforms/base.py` 和现有实现，添加新平台：

```python
# src/platforms/dingtalk.py
from .base import BasePlatform, PlatformConfig

class DingTalkPlatform(BasePlatform):
    def _get_config(self) -> PlatformConfig:
        return PlatformConfig(
            name="钉钉",
            url="https://im.dingtalk.com",
            login_method="qr_code",
            ...
        )
    
    def get_system_prompt(self) -> str:
        return "..."
```

---

**需要 API Key 进行测试？请提供你的 Kimi API Key，我来运行完整测试！** 🔑
