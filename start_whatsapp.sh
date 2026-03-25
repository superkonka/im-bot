#!/bin/bash
# WhatsApp 机器人启动脚本

echo "=========================================="
echo "🤖 WhatsApp 机器人启动器"
echo "=========================================="
echo ""

# 检查是否在本地运行
if [ -n "$SSH_CLIENT" ] || [ -n "$SSH_TTY" ]; then
    echo "⚠️  检测到 SSH 远程连接"
    echo ""
    echo "当前是通过远程终端连接的，无法显示浏览器窗口。"
    echo ""
    echo "请在本地 Mac 上直接运行此脚本："
    echo "  1. 打开 Terminal.app 或 iTerm2"
    echo "  2. cd /Users/konkapeng/im_bot"
    echo "  3. ./start_whatsapp.sh"
    echo ""
    exit 1
fi

# 设置 API Key
export KIMI_API_KEY="sk-7NnrK4lE7sz0VrjUA8N2pFPIl0Wn8ZjTBJB6QZsrM1K0Nqu5"

# 检查 API Key
if [ -z "$KIMI_API_KEY" ]; then
    echo "❌ 错误: KIMI_API_KEY 未设置"
    exit 1
fi

echo "✅ API Key 已设置"
echo ""

# 提示用户
echo "📝 使用说明:"
echo "   1. 浏览器会自动打开 WhatsApp Web"
echo "   2. 请用手机扫码登录"
echo "   3. 登录后机器人自动开始监控消息"
echo "   4. 按 Ctrl+C 停止机器人"
echo ""
read -p "按回车键开始启动..."

echo ""
echo "🚀 启动机器人..."
echo ""

# 启动机器人
python main.py whatsapp --steps 500 --delay 3

echo ""
echo "=========================================="
echo "机器人已停止"
echo "=========================================="
