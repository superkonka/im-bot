#!/usr/bin/env python3
"""
IM 机器人 - 主入口
"""
import sys
import argparse
from src.im_bot import IMBot
from src.platforms import list_platforms
from src.utils.logger import logger
from src.config import get_app_config, validate_config, LOG_FILE


def main():
    app_config = get_app_config()
    runtime_config = app_config['runtime']
    browser_config = app_config['browser']
    logging_config = app_config['logging']

    parser = argparse.ArgumentParser(
        description="Kimi 视觉驱动 IM 机器人",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
支持的平台: {', '.join(list_platforms())}

示例:
  python main.py whatsapp                    # 启动 WhatsApp 机器人
  python main.py telegram --steps 200        # Telegram，运行 200 步
  python main.py whatsapp --delay 5          # WhatsApp，每步间隔 5 秒
        """
    )
    
    parser.add_argument(
        'platform',
        choices=list_platforms(),
        help='选择 IM 平台'
    )
    
    parser.add_argument(
        '--steps', '-s',
        type=int,
        default=runtime_config['max_steps'],
        help=f"最大运行步数 (默认: {runtime_config['max_steps']})"
    )
    
    parser.add_argument(
        '--delay', '-d',
        type=int,
        default=runtime_config['step_delay'],
        help=f"每步间隔秒数 (默认: {runtime_config['step_delay']})"
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        default=browser_config['headless'],
        help=f"无头模式（不显示浏览器窗口，默认: {browser_config['headless']}）"
    )

    parser.add_argument(
        '--headed',
        dest='headless',
        action='store_false',
        help='显式关闭无头模式，显示浏览器窗口'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='调试模式（更多日志）'
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    logger.log_file = LOG_FILE
    logger.set_level(logging_config['level'])
    if runtime_config.get('debug'):
        logger.set_level('DEBUG')
    if args.debug:
        logger.set_level('DEBUG')
    
    # 验证配置
    try:
        validate_config()
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        logger.info("请设置环境变量 KIMI_API_KEY，或运行 python config_center.py 打开配置台")
        sys.exit(1)
    
    # 启动机器人
    bot = IMBot(
        platform=args.platform,
        max_steps=args.steps,
        step_delay=args.delay,
        headless=args.headless
    )
    
    bot.start()


if __name__ == "__main__":
    main()
