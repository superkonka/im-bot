#!/usr/bin/env python3
"""
Kimi 视觉代理 - 分析截图并决策
"""
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from openai import OpenAI

from .utils.logger import logger
from .utils.helpers import encode_image_to_base64, extract_json_from_text, CircularBuffer
from .config import get_app_config, resolve_kimi_api_key
from .use_cases import UseCaseDefinition, UseCaseValidationResult


class ActionDecision:
    """操作决策"""
    
    # 有效操作类型
    VALID_ACTIONS = ['open', 'click', 'input', 'type', 'state', 'wait', 'done', 'scroll', 'back']
    
    def __init__(self, action: str, params: Dict[str, Any], reason: str, confidence: float = 1.0):
        self.action = action
        self.params = params
        self.reason = reason
        self.confidence = confidence
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActionDecision':
        """从字典创建"""
        return cls(
            action=data.get('action', 'wait'),
            params=data.get('params', {}),
            reason=data.get('reason', ''),
            confidence=data.get('confidence', 1.0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            'action': self.action,
            'params': self.params,
            'reason': self.reason,
            'confidence': self.confidence
        }
    
    def is_valid(self) -> bool:
        """检查决策是否有效"""
        return self.action in self.VALID_ACTIONS
    
    def __repr__(self):
        return f"ActionDecision({self.action}, {self.params}, {self.reason[:30]}...)"


class KimiVisionAgent:
    """Kimi 视觉代理"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_history: int = 15,
        client: Optional[OpenAI] = None
    ):
        app_config = get_app_config()
        vision_config = app_config["vision"]
        api_config = app_config["api"]

        resolved_max_history = max_history if max_history != 15 else vision_config["max_history"]
        self.api_key = api_key or resolve_kimi_api_key(app_config)
        self.base_url = api_config["kimi_base_url"]
        self.vision_model = api_config["kimi_vision_model"]
        self.decision_temperature = vision_config["decision_temperature"]
        self.decision_max_tokens = vision_config["decision_max_tokens"]
        self.validation_temperature = vision_config["validation_temperature"]
        self.validation_max_tokens = vision_config["validation_max_tokens"]

        self.client = client or OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.history = CircularBuffer(max_size=resolved_max_history)
        self.system_prompt = ""
        
    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self.system_prompt = prompt
        
    def analyze_screenshot(
        self, 
        screenshot_path: str,
        context: str = "",
        temperature: float = 0.2
    ) -> ActionDecision:
        """
        分析截图并返回决策
        
        Args:
            screenshot_path: 截图文件路径
            context: 额外上下文信息
            temperature: 温度参数
            
        Returns:
            ActionDecision: 操作决策
        """
        resolved_temperature = temperature if temperature != 0.2 else self.decision_temperature
        try:
            # 编码图片
            base64_image = encode_image_to_base64(screenshot_path)
            
            # 构建消息
            messages = self._build_messages(base64_image, context)
            
            # 调用 Kimi API
            logger.debug("调用 Kimi API 分析截图...")
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                temperature=self._normalize_temperature(resolved_temperature),
                max_tokens=self.decision_max_tokens
            )
            
            content = response.choices[0].message.content
            logger.debug(f"Kimi 响应: {content[:200]}...")
            
            # 解析 JSON
            data = extract_json_from_text(content)
            
            if data is None:
                logger.warning("无法从响应中提取 JSON，使用默认决策")
                return ActionDecision(
                    action='wait',
                    params={'seconds': 3},
                    reason='Failed to parse JSON from response'
                )
            
            decision = ActionDecision.from_dict(data)
            
            # 更新历史
            self._update_history(screenshot_path, decision)
            
            return decision
            
        except Exception as e:
            logger.error(f"分析截图失败: {e}")
            return ActionDecision(
                action='wait',
                params={'seconds': 5},
                reason=f'Error: {str(e)}'
            )
    
    def check_login_status(self, screenshot_path: str, platform_name: str) -> tuple[bool, str]:
        """
        检查登录状态
        
        Returns:
            (是否已登录, 提示信息)
        """
        try:
            base64_image = encode_image_to_base64(screenshot_path)
            
            prompt = f"""分析这张 {platform_name} 网页截图，判断是否已完成登录。

判断标准：
- 如果看到二维码 → 未登录
- 如果看到"用手机扫描二维码" → 未登录
- 如果看到"Log in to Telegram"或手机号输入框 → 未登录
- 如果看到"Enter your phone number" → 未登录
- 如果看到聊天列表、联系人列表、消息区域 → 已登录
- 如果看到输入框可以发送消息 → 已登录

只返回 JSON 格式: {{"logged_in": true/false, "hint": "简短说明"}}"""

            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }],
                temperature=self._normalize_temperature(self.validation_temperature),
                max_tokens=min(self.validation_max_tokens, 300)
            )
            
            content = response.choices[0].message.content
            data = extract_json_from_text(content)
            
            if data:
                return data.get('logged_in', False), data.get('hint', '')
            else:
                return False, "无法判断登录状态"
                
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False, str(e)

    def validate_use_case(
        self,
        screenshot_path: str,
        use_case: Union[UseCaseDefinition, Dict[str, Any]],
        step_name: str = "",
        context: str = "",
        temperature: float = 0.1
    ) -> UseCaseValidationResult:
        """
        根据截图校验预设用例是否通过

        Args:
            screenshot_path: 截图文件路径
            use_case: 用例定义
            step_name: 当前步骤名，可覆盖用例中的 step_name
            context: 额外说明
            temperature: 温度参数

        Returns:
            UseCaseValidationResult: 结构化校验结果
        """
        definition = self._normalize_use_case(use_case)
        current_step = step_name or definition.step_name
        resolved_temperature = temperature if temperature != 0.1 else self.validation_temperature

        try:
            base64_image = encode_image_to_base64(screenshot_path)
            prompt = self._build_use_case_validation_prompt(
                definition=definition,
                step_name=current_step,
                context=context
            )

            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }],
                temperature=self._normalize_temperature(resolved_temperature),
                max_tokens=self.validation_max_tokens
            )

            content = response.choices[0].message.content
            data = extract_json_from_text(content)

            if data is None:
                logger.warning("无法从用例校验响应中提取 JSON，返回 uncertain")
                return UseCaseValidationResult(
                    case_id=definition.case_id,
                    step_name=current_step,
                    status="uncertain",
                    confidence=0.0,
                    reason="Failed to parse JSON from response",
                    next_action="review"
                )

            data.setdefault("case_id", definition.case_id)
            data.setdefault("step_name", current_step)
            data.setdefault("next_action", "review")
            data.setdefault("status", "uncertain")
            return UseCaseValidationResult.from_dict(data)

        except Exception as e:
            logger.error(f"用例校验失败: {e}")
            return UseCaseValidationResult(
                case_id=definition.case_id,
                step_name=current_step,
                status="uncertain",
                confidence=0.0,
                reason=f"Error: {str(e)}",
                next_action="review"
            )
    
    def _build_messages(self, base64_image: str, context: str) -> List[Dict]:
        """构建消息列表"""
        messages = []
        
        # 系统提示词
        if self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })
        
        # 历史记录
        for item in self.history:
            messages.append(item)
        
        # 当前请求
        user_content = [
            {
                "type": "text",
                "text": f"当前时间: {datetime.now().strftime('%H:%M:%S')}\n"
                       f"{context}\n"
                       f"请分析截图，返回操作决策。JSON 格式: "
                       f"{{\"action\": \"...\", \"params\": {{...}}, \"reason\": \"...\", \"confidence\": 0.9}}"
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
            }
        ]
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        return messages
    
    def _update_history(self, screenshot_path: str, decision: ActionDecision):
        """更新历史记录"""
        self.history.append({
            "role": "user",
            "content": "Screenshot analyzed"
        })
        self.history.append({
            "role": "assistant",
            "content": json.dumps(decision.to_dict(), ensure_ascii=False)
        })

    def _normalize_use_case(
        self,
        use_case: Union[UseCaseDefinition, Dict[str, Any]]
    ) -> UseCaseDefinition:
        """将输入统一转成用例定义"""
        if isinstance(use_case, UseCaseDefinition):
            return use_case
        return UseCaseDefinition.from_dict(use_case)

    def _normalize_temperature(self, temperature: float) -> float:
        """兼容不同模型的温度参数要求"""
        model_name = (self.vision_model or "").lower()
        if model_name.startswith("kimi-"):
            return 1
        return temperature

    def _build_use_case_validation_prompt(
        self,
        definition: UseCaseDefinition,
        step_name: str,
        context: str
    ) -> str:
        """构建视觉用例校验提示词"""
        sections = [
            "你是一个严谨的视觉测试验收员。",
            "请只根据截图判断当前测试用例是否通过，不要假设截图之外的信息。",
            "",
            f"用例ID: {definition.case_id}",
            f"用例名称: {definition.name}",
            f"当前步骤: {step_name or '未指定'}",
        ]

        if definition.objective:
            sections.append(f"测试目标: {definition.objective}")

        if definition.preconditions:
            sections.append("前置条件:")
            sections.extend(f"- {item}" for item in definition.preconditions)

        if definition.pass_criteria:
            sections.append("通过标准:")
            sections.extend(f"- {item}" for item in definition.pass_criteria)

        if definition.fail_criteria:
            sections.append("失败标准:")
            sections.extend(f"- {item}" for item in definition.fail_criteria)

        if definition.allowed_next_actions:
            sections.append("允许的下一步动作:")
            sections.extend(f"- {item}" for item in definition.allowed_next_actions)

        if definition.notes:
            sections.append("补充说明:")
            sections.extend(f"- {item}" for item in definition.notes)

        if context:
            sections.append(f"补充上下文: {context}")

        sections.extend([
            "",
            "输出要求:",
            "- 只能返回 JSON",
            '- status 只能是 "pass"、"fail"、"uncertain"',
            "- confidence 是 0 到 1 的小数",
            "- matched_rules 填满足的通过/失败规则",
            "- failed_rules 填未满足的关键规则",
            "- evidence 填截图中可观察到的证据",
            '- next_action 优先使用: "proceed"、"retry"、"review"、"stop"',
            "",
            "返回格式:",
            "{",
            f'  "case_id": "{definition.case_id}",',
            f'  "step_name": "{step_name}",',
            '  "status": "pass|fail|uncertain",',
            '  "confidence": 0.0,',
            '  "matched_rules": [],',
            '  "failed_rules": [],',
            '  "evidence": [],',
            '  "reason": "",',
            '  "next_action": "review"',
            "}",
        ])

        return "\n".join(sections)
    
    def clear_history(self):
        """清空历史"""
        self.history.clear()
