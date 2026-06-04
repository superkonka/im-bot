#!/usr/bin/env python3
"""
日志工具
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class Logger:
    """简单的彩色日志记录器"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m',     # 重置
    }
    
    def __init__(self, name: str = "IMBot", log_file: Optional[Path] = None):
        self.name = name
        self.log_file = log_file
        self.levels = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}
        self.level = 'INFO'
        
    def set_level(self, level: str):
        """设置日志级别"""
        self.level = level.upper()
        
    def _log(self, level: str, message: str, color: str = None):
        """记录日志"""
        if self.levels.get(level, 20) < self.levels.get(self.level, 20):
            return
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] [{self.name}] {message}"
        
        # 控制台输出（带颜色）
        color_code = color or self.COLORS.get(level, '')
        reset_code = self.COLORS['RESET']
        print(f"{color_code}{log_message}{reset_code}", file=sys.stdout if level != 'ERROR' else sys.stderr)
        
        # 文件输出（无颜色）
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
    
    def debug(self, message: str):
        self._log('DEBUG', message)
        
    def info(self, message: str):
        self._log('INFO', message)
        
    def warning(self, message: str):
        self._log('WARNING', message)
        
    def error(self, message: str):
        self._log('ERROR', message)
        
    def critical(self, message: str):
        self._log('CRITICAL', message)
        
    def banner(self, message: str):
        """打印横幅"""
        width = 60
        print(f"\n{'=' * width}")
        print(f"  {message}")
        print(f"{'=' * width}\n")


# 全局日志实例
logger = Logger()
