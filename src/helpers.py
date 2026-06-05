#!/usr/bin/env python3
"""
工具函数
"""
import json
import re
from typing import Optional, Dict, Any


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


def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def normalize_temperature(temperature: float, model: str = "") -> float:
    """
    根据模型名称规范化 temperature 参数。

    某些模型（如 Kimi）对 temperature 的处理与其他模型不同，
    需要特殊处理。
    """
    model_name = model.lower()
    if model_name.startswith("kimi-"):
        return 1
    return temperature
