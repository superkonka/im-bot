#!/usr/bin/env python3
"""
Telegram Web 平台适配
"""
from .base import BasePlatform, PlatformConfig
from ..config import get_platform_settings


class TelegramPlatform(BasePlatform):
    """Telegram Web 平台"""
    
    def _get_config(self) -> PlatformConfig:
        platform_settings = get_platform_settings("telegram")
        return PlatformConfig(
            name=platform_settings.get("name", "Telegram Web"),
            url=platform_settings.get("url", "https://web.telegram.org/k/"),
            login_method=platform_settings.get("login_method", "phone_code"),
            login_wait=platform_settings.get("login_wait", 60),
            selectors=platform_settings.get("selectors", {
                "chat_list": ".chat-list",
                "chat_item": ".chat",
                "unread_badge": ".badge.unread",
                "search_input": "input[type='text']",
                "message_input": ".composer-input",
                "send_button": ".btn-icon.send",
                "message_bubble": ".message",
            }),
            tips=platform_settings.get("tips", [
                "Telegram 可以使用手机号+验证码登录",
                "未读消息显示蓝色数字角标",
                "左侧是聊天列表，右侧是消息区域",
                "K 版本 (web.telegram.org/k/) 比 A 版更稳定",
            ])
        )
    
    def get_system_prompt(self) -> str:
        return """你是 Telegram Web 机器人助手。通过分析页面截图，控制浏览器完成 IM 任务。

## Telegram Web (K版) 界面特点
- **左侧**: 聊天列表，显示对话名称、最后一条消息预览、未读数
- **右侧**: 消息区域，显示历史消息气泡（底部是最新消息）
- **底部**: 消息输入框（带贴纸、附件、语音按钮）
- **未读标记**: 蓝色数字角标，显示在聊天列表右侧
- **登录界面**: 可能看到"Log in to Telegram"或"Start Messaging"

## 操作流程
1. **检查登录状态**: 如果看到登录界面（手机号输入框），需要等待用户输入
2. **扫描聊天列表**: 查找带蓝色数字角标的聊天（未读消息）
3. **进入聊天**: 点击有未读消息的聊天项
4. **读取消息**: 查看右侧消息区域的最底部消息（最新消息）
5. **回复消息**:
   - 点击底部输入框
   - 输入回复内容（支持 Markdown 格式）
   - 点击发送按钮（纸飞机图标 ✈️）
6. **返回列表**: 点击左侧聊天列表，继续监控其他聊天

## 可用操作
- `open {"url": "https://web.telegram.org/k/"}` - 打开 Telegram Web
- `click {"index": N}` - 点击第 N 个元素
- `input {"index": N, "text": "..."}` - 点击输入框并输入文本
- `type {"text": "..."}` - 直接输入文本
- `state {}` - 获取可交互元素列表
- `wait {"seconds": N}` - 等待
- `done {}` - 任务完成

## 回复策略

**命令类**:
- `/start` → "欢迎使用 Telegram 机器人！🤖\n我可以帮您回答问题、提供信息。"
- `/help` → "可用命令：\n/start - 开始对话\n/help - 获取帮助"

**问候类**:
- "你好"/"您好"/"Hi" → "你好！我是您的 Telegram 助手 🤖"
- "在吗" → "在的！随时为您服务"

**帮助类**:
- "帮助" → "我可以：回答问题、提供信息、发送提醒"

**结束类**:
- "谢谢" → "不客气！😊"
- "再见" → "再见！随时找我聊天 👋"

**特色回复**（Telegram 支持 Markdown）:
- 可以用 **粗体**、_斜体_、`代码块`
- 可以使用表情符号 🎉👍😊

**其他**:
- 具体问题 → 根据上下文智能回复
- 不清楚 → "请提供更多细节，我会尽力帮助您"

## 注意事项
- Telegram Web K 版在国内可能需要科学上网
- 发送按钮是纸飞机图标（✈️）
- 支持群组聊天，可以考虑是否需要 @提及 才回复
- 操作后等待 2-3 秒让页面响应

返回 JSON 格式: {"action": "...", "params": {...}, "reason": "...", "confidence": 0.95}"""
    
    def generate_reply(self, message: str) -> str:
        """生成回复"""
        msg_lower = message.lower().strip()
        
        # 命令
        if msg_lower == '/start':
            return "欢迎使用 Telegram 机器人！🤖\n我可以帮您回答问题、提供信息。"
        
        if msg_lower == '/help':
            return "**可用命令：**\n/start - 开始对话\n/help - 获取帮助\n\n直接发送消息与我聊天！"
        
        # 问候
        if any(kw in msg_lower for kw in ['你好', '您好', 'hi', 'hello']):
            return "你好！我是您的 Telegram 助手 🤖"
        
        if '在吗' in msg_lower:
            return "在的！随时为您服务 💬"
        
        # 帮助
        if any(kw in msg_lower for kw in ['帮助', 'help']):
            return "我可以帮您：\n• 回答问题\n• 提供信息\n• 发送提醒\n\n直接告诉我就行！"
        
        # 感谢
        if any(kw in msg_lower for kw in ['谢谢', 'thanks', 'thx']):
            return "不客气！😊"
        
        # 再见
        if any(kw in msg_lower for kw in ['再见', '拜拜', 'bye']):
            return "再见！随时找我聊天 👋"
        
        # 时间
        if any(kw in msg_lower for kw in ['几点', '时间']):
            from datetime import datetime
            return f"现在是 **{datetime.now().strftime('%H:%M')}** ⏰"
        
        # 默认回复
        return "收到！我正在处理您的消息 📩"
