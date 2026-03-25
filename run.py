#!/usr/bin/env python3
"""
交互式启动脚本 - 更方便的启动方式
"""
import sys
from src.im_bot import IMBot
from src.platforms import list_platforms, get_platform
from src.utils.logger import logger
from src.config import get_app_config, validate_config, resolve_kimi_api_key, LOG_FILE


def print_menu():
    """打印菜单"""
    print("\n" + "=" * 60)
    print("🤖 Kimi 视觉驱动 IM 机器人")
    print("=" * 60)
    print()
    print("请选择平台:")
    platforms = list_platforms()
    for i, p in enumerate(platforms, 1):
        platform = get_platform(p)
        print(f"  {i}. {platform.config.name}")
    print()
    print("  0. 退出")
    print()


def get_config():
    """获取配置"""
    app_config = get_app_config()
    runtime_config = app_config['runtime']

    try:
        validate_config()
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        print("\n❌ 请先设置 Kimi API Key")
        print("   方法 1: export KIMI_API_KEY='sk-your-api-key'")
        print("   方法 2: python config_center.py")
        return None
    
    platforms = list_platforms()
    
    # 选择平台
    while True:
        choice = input("请输入数字 (0-2): ").strip()
        
        if choice == '0':
            return None
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(platforms):
                platform = platforms[idx]
                break
        
        print("无效选择，请重试")
    
    # 高级配置
    print(f"\n配置 {platform} 机器人:")
    
    steps_input = input(f"最大运行步数 [默认: {runtime_config['max_steps']}]: ").strip()
    steps = int(steps_input) if steps_input.isdigit() else runtime_config['max_steps']
    
    delay_input = input(f"每步间隔秒数 [默认: {runtime_config['step_delay']}]: ").strip()
    delay = int(delay_input) if delay_input.isdigit() else runtime_config['step_delay']
    
    return {
        'platform': platform,
        'steps': steps,
        'delay': delay
    }


def main():
    app_config = get_app_config()
    logging_config = app_config['logging']
    logger.log_file = LOG_FILE
    logger.set_level(logging_config['level'])

    # 检查 API Key
    if app_config['runtime'].get('debug'):
        logger.set_level('DEBUG')

    if not resolve_kimi_api_key(app_config):
        print("\n" + "=" * 60)
        print("⚠️  请先设置 Kimi API Key")
        print("=" * 60)
        print("\n方法 1 (临时):")
        print("  export KIMI_API_KEY='sk-your-api-key'")
        print("\n方法 2 (配置台):")
        print("  python config_center.py")
        print("\n方法 3 (永久 - bash/zsh):")
        print("  echo 'export KIMI_API_KEY=sk-your-api-key' >> ~/.zshrc")
        print("  source ~/.zshrc")
        print("\n获取 API Key: https://platform.moonshot.cn/")
        print("=" * 60 + "\n")
        return
    
    while True:
        print_menu()
        config = get_config()
        
        if config is None:
            print("再见！")
            break
        
        print(f"\n启动 {config['platform']} 机器人...")
        print(f"配置: {config['steps']} 步, {config['delay']} 秒间隔")
        print("按 Ctrl+C 停止\n")
        
        # 启动机器人
        bot = IMBot(
            platform=config['platform'],
            max_steps=config['steps'],
            step_delay=config['delay']
        )
        
        try:
            bot.start()
        except Exception as e:
            logger.error(f"机器人异常: {e}")
        
        print("\n" + "-" * 60)
        restart = input("是否重新开始? (y/n): ").strip().lower()
        if restart != 'y':
            print("再见！")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已退出")
