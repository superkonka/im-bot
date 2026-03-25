#!/usr/bin/env python3
"""
简化版 Kimi 视觉驱动 IM 机器人
适合快速上手使用
"""

import os
import base64
import json
import time
import subprocess
from pathlib import Path
from openai import OpenAI

# ============ 配置区 ============
KIMI_API_KEY = os.getenv("KIMI_API_KEY")  # 从环境变量读取
IM_URL = "https://web.yy.com"  # 修改为你的 IM 网页地址
MAX_STEPS = 200  # 最大运行步数
STEP_DELAY = 2   # 每步延迟（秒）
# ================================

client = OpenAI(api_key=KIMI_API_KEY, base_url="https://api.moonshot.cn/v1")
Path("screenshots").mkdir(exist_ok=True)

def run_cmd(cmd):
    """执行 browser-use 命令"""
    result = subprocess.run(f"browser-use {cmd}", shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def screenshot(step):
    """截图"""
    path = f"screenshots/step_{step:03d}.png"
    run_cmd(f"screenshot {path}")
    return path

def encode_img(path):
    """图片转 base64"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def kimi_decide(img_path, history):
    """让 Kimi 决定下一步"""
    base64_img = encode_img(img_path)
    
    system_msg = """你是网页 IM 机器人。分析截图，决定浏览器操作。
可用操作：
- open {"url": "..."} - 打开网页
- click {"index": N} - 点击第 N 个元素（从 state 获取）
- input {"index": N, "text": "..."} - 在输入框输入文本
- type {"text": "..."} - 直接输入（需先聚焦）
- state {} - 获取可交互元素列表
- wait {"seconds": N} - 等待
- done {} - 任务完成

任务：监控 IM 聊天，自动回复消息。
请返回 JSON: {"action": "...", "params": {...}, "reason": "..."}"""

    messages = [{"role": "system", "content": system_msg}]
    for h in history[-10:]:  # 保留最近10轮
        messages.append(h)
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": "当前页面截图："},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}}
        ]
    })
    
    resp = client.chat.completions.create(
        model="moonshot-v1-32k-vision-preview",
        messages=messages,
        temperature=0.2
    )
    
    content = resp.choices[0].message.content
    # 提取 JSON
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except:
        return {"action": "wait", "params": {"seconds": 3}, "reason": "parse error"}

def execute_action(action_data, step):
    """执行 Kimi 返回的操作"""
    action = action_data.get("action")
    params = action_data.get("params", {})
    
    if action == "open":
        return run_cmd(f"open {params.get('url', IM_URL)}")
    elif action == "click":
        return run_cmd(f"click {params.get('index', 1)}")
    elif action == "input":
        idx = params.get("index", 1)
        text = params.get("text", "")
        return run_cmd(f'input {idx} "{text}"')
    elif action == "type":
        return run_cmd(f'type "{params.get("text", "")}"')
    elif action == "state":
        return run_cmd("state")
    elif action == "wait":
        time.sleep(params.get("seconds", 3))
        return "waited"
    elif action == "done":
        return "done"
    return "unknown"

def main():
    print("🤖 Kimi IM 机器人启动")
    print(f"目标: {IM_URL}")
    
    if not KIMI_API_KEY:
        print("❌ 错误: 请设置 KIMI_API_KEY 环境变量")
        return
    
    # 打开初始页面
    print("\n打开 IM 网页...")
    run_cmd(f"open {IM_URL}")
    time.sleep(5)
    
    history = []
    
    for step in range(1, MAX_STEPS + 1):
        print(f"\n--- 步骤 {step}/{MAX_STEPS} ---")
        
        # 截图
        img_path = screenshot(step)
        
        # Kimi 决策
        decision = kimi_decide(img_path, history)
        print(f"🧠 Kimi: {decision.get('reason', 'no reason')}")
        print(f"🎯 操作: {decision.get('action')} {decision.get('params', {})}")
        
        # 记录历史
        history.append({"role": "user", "content": f"步骤 {step} 截图"})
        history.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        
        # 执行
        result = execute_action(decision, step)
        print(f"✅ 结果: {result[:100]}..." if len(str(result)) > 100 else f"✅ 结果: {result}")
        
        if decision.get("action") == "done":
            print("\n🎉 任务完成")
            break
        
        time.sleep(STEP_DELAY)
    
    print("\n机器人停止")
    run_cmd("close")

if __name__ == "__main__":
    main()
