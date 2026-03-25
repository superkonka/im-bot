#!/usr/bin/env python3
"""
WhatsApp Web 平台适配
"""
from .base import BasePlatform, PlatformConfig
from ..config import get_platform_settings


class WhatsAppPlatform(BasePlatform):
    """WhatsApp Web 平台"""
    
    def _get_config(self) -> PlatformConfig:
        platform_settings = get_platform_settings("whatsapp")
        return PlatformConfig(
            name=platform_settings.get("name", "WhatsApp Web"),
            url=platform_settings.get("url", "https://web.whatsapp.com"),
            login_method=platform_settings.get("login_method", "qr_code"),
            login_wait=platform_settings.get("login_wait", 30),
            selectors=platform_settings.get("selectors", {
                "chat_list": "[data-testid='chat-list']",
                "chat_item": "[data-testid='cell-frame-container']",
                "unread_badge": "[data-testid='icon-unread-count']",
                "message_input": "[data-testid='conversation-compose-box-input']",
                "send_button": "[data-testid='send']",
                "message_bubble": "[data-testid='msg-container']",
            }),
            tips=platform_settings.get("tips", [
                "WhatsApp 需要手机扫码登录，首次使用请准备好手机",
                "未读消息通常显示绿色数字角标",
                "聊天列表在左侧，消息区域在右侧",
                "输入框在页面底部",
            ])
        )
    
    def get_system_prompt(self) -> str:
        return """你是 WhatsApp Web 机器人助手。通过分析页面截图，控制浏览器完成 IM 任务。

## WhatsApp Web 界面特点
- **左侧**: 聊天列表，显示联系人/群组头像和最后一条消息预览
- **右侧**: 当前聊天窗口，显示历史消息（从上到下按时间顺序）
- **底部**: 消息输入框（带表情/附件按钮）
- **未读标记**: 绿色数字角标（如"1"、"2"），显示在聊天列表右侧

## 操作流程
1. **检查登录状态**: 如果看到二维码或"用手机扫描二维码"，需要等待
2. **扫描聊天列表**: 查找带绿色数字角标的聊天（未读消息）
3. **进入聊天**: 点击有未读消息的聊天项
4. **读取消息**: 查看右侧消息区域的最底部消息（最新消息）
5. **回复消息**: 
   - 点击底部输入框（通常是页面最底部）
   - 输入回复内容
   - 点击发送按钮（绿色箭头图标）
   - 等待消息发送成功（出现对勾标记）
6. **返回列表**: 点击左侧聊天列表，准备处理下一个未读消息

## 可用操作
- `open {"url": "..."}` - 打开网页
- `click {"index": N}` - 点击第 N 个元素（从 state 获取索引）
- `input {"index": N, "text": "..."}` - 点击输入框并输入文本
- `type {"text": "..."}` - 直接输入文本（需先聚焦）
- `state {}` - 获取可交互元素列表
- `wait {"seconds": N}` - 等待 N 秒
- `done {}` - 任务完成

## 回复策略
根据用户消息内容智能回复：

**问候类**:
- "你好"/"您好"/"Hi"/"Hello" → "你好！我是智能助手，有什么可以帮您的吗？😊"
- "在吗"/"在吗？" → "在的，有什么可以帮您？"

**帮助类**:
- "帮助"/"help" → "我可以帮您：1.查询信息 2.发送提醒 3.回答问题"
- "能做什么" → "我可以：回答问题、提供信息、提醒事项"

**结束类**:
- "谢谢"/"Thanks"/"Thx" → "不客气！有问题随时找我 👍"
- "再见"/"拜拜"/"Bye" → "再见！祝您有愉快的一天！👋"

**时间相关**:
- "几点了"/"现在时间" → 返回当前时间

**其他**:
- 具体问题 → 根据上下文提供有帮助的回复
- 不清楚的问题 → "抱歉，我可能需要更多信息来回答这个问题"

## 重要提示
- WhatsApp 需要手机保持连接才能使用网页版
- 二维码有效期约 20 秒，过期后页面会自动刷新
- 发送按钮是绿色的箭头图标（►）
- 操作后等待 2-3 秒让页面响应
- 如果找不到输入框，先使用 state 命令获取元素列表

返回 JSON 格式: {"action": "...", "params": {...}, "reason": "...", "confidence": 0.95}"""
    
    def generate_reply(self, message: str) -> str:
        """生成回复"""
        msg_lower = message.lower().strip()
        
        # 问候
        if any(kw in msg_lower for kw in ['你好', '您好', 'hi', 'hello', 'hey']):
            return "你好！我是智能助手，有什么可以帮您的吗？😊"
        
        if '在吗' in msg_lower:
            return "在的，有什么可以帮您？"
        
        # 帮助
        if any(kw in msg_lower for kw in ['帮助', 'help', '能做什么', '功能']):
            return "我可以帮您：\n1. 回答问题\n2. 提供信息\n3. 发送提醒\n请告诉我您需要什么帮助？"
        
        # 感谢
        if any(kw in msg_lower for kw in ['谢谢', 'thanks', 'thx', 'thank you']):
            return "不客气！有问题随时找我 👍"
        
        # 再见
        if any(kw in msg_lower for kw in ['再见', '拜拜', 'bye', 'goodbye']):
            return "再见！祝您有愉快的一天！👋"
        
        # 时间
        if any(kw in msg_lower for kw in ['几点', '时间', '现在']):
            from datetime import datetime
            return f"现在是 {datetime.now().strftime('%H:%M')}"
        
        # 默认回复
        return "收到您的消息了！我正在学习中，会尽快为您提供帮助。"
