#!/usr/bin/env python3
"""
平台基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable


@dataclass
class PlatformConfig:
    """平台配置"""
    name: str
    url: str
    login_method: str  # qr_code, phone_code, password, etc.
    login_wait: int  # 等待登录时间（秒）
    selectors: Dict[str, str]
    tips: List[str]


class BasePlatform(ABC):
    """平台基类"""
    
    def __init__(self):
        self.config: PlatformConfig = self._get_config()
        
    @abstractmethod
    def _get_config(self) -> PlatformConfig:
        """获取平台配置"""
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        pass
    
    @abstractmethod
    def generate_reply(self, message: str) -> str:
        """生成回复"""
        pass
    
    def get_welcome_message(self) -> str:
        """获取欢迎消息"""
        return f"欢迎使用 {self.config.name} 机器人！\n" + "\n".join(f"• {tip}" for tip in self.config.tips)
