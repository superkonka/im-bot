#!/usr/bin/env python3
"""
Telegram 运行时控制与后台面板共享的数据结构
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATA_DIR


@dataclass
class RuntimeMessage:
    """运行时消息记录"""

    role: str
    text: str
    timestamp: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeMessage":
        return cls(
            role=str(data.get("role", "")).strip(),
            text=str(data.get("text", "")).strip(),
            timestamp=str(data.get("timestamp", "")).strip(),
        )


@dataclass
class PendingDraft:
    """待人工处理的消息草稿"""

    draft_id: str
    mode: str
    topic: str
    message: str
    reason: str
    created_at: str
    risk: str = "low"
    confidence: float = 0.0
    proactive: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PendingDraft":
        return cls(
            draft_id=str(data.get("draft_id", "")).strip(),
            mode=str(data.get("mode", "")).strip(),
            topic=str(data.get("topic", "")).strip(),
            message=str(data.get("message", "")).strip(),
            reason=str(data.get("reason", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            risk=str(data.get("risk", "low")).strip(),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            proactive=bool(data.get("proactive", False)),
        )


@dataclass
class RuntimeDashboard:
    """后台运行时状态"""

    session_name: str
    target_chat: str
    transport: str = "user"
    lock_mode: str = ""
    locked: bool = False
    locked_chat_title: str = ""
    last_locked_at: str = ""
    memory_summary: str = ""
    memory_file: str = ""
    status: str = "idle"
    automation_paused: bool = False
    proactive_paused: bool = False
    manual_review_enabled: bool = False
    last_error: str = ""
    last_decision: str = ""
    last_updated_at: str = ""
    recent_messages: List[RuntimeMessage] = field(default_factory=list)
    pending_draft: Optional[PendingDraft] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeDashboard":
        return cls(
            session_name=str(data.get("session_name", "")).strip(),
            target_chat=str(data.get("target_chat", "")).strip(),
            transport=str(data.get("transport", "user")).strip() or "user",
            lock_mode=str(data.get("lock_mode", "")).strip(),
            locked=bool(data.get("locked", False)),
            locked_chat_title=str(data.get("locked_chat_title", "")).strip(),
            last_locked_at=str(data.get("last_locked_at", "")).strip(),
            memory_summary=str(data.get("memory_summary", "")).strip(),
            memory_file=str(data.get("memory_file", "")).strip(),
            status=str(data.get("status", "idle")).strip(),
            automation_paused=bool(data.get("automation_paused", False)),
            proactive_paused=bool(data.get("proactive_paused", False)),
            manual_review_enabled=bool(data.get("manual_review_enabled", False)),
            last_error=str(data.get("last_error", "")).strip(),
            last_decision=str(data.get("last_decision", "")).strip(),
            last_updated_at=str(data.get("last_updated_at", "")).strip(),
            recent_messages=[
                RuntimeMessage.from_dict(item)
                for item in data.get("recent_messages", [])
                if isinstance(item, dict)
            ],
            pending_draft=PendingDraft.from_dict(data["pending_draft"])
            if isinstance(data.get("pending_draft"), dict)
            else None,
        )

    def note_message(self, role: str, text: str, timestamp: str) -> None:
        self.recent_messages.append(RuntimeMessage(role=role, text=text, timestamp=timestamp))
        self.recent_messages = self.recent_messages[-50:]
        self.last_updated_at = datetime.now().isoformat()


@dataclass
class OperatorCommand:
    """后台发给 bot 的控制命令"""

    command_id: str
    action: str
    created_at: str
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperatorCommand":
        return cls(
            command_id=str(data.get("command_id", "")).strip(),
            action=str(data.get("action", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            payload=dict(data.get("payload", {})),
        )


@dataclass
class OperatorControlState:
    """运行时控制面板状态"""

    automation_paused: bool = False
    proactive_paused: bool = False
    commands: List[OperatorCommand] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperatorControlState":
        return cls(
            automation_paused=bool(data.get("automation_paused", False)),
            proactive_paused=bool(data.get("proactive_paused", False)),
            commands=[
                OperatorCommand.from_dict(item)
                for item in data.get("commands", [])
                if isinstance(item, dict)
            ],
        )


class JsonStore:
    """简单 JSON 文件存储"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_dict(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_dict(self, data: Dict[str, Any]) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class RuntimeDashboardStore(JsonStore):
    """运行时后台状态存储"""

    def load(self, session_name: str = "", target_chat: str = "") -> RuntimeDashboard:
        data = self._read_dict()
        dashboard = RuntimeDashboard.from_dict(data)
        if session_name and not dashboard.session_name:
            dashboard.session_name = session_name
        if target_chat and not dashboard.target_chat:
            dashboard.target_chat = target_chat
        return dashboard

    def save(self, dashboard: RuntimeDashboard) -> None:
        self._write_dict(asdict(dashboard))


class OperatorControlStore(JsonStore):
    """控制命令存储"""

    def load(self) -> OperatorControlState:
        return OperatorControlState.from_dict(self._read_dict())

    def save(self, control: OperatorControlState) -> None:
        self._write_dict(asdict(control))

    def set_paused(self, paused: bool) -> OperatorControlState:
        control = self.load()
        control.automation_paused = paused
        self.save(control)
        return control

    def set_proactive_paused(self, paused: bool) -> OperatorControlState:
        control = self.load()
        control.proactive_paused = paused
        self.save(control)
        return control

    def append_command(self, action: str, payload: Optional[Dict[str, Any]] = None) -> OperatorCommand:
        control = self.load()
        command = OperatorCommand(
            command_id=f"{action}:{datetime.now().timestamp()}",
            action=action,
            created_at=datetime.now().isoformat(),
            payload=payload or {},
        )
        control.commands.append(command)
        self.save(control)
        return command

    def pop_commands(self) -> tuple[bool, bool, List[OperatorCommand]]:
        control = self.load()
        commands = list(control.commands)
        control.commands = []
        self.save(control)
        return control.automation_paused, control.proactive_paused, commands


def get_runtime_store_paths(session_name: str) -> tuple[Path, Path]:
    """获取 runtime/control 文件路径"""
    base = DATA_DIR / "telegram_sessions"
    return (
        base / f"{session_name}_runtime.json",
        base / f"{session_name}_control.json",
    )
