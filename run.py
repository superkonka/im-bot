#!/usr/bin/env python3
"""
交互式启动脚本 - 更方便的启动方式
支持工作流录制和回放
"""
import sys
from getpass import getpass
from src.launcher import launch_platform, resolve_telegram_transport
from src.platforms import list_platforms, get_platform
from src.telegram_userbot import TelegramUserSettings, fetch_recent_dialog_choices
from src.workflow_engine import WorkflowManager
from src.utils.logger import logger
from src.config import (
    get_config_center_url,
    get_app_config,
    validate_config,
    resolve_kimi_api_key,
    save_app_config,
    get_missing_telegram_user_fields,
    LOG_FILE,
)


def print_menu():
    """打印菜单"""
    print("\n" + "=" * 60)
    print("🤖 Kimi 视觉驱动 IM 机器人")
    print("=" * 60)
    print()
    print("请选择模式:")
    platforms = list_platforms()
    for i, p in enumerate(platforms, 1):
        platform = get_platform(p)
        print(f"  {i}. {platform.config.name}")
    print("  3. 🌐 自由网页操控 (任意URL)")
    print("  4. 🎬 执行已保存的工作流")
    print("  5. 📋 管理工作流")
    print()
    print("  0. 退出")
    print()


def get_free_web_config():
    """获取自由网页操控配置"""
    app_config = get_app_config()
    runtime_config = app_config['runtime']
    
    print("\n" + "=" * 60)
    print("🌐 自由网页操控模式")
    print("=" * 60)
    print("\n此模式允许你操控任意网页，只需提供 URL 和目标描述。")
    print("AI 会自动分析页面并执行操作来完成你的目标。\n")
    
    # 输入 URL
    while True:
        url = input("请输入网页 URL (如 https://www.example.com): ").strip()
        if url:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            break
        print("URL 不能为空，请重新输入")
    
    # 输入目标
    print("\n请描述你想让 AI 完成什么任务，例如:")
    print('  - "搜索今天的新闻"')
    print('  - "登录账号并查看订单"')
    print('  - "填写表单并提交"')
    print('  - "点击购物车并结算"')
    goal = input("\n任务目标: ").strip()
    
    if not goal:
        goal = "探索网页并完成合理任务"
        print(f"使用默认目标: {goal}")
    
    # 询问是否录制
    record_input = input("\n是否录制为工作流？ [y/N]: ").strip().lower()
    record_mode = record_input in ('y', 'yes')
    
    workflow_name = None
    if record_mode:
        workflow_name = input("工作流名称 [默认自动生成]: ").strip()
    
    # 高级配置
    print(f"\n配置选项 (直接回车使用默认值):")
    
    steps_input = input(f"最大运行步数 [默认: {runtime_config['max_steps']}]: ").strip()
    steps = int(steps_input) if steps_input.isdigit() else runtime_config['max_steps']
    
    delay_input = input(f"每步间隔秒数 [默认: {runtime_config['step_delay']}]: ").strip()
    delay = int(delay_input) if delay_input.isdigit() else runtime_config['step_delay']
    
    headless_input = input("无头模式 (后台运行，不显示浏览器) [y/N]: ").strip().lower()
    headless = headless_input in ('y', 'yes')
    
    return {
        'platform': 'free_web',
        'url': url,
        'goal': goal,
        'steps': steps,
        'delay': delay,
        'headless': headless,
        'record_mode': record_mode,
        'workflow_name': workflow_name,
    }


def get_workflow_playback_config():
    """获取工作流回放配置"""
    manager = WorkflowManager()
    workflows = manager.list_workflows()
    
    print("\n" + "=" * 60)
    print("🎬 执行已保存的工作流")
    print("=" * 60)
    
    if not workflows:
        print("\n暂无保存的工作流。先使用自由网页操控模式录制一个吧！")
        return None
    
    print("\n已保存的工作流:")
    for i, wf in enumerate(workflows, 1):
        print(f"  {i}. {wf['name']} ({wf['step_count']} 步骤)")
        print(f"     {wf['description'][:50]}...")
    print("  0. 返回")
    
    while True:
        choice = input("\n请选择工作流 (0-{}): ".format(len(workflows))).strip()
        if choice == '0':
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                selected = workflows[idx]
                break
        print("无效选择")
    
    # 加载工作流获取参数信息
    workflow = manager.load_workflow(selected['filename'])
    params = {}
    
    if workflow and workflow.parameters:
        print(f"\n工作流参数:")
        for param in workflow.parameters:
            name = param['name']
            default = param.get('default', '')
            desc = param.get('description', '')
            prompt = f"{name}"
            if desc:
                prompt += f" ({desc})"
            if default:
                prompt += f" [默认: {default}]"
            prompt += ": "
            
            value = input(prompt).strip()
            params[name] = value if value else default
    
    # 高级配置
    print(f"\n执行选项:")
    headless_input = input("无头模式 (后台运行) [y/N]: ").strip().lower()
    headless = headless_input in ('y', 'yes')
    
    return {
        'platform': 'free_web',
        'workflow_file': selected['filename'],
        'workflow_params': params,
        'headless': headless,
        'url': workflow.start_url if workflow else '',
        'goal': f"执行工作流: {selected['name']}",
    }


def manage_workflows():
    """管理工作流"""
    manager = WorkflowManager()
    
    while True:
        workflows = manager.list_workflows()
        
        print("\n" + "=" * 60)
        print("📋 工作流管理")
        print("=" * 60)
        
        if workflows:
            print("\n已保存的工作流:")
            for i, wf in enumerate(workflows, 1):
                print(f"  {i}. {wf['name']}")
                print(f"     步骤: {wf['step_count']} | 更新: {wf['updated_at'][:10]}")
        else:
            print("\n暂无工作流")
        
        print("\n操作:")
        print("  d. 删除工作流")
        print("  v. 查看详情")
        print("  0. 返回")
        
        choice = input("\n选择操作: ").strip().lower()
        
        if choice == '0':
            break
        elif choice == 'd':
            if not workflows:
                print("没有可删除的工作流")
                continue
            name = input("输入要删除的工作流名称: ").strip()
            if manager.delete_workflow(name):
                print("删除成功")
            else:
                print("工作流不存在")
        elif choice == 'v':
            if not workflows:
                print("没有可查看的工作流")
                continue
            name = input("输入要查看的工作流名称: ").strip()
            workflow = manager.load_workflow(name)
            if workflow:
                print(f"\n工作流: {workflow.name}")
                print(f"描述: {workflow.description}")
                print(f"起始 URL: {workflow.start_url}")
                print(f"步骤数: {len(workflow.steps)}")
                print(f"创建时间: {workflow.created_at}")
                print(f"更新时间: {workflow.updated_at}")
                print("\n步骤列表:")
                for step in workflow.steps:
                    print(f"  {step.step_number}. [{step.step_type}] {step.description}")
            else:
                print("工作流不存在")
        else:
            print("无效选择")


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
        choice = input("请输入数字 (0-5): ").strip()
        
        if choice == '0':
            return None
        
        if choice == '3':
            return get_free_web_config()
        
        if choice == '4':
            return get_workflow_playback_config()
        
        if choice == '5':
            manage_workflows()
            return 'manage_workflows'  # 特殊标记
        
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
    
    transport = 'auto'
    if platform == 'telegram':
        default_transport = resolve_telegram_transport('auto', app_config)
        transport_input = input(f"Telegram 启动方式 [默认: {default_transport}, user/web]: ").strip().lower()
        if transport_input in {'user', 'web'}:
            transport = transport_input

    return {
        'platform': platform,
        'steps': steps,
        'delay': delay,
        'transport': transport,
    }


def ensure_telegram_user_onboarding():
    """交互式补齐 Telegram 用户账号模式的关键配置"""
    app_config = get_app_config()
    missing = get_missing_telegram_user_fields(app_config)
    if not missing:
        return

    telegram_user = dict(app_config.get('telegram_user', {}))
    print("\n" + "=" * 60)
    print("Telegram 用户账号模式首次配置")
    print("=" * 60)
    print("当前缺少以下关键项: " + ", ".join(missing))
    print("直接回车将保留现有值。\n")

    if 'api_id' in missing:
        current = telegram_user.get('api_id', '')
        value = input(f"TELEGRAM_API_ID [{current or '未设置'}]: ").strip()
        if value:
            telegram_user['api_id'] = value

    if 'api_hash' in missing:
        current = telegram_user.get('api_hash', '')
        prompt = "TELEGRAM_API_HASH [已设置则回车跳过]: " if current else "TELEGRAM_API_HASH: "
        value = getpass(prompt).strip()
        if value:
            telegram_user['api_hash'] = value

    phone_current = telegram_user.get('phone_number', '')
    phone_value = input(f"手机号（可选） [{phone_current or '留空即可'}]: ").strip()
    if phone_value:
        telegram_user['phone_number'] = phone_value

    if 'target_chat' in missing:
        current = telegram_user.get('target_chat', '')
        if telegram_user.get('api_id') and telegram_user.get('api_hash'):
            use_picker = input("尝试读取最近聊天列表来选择目标聊天？ [Y/n]: ").strip().lower()
            if use_picker in {"", "y", "yes"}:
                temp_config = dict(app_config)
                temp_config['telegram_user'] = telegram_user
                try:
                    settings = TelegramUserSettings.from_config(temp_config)
                    choices = fetch_recent_dialog_choices(settings, limit=12)
                except Exception as exc:
                    print(f"读取最近聊天失败: {exc}")
                    choices = []

                if choices:
                    print("\n最近聊天列表:")
                    for index, choice in enumerate(choices, 1):
                        print(f"  {index}. {choice.display_label()}")

                    selection = input("选择目标聊天编号，或直接回车手动输入: ").strip()
                    if selection.isdigit():
                        idx = int(selection) - 1
                        if 0 <= idx < len(choices):
                            telegram_user['target_chat'] = choices[idx].target_value()
                            print(f"已选择目标聊天: {choices[idx].display_label()}")

        if not telegram_user.get('target_chat'):
            value = input(f"目标聊天用户名/备注名/ID [{current or '未设置'}]: ").strip()
            if value:
                telegram_user['target_chat'] = value

    if 'persona' in missing:
        current = telegram_user.get('persona', '')
        value = input(f"人设说明 [{current or '未设置'}]: ").strip()
        if value:
            telegram_user['persona'] = value

    if 'allowed_topics' in missing:
        current_topics = telegram_user.get('allowed_topics', [])
        current_label = "、".join(current_topics) if current_topics else "未设置"
        value = input(f"允许话题（用中文逗号分隔） [{current_label}]: ").strip()
        if value:
            telegram_user['allowed_topics'] = [item.strip() for item in value.replace('，', ',').split(',') if item.strip()]

    app_config['telegram_user'] = telegram_user
    save_app_config(app_config)
    print("\n已保存 Telegram 用户账号配置。")
    print("首次登录时 Telethon 会在终端中提示验证码，session 会保存在 data/telegram_sessions 下。\n")


def main():
    app_config = get_app_config()
    config_center_url = get_config_center_url()
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
        print(f"  打开后访问: {config_center_url}")
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
        
        # 管理工作流后直接继续循环
        if config == 'manage_workflows':
            continue
        
        print(f"\n启动 {config['platform']} 机器人...")
        if 'steps' in config:
            print(f"配置: {config['steps']} 步, {config['delay']} 秒间隔")
        print("按 Ctrl+C 停止\n")
        print(f"配置中心 / 运行后台地址: {config_center_url}（需先运行 python config_center.py）\n")
        logger.info(f"配置中心 / 运行后台地址: {config_center_url}（需先运行 python config_center.py）")

        if config['platform'] == 'telegram' and config.get('transport', 'auto') != 'web':
            ensure_telegram_user_onboarding()

        try:
            if config['platform'] == 'free_web':
                launch_platform(
                    platform=config['platform'],
                    url=config['url'],
                    goal=config['goal'],
                    max_steps=config.get('steps', 50),
                    step_delay=config.get('delay', 3),
                    headless=config.get('headless', False),
                    record_mode=config.get('record_mode', False),
                    workflow_name=config.get('workflow_name'),
                    workflow_file=config.get('workflow_file'),
                    workflow_params=config.get('workflow_params', {}),
                )
            else:
                launch_platform(
                    platform=config['platform'],
                    max_steps=config['steps'],
                    step_delay=config['delay'],
                    transport=config.get('transport', 'auto'),
                )
        except ValueError as e:
            logger.error(f"配置错误: {e}")
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
