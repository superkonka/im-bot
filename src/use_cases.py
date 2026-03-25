#!/usr/bin/env python3
"""
视觉用例定义与校验结果
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class UseCaseDefinition:
    """视觉用例定义"""

    case_id: str
    name: str
    objective: str = ""
    preconditions: List[str] = field(default_factory=list)
    pass_criteria: List[str] = field(default_factory=list)
    fail_criteria: List[str] = field(default_factory=list)
    allowed_next_actions: List[str] = field(default_factory=list)
    step_name: str = ""
    notes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UseCaseDefinition":
        """从字典创建用例定义"""
        return cls(
            case_id=data.get("case_id", ""),
            name=data.get("name", ""),
            objective=data.get("objective", ""),
            preconditions=list(data.get("preconditions", [])),
            pass_criteria=list(data.get("pass_criteria", [])),
            fail_criteria=list(data.get("fail_criteria", [])),
            allowed_next_actions=list(data.get("allowed_next_actions", [])),
            step_name=data.get("step_name", ""),
            notes=list(data.get("notes", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "case_id": self.case_id,
            "name": self.name,
            "objective": self.objective,
            "preconditions": self.preconditions,
            "pass_criteria": self.pass_criteria,
            "fail_criteria": self.fail_criteria,
            "allowed_next_actions": self.allowed_next_actions,
            "step_name": self.step_name,
            "notes": self.notes,
        }


@dataclass
class UseCaseValidationResult:
    """视觉用例校验结果"""

    case_id: str
    step_name: str = ""
    status: str = "uncertain"
    confidence: float = 0.0
    matched_rules: List[str] = field(default_factory=list)
    failed_rules: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    reason: str = ""
    next_action: str = "review"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UseCaseValidationResult":
        """从字典创建校验结果"""
        return cls(
            case_id=data.get("case_id", ""),
            step_name=data.get("step_name", ""),
            status=data.get("status", "uncertain"),
            confidence=float(data.get("confidence", 0.0)),
            matched_rules=list(data.get("matched_rules", [])),
            failed_rules=list(data.get("failed_rules", [])),
            evidence=list(data.get("evidence", [])),
            reason=data.get("reason", ""),
            next_action=data.get("next_action", "review"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "case_id": self.case_id,
            "step_name": self.step_name,
            "status": self.status,
            "confidence": self.confidence,
            "matched_rules": self.matched_rules,
            "failed_rules": self.failed_rules,
            "evidence": self.evidence,
            "reason": self.reason,
            "next_action": self.next_action,
        }
