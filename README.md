# 🤖 Kimi 视觉驱动 IM 机器人 v1.1

利用 Kimi LLM 的视觉能力，让 AI 自主控制浏览器完成 **WhatsApp Web** 和 **Telegram Web** 的消息监控与自动回复。

## ✨ 核心特性

| 特性 | 说明 |
|-----|------|
| 🔮 **纯视觉驱动** | Kimi 直接分析截图决策，无需解析 DOM |
| 📱 **双平台支持** | WhatsApp Web + Telegram Web |
| 🧠 **智能回复** | 内置常用回复策略，支持自定义 |
| 🔒 **安全登录** | 二维码/手机号登录，人工确认 |
| 📊 **完整日志** | 彩色控制台 + 文件日志 + 截图记录 |
| 🧩 **模块化架构** | 易于扩展更多平台 |

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

### 3. 安装 Browser Use CLI

```bash
# macOS / Linux
curl -fsSL https://browser-use.com/cli/install.sh | bash

# 验证
browser-use doctor
```

### 4. 配置 API Key

```bash
# 临时设置
export KIMI_API_KEY="sk-your-kimi-api-key"

# 永久设置 (推荐)
echo 'export KIMI_API_KEY=sk-your-api-key' >> ~/.zshrc  # 或 ~/.bashrc
source ~/.zshrc
```

获取 API Key: https://platform.moonshot.cn/

---

## 🚀 快速开始

### 方式一：交互式启动（推荐）

```bash
python run.py
```

按提示选择平台、配置参数。

### 方式二：命令行启动

```bash
# WhatsApp
python main.py whatsapp

# Telegram
python main.py telegram

# 高级配置
python main.py whatsapp --steps 200 --delay 5 --debug
```

### 方式三：Python 代码

```python
from src.im_bot import IMBot

bot = IMBot(platform='whatsapp', max_steps=100, step_delay=3)
bot.start()
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

### Telegram Web

**登录方式**: 手机号 + 验证码

1. 启动后浏览器打开 web.telegram.org/k/
2. **输入手机号** → 接收验证码 → 输入验证码
3. 登录成功后开始监控

**界面特点**:
- 左侧：聊天列表，带蓝色未读角标
- 右侧：消息区域
- 底部：输入框 + 纸飞机发送按钮

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
│   ├── browser_controller.py  # 浏览器控制
│   ├── vision_agent.py     # Kimi 视觉分析
│   │
│   ├── platforms/          # 平台适配
│   │   ├── __init__.py
│   │   ├── base.py         # 基类
│   │   ├── whatsapp.py     # WhatsApp 适配
│   │   └── telegram.py     # Telegram 适配
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

### 环境变量

| 变量 | 说明 | 必需 |
|-----|------|-----|
| `KIMI_API_KEY` | Moonshot API Key | ✅ |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO) | ❌ |
| `BROWSER_HEADLESS` | 无头模式 | ❌ |

---

## 🔧 自定义回复

编辑 `src/platforms/whatsapp.py` 或 `src/platforms/telegram.py` 中的 `generate_reply` 方法：

```python
def generate_reply(self, message: str) -> str:
    msg_lower = message.lower()
    
    # 自定义关键词回复
    if "价格" in msg_lower:
        return "请咨询官方客服获取最新价格 💰"
    
    if "投诉" in msg_lower:
        return "非常抱歉，请提供订单号，我帮您处理 🙏"
    
    # 默认回复
    return "收到您的消息！"
```

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

1. **首次使用需要登录** - 机器人会等待你完成扫码/验证码
2. **保持手机连接** - WhatsApp 需要手机在线
3. **网络环境** - Telegram 可能需要科学上网
4. **API 额度** - 注意 Kimi API 余额

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

### 登录失败？
- WhatsApp: 确保手机网络正常
- Telegram: 检查是否能正常接收验证码

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
