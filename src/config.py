#!/usr/bin/env python3
"""
统一配置中心

- 结构化 JSON 配置，方便人和 LLM 读取/修改
- 提供默认配置、Schema、读写接口
- 兼容旧代码使用的常量导出
"""
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


# 基础路径
BASE_DIR = Path(__file__).parent.parent
SCREENSHOT_DIR = BASE_DIR / "screenshots"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = DATA_DIR / "app_config.json"

# 创建目录
SCREENSHOT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


DEFAULT_APP_CONFIG: Dict[str, Any] = {
    "api": {
        "kimi_api_key": "",
        "kimi_base_url": "https://api.moonshot.cn/v1",
        "kimi_vision_model": "moonshot-v1-32k-vision-preview",
        "kimi_text_model": "moonshot-v1-8k",
    },
    "runtime": {
        "default_platform": "whatsapp",
        "max_steps": 500,
        "step_delay": 3,
        "login_timeout": 120,
        "debug": False,
        "target_chat_name": "",
    },
    "browser": {
        "headless": False,
        "timeout": 30,
        "viewport_width": 1280,
        "viewport_height": 800,
        "launch_args": ["--disable-blink-features=AutomationControlled"],
    },
    "vision": {
        "max_history": 15,
        "decision_temperature": 0.2,
        "decision_max_tokens": 1500,
        "validation_temperature": 0.1,
        "validation_max_tokens": 800,
    },
    "logging": {
        "level": "INFO",
        "log_file": str(LOG_DIR / "bot.log"),
    },
    "use_case_validation": {
        "default_next_actions": ["proceed", "retry", "review", "stop"],
        "strict_json": True,
        "include_evidence": True,
    },
    "platforms": {
        "whatsapp": {
            "name": "WhatsApp Web",
            "url": "https://web.whatsapp.com",
            "login_method": "qr_code",
            "login_wait": 30,
            "selectors": {
                "chat_list": "[data-testid='chat-list']",
                "chat_item": "[data-testid='cell-frame-container']",
                "unread_badge": "[data-testid='icon-unread-count']",
                "message_input": "[data-testid='conversation-compose-box-input']",
                "send_button": "[data-testid='send']",
                "message_bubble": "[data-testid='msg-container']",
            },
            "tips": [
                "WhatsApp 需要手机扫码登录，首次使用请准备好手机",
                "未读消息通常显示绿色数字角标",
                "聊天列表在左侧，消息区域在右侧",
                "输入框在页面底部",
            ],
        },
        "telegram": {
            "name": "Telegram Web",
            "url": "https://web.telegram.org/k/",
            "login_method": "phone_code",
            "login_wait": 60,
            "selectors": {
                "chat_list": ".chat-list",
                "chat_item": ".chat",
                "unread_badge": ".badge.unread",
                "search_input": "input[type='text']",
                "message_input": ".composer-input",
                "send_button": ".btn-icon.send",
                "message_bubble": ".message",
            },
            "tips": [
                "Telegram 可以使用手机号+验证码登录",
                "未读消息显示蓝色数字角标",
                "左侧是聊天列表，右侧是消息区域",
                "K 版本 (web.telegram.org/k/) 比 A 版更稳定",
            ],
        },
    },
}


CONFIG_SCHEMA: Dict[str, Any] = {
    "api": {
        "title": "API",
        "description": "模型与接口访问配置",
        "fields": {
            "kimi_api_key": {
                "type": "string",
                "label": "Kimi API Key",
                "description": "Moonshot 平台 API Key。也可被环境变量 KIMI_API_KEY 覆盖。",
                "secret": True,
            },
            "kimi_base_url": {
                "type": "string",
                "label": "Base URL",
                "description": "Kimi 接口基础地址",
            },
            "kimi_vision_model": {
                "type": "string",
                "label": "视觉模型",
                "description": "截图分析与用例校验使用的模型",
            },
            "kimi_text_model": {
                "type": "string",
                "label": "文本模型",
                "description": "预留给纯文本能力使用的模型",
            },
        },
    },
    "runtime": {
        "title": "运行",
        "description": "机器人运行时的默认行为",
        "fields": {
            "default_platform": {
                "type": "enum",
                "label": "默认平台",
                "description": "未显式指定时的默认平台",
                "options": ["whatsapp", "telegram"],
            },
            "max_steps": {
                "type": "integer",
                "label": "最大步数",
                "description": "主循环最多运行多少步",
            },
            "step_delay": {
                "type": "integer",
                "label": "步进延迟(秒)",
                "description": "每一步操作之间的默认等待时间",
            },
            "login_timeout": {
                "type": "integer",
                "label": "登录超时(秒)",
                "description": "等待人工完成登录的超时时间",
            },
            "debug": {
                "type": "boolean",
                "label": "调试模式",
                "description": "启用更详细的日志输出",
            },
            "target_chat_name": {
                "type": "string",
                "label": "指定聊天",
                "description": "填写后，机器人会优先打开并轮询这个聊天窗口进行自动回复。",
            },
        },
    },
    "browser": {
        "title": "浏览器",
        "description": "Playwright 浏览器启动与页面行为",
        "fields": {
            "headless": {
                "type": "boolean",
                "label": "无头模式",
                "description": "是否隐藏浏览器窗口",
            },
            "timeout": {
                "type": "integer",
                "label": "超时(秒)",
                "description": "浏览器层默认超时",
            },
            "viewport_width": {
                "type": "integer",
                "label": "视口宽度",
                "description": "浏览器窗口宽度",
            },
            "viewport_height": {
                "type": "integer",
                "label": "视口高度",
                "description": "浏览器窗口高度",
            },
            "launch_args": {
                "type": "json",
                "label": "启动参数",
                "description": "Chromium 启动参数列表，JSON 数组格式",
            },
        },
    },
    "vision": {
        "title": "视觉代理",
        "description": "Kimi 视觉分析与验收策略",
        "fields": {
            "max_history": {
                "type": "integer",
                "label": "最大历史轮数",
                "description": "保留给模型的最近对话轮数",
            },
            "decision_temperature": {
                "type": "float",
                "label": "决策温度",
                "description": "截图决策时的温度",
            },
            "decision_max_tokens": {
                "type": "integer",
                "label": "决策最大输出",
                "description": "截图决策的最大 tokens",
            },
            "validation_temperature": {
                "type": "float",
                "label": "验收温度",
                "description": "用例校验时的温度",
            },
            "validation_max_tokens": {
                "type": "integer",
                "label": "验收最大输出",
                "description": "用例校验的最大 tokens",
            },
        },
    },
    "logging": {
        "title": "日志",
        "description": "控制台与文件日志配置",
        "fields": {
            "level": {
                "type": "enum",
                "label": "日志级别",
                "description": "默认日志级别",
                "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            },
            "log_file": {
                "type": "string",
                "label": "日志文件",
                "description": "日志输出文件路径",
            },
        },
    },
    "use_case_validation": {
        "title": "用例验收",
        "description": "视觉用例验证的默认策略",
        "fields": {
            "default_next_actions": {
                "type": "json",
                "label": "默认下一步动作",
                "description": "返回给 LLM/流程控制器的动作优先级，JSON 数组格式",
            },
            "strict_json": {
                "type": "boolean",
                "label": "严格 JSON",
                "description": "提示模型只返回 JSON",
            },
            "include_evidence": {
                "type": "boolean",
                "label": "要求证据",
                "description": "提示模型附带截图可见证据",
            },
        },
    },
    "platforms": {
        "title": "平台",
        "description": "不同 IM 平台的入口、登录方式和关键选择器",
        "subsections": {
            "whatsapp": {
                "title": "WhatsApp",
                "fields": {
                    "name": {"type": "string", "label": "显示名称", "description": "平台名称"},
                    "url": {"type": "string", "label": "入口地址", "description": "打开网页时使用的 URL"},
                    "login_method": {"type": "string", "label": "登录方式", "description": "如 qr_code、phone_code"},
                    "login_wait": {"type": "integer", "label": "建议登录等待", "description": "平台建议登录等待秒数"},
                    "selectors": {"type": "json", "label": "选择器", "description": "关键 DOM 选择器，JSON 对象格式"},
                    "tips": {"type": "json", "label": "使用提示", "description": "平台提示列表，JSON 数组格式"},
                },
            },
            "telegram": {
                "title": "Telegram",
                "fields": {
                    "name": {"type": "string", "label": "显示名称", "description": "平台名称"},
                    "url": {"type": "string", "label": "入口地址", "description": "打开网页时使用的 URL"},
                    "login_method": {"type": "string", "label": "登录方式", "description": "如 qr_code、phone_code"},
                    "login_wait": {"type": "integer", "label": "建议登录等待", "description": "平台建议登录等待秒数"},
                    "selectors": {"type": "json", "label": "选择器", "description": "关键 DOM 选择器，JSON 对象格式"},
                    "tips": {"type": "json", "label": "使用提示", "description": "平台提示列表，JSON 数组格式"},
                },
            },
        },
    },
}


def _deep_merge(defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并配置，保留默认结构"""
    merged = copy.deepcopy(defaults)
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class ConfigManager:
    """配置文件管理器"""

    def __init__(self, path: Path, default_config: Dict[str, Any], schema: Dict[str, Any]):
        self.path = path
        self.default_config = copy.deepcopy(default_config)
        self.schema = copy.deepcopy(schema)

    def load(self) -> Dict[str, Any]:
        """加载配置，不存在时自动写入默认配置"""
        if not self.path.exists():
            config = copy.deepcopy(self.default_config)
            self.save(config)
            return config

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except (json.JSONDecodeError, OSError):
            current = {}

        config = _deep_merge(self.default_config, current)
        if config != current:
            self.save(config)
        return config

    def save(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """保存配置，同时用默认值补齐结构"""
        normalized = _deep_merge(self.default_config, config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        return normalized

    def reset(self) -> Dict[str, Any]:
        """重置为默认配置"""
        return self.save(copy.deepcopy(self.default_config))

    def get_schema(self) -> Dict[str, Any]:
        """获取配置 Schema"""
        return copy.deepcopy(self.schema)


config_manager = ConfigManager(CONFIG_FILE, DEFAULT_APP_CONFIG, CONFIG_SCHEMA)


def get_app_config(refresh: bool = True) -> Dict[str, Any]:
    """获取当前配置"""
    if refresh:
        return config_manager.load()
    return copy.deepcopy(APP_CONFIG)


def save_app_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """保存配置并刷新全局快照"""
    global APP_CONFIG
    APP_CONFIG = config_manager.save(config)
    return copy.deepcopy(APP_CONFIG)


def reset_app_config() -> Dict[str, Any]:
    """重置配置"""
    global APP_CONFIG
    APP_CONFIG = config_manager.reset()
    return copy.deepcopy(APP_CONFIG)


def get_config_schema() -> Dict[str, Any]:
    """获取配置元数据"""
    return config_manager.get_schema()


def resolve_kimi_api_key(config: Optional[Dict[str, Any]] = None) -> str:
    """环境变量优先，其次配置文件"""
    cfg = config or get_app_config()
    return os.getenv("KIMI_API_KEY", cfg["api"].get("kimi_api_key", ""))


def get_platform_settings(platform_name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """获取指定平台配置"""
    cfg = config or get_app_config()
    platforms = cfg.get("platforms", {})
    return copy.deepcopy(platforms.get(platform_name, {}))


def validate_config(config: Optional[Dict[str, Any]] = None):
    """验证配置是否完整"""
    cfg = config or get_app_config()
    errors = []

    if not resolve_kimi_api_key(cfg):
        errors.append("KIMI_API_KEY 未设置，请在环境变量或配置中心中填写")

    if errors:
        raise ValueError("\n".join(errors))

    return True


# 兼容旧代码的常量快照
APP_CONFIG = config_manager.load()
KIMI_API_KEY = resolve_kimi_api_key(APP_CONFIG)
KIMI_BASE_URL = APP_CONFIG["api"]["kimi_base_url"]
KIMI_VISION_MODEL = APP_CONFIG["api"]["kimi_vision_model"]
KIMI_TEXT_MODEL = APP_CONFIG["api"]["kimi_text_model"]

DEFAULT_MAX_STEPS = APP_CONFIG["runtime"]["max_steps"]
DEFAULT_STEP_DELAY = APP_CONFIG["runtime"]["step_delay"]
DEFAULT_LOGIN_TIMEOUT = APP_CONFIG["runtime"]["login_timeout"]

LOG_LEVEL = os.getenv("LOG_LEVEL", APP_CONFIG["logging"]["level"])
LOG_FILE = Path(APP_CONFIG["logging"]["log_file"])

BROWSER_TIMEOUT = APP_CONFIG["browser"]["timeout"]
BROWSER_HEADLESS = APP_CONFIG["browser"]["headless"]
