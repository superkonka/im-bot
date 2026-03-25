#!/usr/bin/env python3
"""
多平台 IM 机器人 - 支持 WhatsApp Web 和 Telegram Web
Kimi 视觉驱动浏览器自动化
"""

import os
import sys
import base64
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from platform_configs import get_platform_config, get_platform_list

# ============ 配置 ============
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
SCREENSHOT_DIR = Path("./screenshots")
LOG_FILE = Path("./bot.log")

# 创建目录
SCREENSHOT_DIR.mkdir(exist_ok=True)

# 初始化 Kimi
client = OpenAI(api_key=KIMI_API_KEY, base_url="https://api.moonshot.cn/v1")


def log(message: str):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")


def run_browser_cmd(cmd: str, timeout: int = 30) -> str:
    """执行 browser-use CLI 命令"""
    try:
        result = subprocess.run(
            f"browser-use {cmd}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timeout"
    except Exception as e:
        return f"Error: {e}"


def take_screenshot(step: int, prefix: str = "") -> str:
    """截图"""
    filename = f"{prefix}step_{step:03d}.png" if prefix else f"step_{step:03d}.png"
    filepath = SCREENSHOT_DIR / filename
    result = run_browser_cmd(f"screenshot {filepath}")
    log(f"[截图] {result}")
    return str(filepath)


def encode_image(image_path: str) -> str:
    """图片转 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def kimi_decide(screenshot_path: str, history: list, system_prompt: str) -> dict:
    """
    让 Kimi 分析截图并决定下一步操作
    """
    base64_image = encode_image(screenshot_path)
    
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-15:],  # 保留最近15轮
        {
            "role": "user",
            "content": [
                {
                    "type": "text", 
                    "text": f"当前时间: {datetime.now().strftime('%H:%M:%S')}\n"
                           f"请分析截图，决定下一步操作。返回 JSON: "
                           f"{{\"action\": \"...\", \"params\": {{...}}, \"reason\": \"...\"}}"
                },
                {
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                }
            ]
        }
    ]
    
    try:
        response = client.chat.completions.create(
            model="moonshot-v1-32k-vision-preview",
            messages=messages,
            temperature=0.2,
            max_tokens=1500
        )
        
        content = response.choices[0].message.content
        
        # 提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        decision = json.loads(content.strip())
        log(f"🧠 Kimi 决策: {decision.get('reason', 'N/A')}")
        return decision
        
    except json.JSONDecodeError as e:
        log(f"❌ JSON 解析错误: {e}, 内容: {content[:200]}")
        return {"action": "wait", "params": {"seconds": 5}, "reason": "JSON parse error"}
    except Exception as e:
        log(f"❌ Kimi API 错误: {e}")
        return {"action": "wait", "params": {"seconds": 5}, "reason": f"API error: {e}"}


def execute_action(action_data: dict, platform_config: dict) -> str:
    """执行 Kimi 返回的操作"""
    action = action_data.get("action", "wait")
    params = action_data.get("params", {})
    
    if action == "open":
        url = params.get("url", platform_config["url"])
        result = run_browser_cmd(f"open {url}")
        time.sleep(3)
        return result
        
    elif action == "click":
        index = params.get("index", 1)
        result = run_browser_cmd(f"click {index}")
        time.sleep(2)
        return result
        
    elif action == "input":
        index = params.get("index", 1)
        text = params.get("text", "")
        # 转义特殊字符
        text = text.replace('"', '\\"')
        result = run_browser_cmd(f'input {index} "{text}"')
        time.sleep(1)
        return result
        
    elif action == "type":
        text = params.get("text", "")
        text = text.replace('"', '\\"')
        result = run_browser_cmd(f'type "{text}"')
        time.sleep(1)
        return result
        
    elif action == "state":
        return run_browser_cmd("state")
        
    elif action == "wait":
        seconds = params.get("seconds", 3)
        time.sleep(seconds)
        return f"等待 {seconds} 秒"
        
    elif action == "done":
        return "任务完成"
        
    else:
        return f"未知操作: {action}"


def check_login_status(screenshot_path: str, platform: str) -> bool:
    """
    检查是否已登录（通过 Kimi 视觉判断）
    """
    base64_image = encode_image(screenshot_path)
    
    prompt = f"""分析这张 {platform} 网页截图，判断是否已完成登录。

判断标准：
- 如果看到二维码 → 未登录
- 如果看到手机号输入框 → 未登录
- 如果看到聊天列表 → 已登录
- 如果看到消息"请使用手机登录" → 未登录

只返回一个 JSON: {{"logged_in": true/false, "hint": "..."}}"""

    try:
        response = client.chat.completions.create(
            model="moonshot-v1-32k-vision-preview",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        result = json.loads(content.strip())
        return result.get("logged_in", False)
        
    except Exception as e:
        log(f"❌ 登录状态检查失败: {e}")
        return False


def wait_for_login(platform_config: dict, max_wait: int = 120):
    """等待用户完成登录"""
    log(f"⏳ 等待登录 ({platform_config['name']})...")
    log(f"💡 提示: {platform_config['tips'][0]}")
    
    waited = 0
    check_interval = 5
    
    while waited < max_wait:
        time.sleep(check_interval)
        waited += check_interval
        
        # 截图检查
        img_path = str(SCREENSHOT_DIR / "login_check.png")
        run_browser_cmd(f"screenshot {img_path}")
        
        if check_login_status(img_path, platform_config["name"]):
            log(f"✅ 登录成功！等待了 {waited} 秒")
            return True
        
        if waited % 15 == 0:
            log(f"⏳ 仍在等待登录... ({waited}/{max_wait} 秒)")
    
    log(f"⚠️ 登录等待超时 ({max_wait} 秒)")
    return False


def run_bot(platform: str, max_steps: int = 500, step_delay: int = 3):
    """
    运行机器人主循环
    
    Args:
        platform: "whatsapp" 或 "telegram"
        max_steps: 最大运行步数
        step_delay: 每步间隔（秒）
    """
    if platform not in get_platform_list():
        log(f"❌ 不支持的平台: {platform}")
        log(f"支持的平台: {', '.join(get_platform_list())}")
        return
    
    config = get_platform_config(platform)
    
    log("=" * 60)
    log(f"🤖 启动 {config['name']} 机器人")
    log("=" * 60)
    log(f"📱 目标网址: {config['url']}")
    log(f"📝 登录方式: {config['login_method']}")
    log(f"💡 使用提示:")
    for tip in config['tips']:
        log(f"   • {tip}")
    
    if not KIMI_API_KEY:
        log("❌ 错误: 未设置 KIMI_API_KEY 环境变量")
        log("   请运行: export KIMI_API_KEY='your-api-key'")
        return
    
    # 打开网页
    log(f"\n[初始化] 打开 {config['name']}...")
    run_browser_cmd(f"open {config['url']}")
    time.sleep(5)
    
    # 等待登录
    if not wait_for_login(config):
        log("❌ 登录失败，机器人退出")
        return
    
    log("\n🚀 开始监控消息...")
    log("按 Ctrl+C 停止机器人\n")
    
    history = []
    
    try:
        for step in range(1, max_steps + 1):
            log(f"\n{'─' * 60}")
            log(f"[步骤 {step}/{max_steps}] {datetime.now().strftime('%H:%M:%S')}")
            
            # 1. 截图
            img_path = take_screenshot(step, prefix=f"{platform}_")
            
            # 2. Kimi 决策
            decision = kimi_decide(img_path, history, config["prompt"])
            action = decision.get("action", "wait")
            params = decision.get("params", {})
            
            log(f"🎯 操作: {action} {params}")
            
            # 3. 更新历史
            history.append({"role": "user", "content": f"步骤 {step} 截图"})
            history.append({
                "role": "assistant", 
                "content": json.dumps(decision, ensure_ascii=False)
            })
            
            # 4. 执行操作
            result = execute_action(decision, config)
            log(f"✅ 执行结果: {result[:100]}..." if len(str(result)) > 100 else f"✅ 执行结果: {result}")
            
            if action == "done":
                log("\n🎉 任务完成")
                break
            
            time.sleep(step_delay)
            
    except KeyboardInterrupt:
        log("\n\n⚠️ 用户中断")
    except Exception as e:
        log(f"\n❌ 运行错误: {e}")
    finally:
        log("\n🛑 机器人停止")
        log(f"📊 共运行 {step} 步")
        run_browser_cmd("close")


def main():
    """主函数 - 交互式选择平台"""
    print("=" * 60)
    print("🤖 多平台 IM 机器人")
    print("支持: WhatsApp Web, Telegram Web")
    print("=" * 60)
    print()
    
    # 选择平台
    platforms = get_platform_list()
    print("请选择平台:")
    for i, p in enumerate(platforms, 1):
        config = get_platform_config(p)
        print(f"  {i}. {config['name']}")
    print()
    
    try:
        choice = input("请输入数字 (1-2) [默认: 1]: ").strip()
        if not choice:
            choice = "1"
        
        platform_idx = int(choice) - 1
        if platform_idx < 0 or platform_idx >= len(platforms):
            print("❌ 无效选择")
            return
        
        platform = platforms[platform_idx]
        
        # 高级配置
        print()
        print("高级配置 (直接回车使用默认值):")
        
        max_steps_input = input("最大运行步数 [默认: 500]: ").strip()
        max_steps = int(max_steps_input) if max_steps_input.isdigit() else 500
        
        step_delay_input = input("每步间隔秒数 [默认: 3]: ").strip()
        step_delay = int(step_delay_input) if step_delay_input.isdigit() else 3
        
        print()
        run_bot(platform, max_steps, step_delay)
        
    except ValueError:
        print("❌ 请输入有效的数字")
    except KeyboardInterrupt:
        print("\n\n已取消")


if __name__ == "__main__":
    # 也可以命令行直接指定平台
    if len(sys.argv) > 1:
        platform = sys.argv[1].lower()
        max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 500
        step_delay = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        run_bot(platform, max_steps, step_delay)
    else:
        main()
