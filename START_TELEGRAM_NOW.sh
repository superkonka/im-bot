#!/bin/bash
echo "=========================================="
echo "🚀 Telegram 机器人 - 完整版启动"
echo "=========================================="
echo ""

export KIMI_API_KEY="sk-7NnrK4lE7sz0VrjUA8N2pFPIl0Wn8ZjTBJB6QZsrM1K0Nqu5"

cd /Users/konkapeng/im_bot

echo "📱 登录步骤："
echo "  1. 浏览器会自动打开 web.telegram.org/k/"
echo "  2. 点击 'LOG IN BY PHONE NUMBER'"
echo "  3. 输入手机号 (+86xxxxxxxxxxx)"
echo "  4. 输入短信验证码"
echo "  5. 登录后机器人自动开始工作"
echo ""
read -p "按回车键开始..."
echo ""

python main.py telegram --steps 500 --delay 3
