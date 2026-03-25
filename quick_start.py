#!/usr/bin/env python3
"""
快速开始脚本 - 一行命令启动 WhatsApp/Telegram 机器人
"""

import sys
import os

# 检查环境变量
if not os.getenv("KIMI_API_KEY"):
    print("❌ 请先设置 KIMI_API_KEY 环境变量")
    print("   export KIMI_API_KEY='sk-your-api-key'")
    sys.exit(1)

# 导入主程序
from multi_platform_bot import run_bot

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python quick_start.py <platform> [max_steps] [delay]")
        print()
        print("平台:")
        print("  whatsapp  - WhatsApp Web")
        print("  telegram  - Telegram Web")
        print()
        print("示例:")
        print("  python quick_start.py whatsapp")
        print("  python quick_start.py telegram 200 5")
        sys.exit(1)
    
    platform = sys.argv[1].lower()
    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    step_delay = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    
    run_bot(platform, max_steps, step_delay)
