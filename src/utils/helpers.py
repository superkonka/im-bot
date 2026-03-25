#!/usr/bin/env python3
"""
工具函数
"""
import base64
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any


def encode_image_to_base64(image_path: str) -> str:
    """将图片转为 base64 字符串"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """从文本中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    
    # 尝试从 markdown 代码块中提取
    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\{.*\}',  # 最宽松的匹配
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
    
    return None


def sanitize_text_for_shell(text: str) -> str:
    """转义 shell 特殊字符"""
    # 转义双引号和反斜杠
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`')


def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


class CircularBuffer:
    """循环缓冲区，用于存储历史记录"""
    
    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self.buffer = []
        
    def append(self, item):
        """添加元素"""
        self.buffer.append(item)
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)
    
    def get_all(self):
        """获取所有元素"""
        return self.buffer.copy()
    
    def clear(self):
        """清空缓冲区"""
        self.buffer = []
    
    def __len__(self):
        return len(self.buffer)
    
    def __iter__(self):
        return iter(self.buffer)
