#!/usr/bin/env python3
"""
Kimi 视觉驱动浏览器 IM 机器人
利用 Kimi 读取截图，自主决定浏览器操作
"""

import os
import base64
import json
import time
import subprocess
from pathlib import Path
from openai import OpenAI

# ============== 配置 ==============
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "your-api-key-here")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
IM_URL = "https://im.example.com"  # 替换为你的 IM 网页地址
SCREENSHOT_DIR = Path("./screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# 初始化 Kimi 客户端
client = OpenAI(api_key=KIMI_API_KEY, base_url=KIMI_BASE_URL)

# ============== Browser Use CLI 操作封装 ==============

def browser_command(cmd: str) -> str:
    """执行 browser-use CLI 命令"""
    try:
        result = subprocess.run(
            f"browser-use {cmd}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error: {e}"

def take_screenshot(filename: str = "current.png") -> str:
    """截图并返回文件路径"""
    filepath = SCREENSHOT_DIR / filename
    result = browser_command(f"screenshot {filepath}")
    print(f"[截图] {result}")
    return str(filepath)

def get_page_state() -> str:
    """获取页面可交互元素列表"""
    return browser_command("state")

def click_element(index: int) -> str:
    """点击指定索引的元素"""
    return browser_command(f"click {index}")

def type_text(text: str) -> str:
    """在当前焦点元素输入文本"""
    # 注意：browser-use 的 type 命令可能需要先点击输入框
    return browser_command(f'type "{text}"')

def input_to_element(index: int, text: str) -> str:
    """点击元素并输入文本"""
    return browser_command(f'input {index} "{text}"')

def open_url(url: str) -> str:
    """打开网页"""
    return browser_command(f"open {url}")

def close_browser() -> str:
    """关闭浏览器"""
    return browser_command("close")

# ============== Kimi 视觉分析 ==============

def encode_image(image_path: str) -> str:
    """将图片转为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def ask_kimi_to_act(screenshot_path: str, context: list, system_prompt: str) -> dict:
    """
    让 Kimi 分析截图并决定下一步操作
    
    返回格式: {"action": "click|type|wait|done", "params": {}, "reasoning": "..."}
    """
    base64_image = encode_image(screenshot_path)
    
    messages = [
        {"role": "system", "content": system_prompt},
        *context,
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这是当前网页截图，请分析并决定下一步操作。返回 JSON 格式：{\"action\": \"click|type|input|open|wait|done\", \"params\": {...}, \"reasoning\": \"...\"}"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]
    
    try:
        response = client.chat.completions.create(
            model="moonshot-v1-32k-vision-preview",  # 使用支持视觉的模型
            messages=messages,
            temperature=0.1,
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        
        # 提取 JSON（Kimi 可能会用 markdown 代码块包裹）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        return json.loads(content.strip())
    except Exception as e:
        print(f"[Kimi 错误] {e}")
        return {"action": "wait", "params": {"seconds": 3}, "reasoning": f"Error: {e}"}

# ============== IM 机器人系统提示词 ==============

IM_BOT_PROMPT = """你是一个网页 IM 机器人助手。你的任务是通过控制浏览器来完成 IM 聊天任务。

## 可用操作
1. `open` - 打开网页，params: {"url": "..."}
2. `click` - 点击元素，params: {"index": 数字}（需先用 state 获取元素索引）
3. `type` - 在当前焦点输入文本，params: {"text": "..."}
4. `input` - 点击输入框并输入文本，params: {"index": 数字, "text": "..."}
5. `state` - 获取页面可交互元素列表
6. `screenshot` - 截图（一般不需要主动调用）
7. `wait` - 等待，params: {"seconds": 数字}
8. `done` - 任务完成

## IM 机器人任务流程
1. 打开 IM 网页
2. 检查是否已登录，如未登录提示用户手动登录（等待）
3. 进入指定聊天窗口
4. **循环监控新消息**:
   - 查看聊天列表，检查未读消息
   - 点击有未读消息的会话
   - 读取最新消息内容
   - 根据消息内容决定回复
   - 发送回复
   - 返回聊天列表继续监控

## 回复策略
- "你好"/"您好" → "你好！我是 AI 助手，有什么可以帮你的吗？"
- "帮助"/"help" → "我可以帮您：1.查信息 2.提醒事项 3.回答问题"
- "谢谢" → "不客气！有其他问题随时找我"
- 其他问题 → 根据上下文智能回复

## 重要提示
- 每次操作后截图会更新，根据新截图决定下一步
- 如果页面加载中，请等待
- 如果遇到验证码或登录，返回 wait 让人工处理
- 操作后等待页面响应（2-3秒）

请分析当前截图，返回下一步操作 JSON。"""

# ============== 主循环 ==============

def main():
    print("=" * 50)
    print("🤖 Kimi 视觉驱动 IM 机器人启动")
    print("=" * 50)
    
    # 对话上下文
    context = []
    step = 0
    max_steps = 100  # 防止无限循环
    
    # 初始状态：打开 IM 网页
    print(f"\n[步骤 {step}] 打开 IM 网页...")
    open_url(IM_URL)
    time.sleep(3)
    
    while step < max_steps:
        step += 1
        print(f"\n{'='*50}")
        print(f"[步骤 {step}]")
        
        # 1. 截图当前状态
        screenshot_path = take_screenshot(f"step_{step:03d}.png")
        
        # 2. 获取页面元素状态（可选，帮助 Kimi 决策）
        page_state = get_page_state()
        print(f"[页面状态] {page_state[:500]}...")  # 打印前500字符
        
        # 3. 让 Kimi 决定操作
        action_result = ask_kimi_to_act(screenshot_path, context, IM_BOT_PROMPT)
        
        print(f"[Kimi 决策] {action_result}")
        
        action = action_result.get("action", "wait")
        params = action_result.get("params", {})
        reasoning = action_result.get("reasoning", "")
        
        # 更新上下文
        context.append({"role": "user", "content": f"步骤 {step} 截图已发送"})
        context.append({"role": "assistant", "content": json.dumps(action_result, ensure_ascii=False)})
        
        # 限制上下文长度
        if len(context) > 20:
            context = context[-20:]
        
        # 4. 执行操作
        if action == "done":
            print("[任务完成]")
            break
            
        elif action == "wait":
            seconds = params.get("seconds", 3)
            print(f"[等待 {seconds} 秒...]")
            time.sleep(seconds)
            
        elif action == "open":
            url = params.get("url", IM_URL)
            result = open_url(url)
            print(f"[打开网页] {result}")
            time.sleep(3)
            
        elif action == "click":
            index = params.get("index", 1)
            result = click_element(index)
            print(f"[点击元素 {index}] {result}")
            time.sleep(2)
            
        elif action == "type":
            text = params.get("text", "")
            result = type_text(text)
            print(f"[输入文本] {result}")
            time.sleep(1)
            
        elif action == "input":
            index = params.get("index", 1)
            text = params.get("text", "")
            result = input_to_element(index, text)
            print(f"[输入到元素 {index}] {result}")
            time.sleep(1)
            
        elif action == "state":
            result = get_page_state()
            print(f"[获取页面状态] {result}")
            
        else:
            print(f"[未知操作] {action}")
            time.sleep(3)
    
    print("\n" + "=" * 50)
    print("机器人运行结束")
    print("=" * 50)

if __name__ == "__main__":
    main()
