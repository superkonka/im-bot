#!/usr/bin/env python3
"""
技能层（Skill Layer）

将外部能力（IM 平台、数据库、支付等）封装为 Agent 可调用的工具接口。
每个 Skill 都是独立的异步模块，遵循统一的调用契约。
"""

from .telegram import TelegramSkill

__all__ = ["TelegramSkill"]
