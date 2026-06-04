#!/usr/bin/env python3
"""
Telegram 用户账号自动对话引擎

- 使用 Telethon 连接用户自己的 Telegram 账号
- 使用 LLM 生成受控的被动回复与主动对话草稿
- 使用本地策略约束话题、频率与时间窗口
"""
import asyncio
import contextlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from core.config import (
    DATA_DIR,
    get_app_config,
    resolve_kimi_api_key,
    resolve_telegram_api_hash,
    resolve_telegram_api_id,
    save_app_config,
)
from agent.runtime_control import (
    OperatorControlStore,
    PendingDraft,
    RuntimeDashboard,
    RuntimeDashboardStore,
    get_runtime_store_paths,
)
from .utils.helpers import extract_json_from_text, truncate_string
from core.logger import logger

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


@dataclass
class ConversationTurn:
    """对话轮次"""

    role: str
    text: str
    timestamp: str


@dataclass
class DialogChoice:
    """用于交互选择的聊天候选项"""

    title: str
    username: str = ""
    dialog_id: int = 0

    def target_value(self) -> str:
        if self.username:
            return self.username
        if self.dialog_id:
            return str(self.dialog_id)
        return self.title

    def display_label(self) -> str:
        if self.username:
            return f"{self.title} (@{self.username})"
        if self.dialog_id:
            return f"{self.title} (id={self.dialog_id})"
        return self.title


@dataclass
class ProactiveSettings:
    """主动对话配置"""

    enabled: bool = True
    cooldown_minutes: int = 240
    min_idle_since_incoming_minutes: int = 180
    max_daily_initiations: int = 3
    active_hours_start: int = 9
    active_hours_end: int = 21
    poll_interval_seconds: int = 90
    reply_delay_seconds: int = 3


@dataclass
class SafetyReviewSettings:
    """发送前二次审核配置"""

    enabled: bool = True
    max_risk: str = "medium"
    minimum_confidence: float = 0.55
    block_if_topic_missing: bool = True


@dataclass
class TelegramUserSettings:
    """Telegram 用户账号配置"""

    api_id: int
    api_hash: str
    session_name: str
    phone_number: str
    target_chat: str
    timezone_name: str
    history_limit: int
    max_message_chars: int
    persona: str
    relationship_context: str
    response_style: str
    allowed_topics: List[str] = field(default_factory=list)
    blocked_topics: List[str] = field(default_factory=list)
    proactive: ProactiveSettings = field(default_factory=ProactiveSettings)
    safety_review: SafetyReviewSettings = field(default_factory=SafetyReviewSettings)
    manual_review: bool = False
    dry_run: bool = False

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "TelegramUserSettings":
        cfg = config or get_app_config()
        tg = cfg.get("telegram_user", {})
        proactive = tg.get("proactive", {})
        safety_review = tg.get("safety_review", {})

        api_id_raw = resolve_telegram_api_id(cfg)
        api_hash = resolve_telegram_api_hash(cfg)

        if not api_id_raw:
            raise ValueError("TELEGRAM_API_ID 未设置，请在环境变量或配置中心中填写")
        if not api_hash:
            raise ValueError("TELEGRAM_API_HASH 未设置，请在环境变量或配置中心中填写")

        return cls(
            api_id=int(api_id_raw),
            api_hash=api_hash,
            session_name=tg.get("session_name", "telegram_user"),
            phone_number=tg.get("phone_number", "").strip(),
            target_chat=tg.get("target_chat", "").strip(),
            timezone_name=tg.get("timezone_name", "Asia/Shanghai"),
            history_limit=int(tg.get("history_limit", 20)),
            max_message_chars=int(tg.get("max_message_chars", 180)),
            persona=tg.get("persona", "").strip(),
            relationship_context=tg.get("relationship_context", "").strip(),
            response_style=tg.get("response_style", "").strip(),
            allowed_topics=[item.strip() for item in tg.get("allowed_topics", []) if str(item).strip()],
            blocked_topics=[item.strip() for item in tg.get("blocked_topics", []) if str(item).strip()],
            proactive=ProactiveSettings(
                enabled=bool(proactive.get("enabled", True)),
                cooldown_minutes=int(proactive.get("cooldown_minutes", 240)),
                min_idle_since_incoming_minutes=int(proactive.get("min_idle_since_incoming_minutes", 180)),
                max_daily_initiations=int(proactive.get("max_daily_initiations", 3)),
                active_hours_start=int(proactive.get("active_hours_start", 9)),
                active_hours_end=int(proactive.get("active_hours_end", 21)),
                poll_interval_seconds=int(proactive.get("poll_interval_seconds", 90)),
                reply_delay_seconds=int(proactive.get("reply_delay_seconds", 3)),
            ),
            safety_review=SafetyReviewSettings(
                enabled=bool(safety_review.get("enabled", True)),
                max_risk=str(safety_review.get("max_risk", "medium")).strip() or "medium",
                minimum_confidence=float(safety_review.get("minimum_confidence", 0.55) or 0.55),
                block_if_topic_missing=bool(safety_review.get("block_if_topic_missing", True)),
            ),
            manual_review=bool(tg.get("manual_review", False)),
            dry_run=bool(tg.get("dry_run", False)),
        )


@dataclass
class ConversationState:
    """会话状态"""

    last_incoming_at: str = ""
    last_outgoing_at: str = ""
    last_proactive_at: str = ""
    last_outgoing_text: str = ""
    last_decision_at: str = ""
    last_topic: str = ""
    last_processed_incoming_id: int = 0
    daily_initiation_counts: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        return cls(
            last_incoming_at=data.get("last_incoming_at", ""),
            last_outgoing_at=data.get("last_outgoing_at", ""),
            last_proactive_at=data.get("last_proactive_at", ""),
            last_outgoing_text=data.get("last_outgoing_text", ""),
            last_decision_at=data.get("last_decision_at", ""),
            last_topic=data.get("last_topic", ""),
            last_processed_incoming_id=int(data.get("last_processed_incoming_id", 0) or 0),
            daily_initiation_counts=dict(data.get("daily_initiation_counts", {})),
        )

    def touch_incoming(self, when: datetime) -> None:
        self.last_incoming_at = when.isoformat()

    def touch_outgoing(self, when: datetime, text: str, proactive: bool) -> None:
        self.last_outgoing_at = when.isoformat()
        self.last_outgoing_text = text.strip()
        if proactive:
            self.last_proactive_at = when.isoformat()
            day_key = when.date().isoformat()
            self.daily_initiation_counts[day_key] = self.daily_initiation_counts.get(day_key, 0) + 1


@dataclass
class ConversationMemory:
    """长期记忆"""

    relationship_summary: str = ""
    salient_facts: List[str] = field(default_factory=list)
    open_loops: List[str] = field(default_factory=list)
    recent_topics: List[str] = field(default_factory=list)
    interaction_notes: List[str] = field(default_factory=list)
    last_refreshed_at: str = ""
    source_message_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMemory":
        return cls(
            relationship_summary=str(data.get("relationship_summary", "")).strip(),
            salient_facts=[str(item).strip() for item in data.get("salient_facts", []) if str(item).strip()],
            open_loops=[str(item).strip() for item in data.get("open_loops", []) if str(item).strip()],
            recent_topics=[str(item).strip() for item in data.get("recent_topics", []) if str(item).strip()],
            interaction_notes=[str(item).strip() for item in data.get("interaction_notes", []) if str(item).strip()],
            last_refreshed_at=str(data.get("last_refreshed_at", "")).strip(),
            source_message_count=int(data.get("source_message_count", 0) or 0),
        )

    def note_topic(self, topic: str) -> None:
        normalized = topic.strip()
        if not normalized:
            return
        self.recent_topics = [item for item in self.recent_topics if item != normalized]
        self.recent_topics.append(normalized)
        self.recent_topics = self.recent_topics[-6:]

    def note_interaction(self, note: str) -> None:
        normalized = note.strip()
        if not normalized:
            return
        self.interaction_notes.append(normalized)
        self.interaction_notes = self.interaction_notes[-10:]


@dataclass
class ConversationJob:
    """队列里的串行处理任务"""

    job_id: str
    mode: str
    created_at: str
    latest_partner_message: str = ""
    message_id: int = 0


@dataclass
class ConversationDecision:
    """模型输出的结构化决策"""

    action: str
    topic: str
    message: str
    reason: str
    confidence: float = 0.0
    risk: str = "low"

    @classmethod
    def hold(cls, reason: str) -> "ConversationDecision":
        return cls(
            action="hold",
            topic="",
            message="",
            reason=reason,
            confidence=0.0,
            risk="low",
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationDecision":
        return cls(
            action=str(data.get("action", "hold")).strip(),
            topic=str(data.get("topic", "")).strip(),
            message=str(data.get("message", "")).strip(),
            reason=str(data.get("reason", "")).strip(),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            risk=str(data.get("risk", "low")).strip(),
        )


@dataclass
class SafetyReviewResult:
    """发送前审核结果"""

    allow: bool
    reason: str
    risk: str = "low"
    confidence: float = 0.0
    suggested_message: str = ""

    @classmethod
    def allow_result(cls, reason: str, risk: str = "low", confidence: float = 1.0) -> "SafetyReviewResult":
        return cls(
            allow=True,
            reason=reason,
            risk=risk,
            confidence=confidence,
            suggested_message="",
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SafetyReviewResult":
        return cls(
            allow=bool(data.get("allow", False)),
            reason=str(data.get("reason", "")).strip(),
            risk=str(data.get("risk", "low")).strip(),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            suggested_message=str(data.get("suggested_message", "")).strip(),
        )


class ConversationStateStore:
    """会话状态持久化"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ConversationState:
        if not self.path.exists():
            return ConversationState()

        try:
            return ConversationState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return ConversationState()

    def save(self, state: ConversationState) -> None:
        self.path.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class ConversationMemoryStore:
    """长期记忆持久化"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ConversationMemory:
        if not self.path.exists():
            return ConversationMemory()

        try:
            return ConversationMemory.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return ConversationMemory()

    def save(self, memory: ConversationMemory) -> None:
        self.path.write_text(
            json.dumps(asdict(memory), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class ConversationGuard:
    """会话守卫：控制主动频率、话题边界和草稿合法性"""

    def __init__(self, settings: TelegramUserSettings):
        self.settings = settings
        self.allowed_topics = {item.lower(): item for item in settings.allowed_topics}
        self.blocked_topics = [item.lower() for item in settings.blocked_topics]

    def can_initiate(self, now: datetime, state: ConversationState) -> tuple[bool, str]:
        proactive = self.settings.proactive
        if not proactive.enabled:
            return False, "主动对话已关闭"

        if not self._is_active_hour(now):
            return False, "当前不在允许主动发起的时间窗口"

        if not state.last_incoming_at:
            return False, "尚未建立足够的聊天上下文"

        last_incoming = self._parse_dt(state.last_incoming_at)
        if last_incoming and now - last_incoming < timedelta(minutes=proactive.min_idle_since_incoming_minutes):
            return False, "距离对方上次发言时间太短"

        last_proactive = self._parse_dt(state.last_proactive_at)
        if last_proactive and now - last_proactive < timedelta(minutes=proactive.cooldown_minutes):
            return False, "主动发起冷却中"

        day_key = now.date().isoformat()
        if state.daily_initiation_counts.get(day_key, 0) >= proactive.max_daily_initiations:
            return False, "今日主动发起次数已达上限"

        return True, "允许主动发起"

    def validate_decision(
        self,
        decision: ConversationDecision,
        mode: str,
        history: List[ConversationTurn],
        state: ConversationState,
    ) -> ConversationDecision:
        valid_actions = {"reply", "hold"} if mode == "reply" else {"initiate", "hold"}
        if decision.action not in valid_actions:
            return ConversationDecision.hold(f"非法 action: {decision.action}")

        if decision.action == "hold":
            return decision

        if not decision.message:
            return ConversationDecision.hold("消息草稿为空")

        if len(decision.message) > self.settings.max_message_chars:
            return ConversationDecision.hold("消息长度超过限制")

        if self.blocked_topics and self._contains_blocked(decision.message):
            return ConversationDecision.hold("命中了禁止话题关键词")

        if self.allowed_topics and decision.topic.lower() not in self.allowed_topics:
            return ConversationDecision.hold(f"话题不在白名单中: {decision.topic}")

        normalized_message = decision.message.strip()
        if normalized_message == state.last_outgoing_text.strip():
            return ConversationDecision.hold("与上一条外发消息重复")

        recent_outgoing = [
            turn.text.strip()
            for turn in history
            if turn.role == "assistant" and turn.text.strip()
        ]
        if normalized_message in recent_outgoing[-3:]:
            return ConversationDecision.hold("与最近外发消息重复")

        return decision

    def _contains_blocked(self, text: str) -> bool:
        lowered = text.lower()
        return any(topic in lowered for topic in self.blocked_topics)

    def _is_active_hour(self, now: datetime) -> bool:
        start = self.settings.proactive.active_hours_start
        end = self.settings.proactive.active_hours_end
        hour = now.hour
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def _parse_dt(self, value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


class TelegramLLMOrchestrator:
    """围绕受控对话场景构建提示并解析 JSON 输出"""

    def __init__(self, settings: TelegramUserSettings, client: Optional[OpenAI] = None):
        app_config = get_app_config()
        self.settings = settings
        self.model = app_config["api"]["kimi_text_model"]
        self.temperature = 0.3
        api_key = resolve_kimi_api_key(app_config)
        self.client = client or OpenAI(
            api_key=api_key,
            base_url=app_config["api"]["kimi_base_url"],
        )

    def decide_reply(
        self,
        history: List[ConversationTurn],
        latest_partner_message: str,
        now: datetime,
        memory: Optional[ConversationMemory] = None,
    ) -> ConversationDecision:
        return self._decide(
            mode="reply",
            history=history,
            now=now,
            latest_partner_message=latest_partner_message,
            memory=memory,
        )

    def decide_proactive(
        self,
        history: List[ConversationTurn],
        now: datetime,
        memory: Optional[ConversationMemory] = None,
    ) -> ConversationDecision:
        return self._decide(
            mode="initiate",
            history=history,
            now=now,
            latest_partner_message="",
            memory=memory,
        )

    def _decide(
        self,
        mode: str,
        history: List[ConversationTurn],
        now: datetime,
        latest_partner_message: str,
        memory: Optional[ConversationMemory],
    ) -> ConversationDecision:
        prompt = self._build_prompt(
            mode=mode,
            history=history,
            now=now,
            latest_partner_message=latest_partner_message,
            memory=memory,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个克制、可靠的中文聊天编排器，只能输出 JSON。",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self._normalize_temperature(self.temperature),
                max_tokens=900,
            )
            content = response.choices[0].message.content
            data = extract_json_from_text(content or "")
            if data is None:
                logger.warning("LLM 未返回有效 JSON，改为 hold")
                return ConversationDecision.hold("LLM 返回结果无法解析为 JSON")
            return ConversationDecision.from_dict(data)
        except Exception as exc:
            logger.error(f"文本决策失败: {exc}")
            return ConversationDecision.hold(f"LLM 调用失败: {exc}")

    def _build_prompt(
        self,
        mode: str,
        history: List[ConversationTurn],
        now: datetime,
        latest_partner_message: str,
        memory: Optional[ConversationMemory],
    ) -> str:
        action_hint = "reply 或 hold" if mode == "reply" else "initiate 或 hold"
        mode_hint = "收到对方新消息后的回复判断" if mode == "reply" else "定时检查是否应该主动开启话题"
        history_lines = self._render_history(history)
        allowed_topics = self.settings.allowed_topics or ["未设置，视为仅可围绕既有聊天上下文"]
        blocked_topics = self.settings.blocked_topics or ["未设置"]

        return "\n".join([
            f"场景: {mode_hint}",
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} ({self.settings.timezone_name})",
            f"目标聊天对象: {self.settings.target_chat}",
            "",
            "人设与关系设定:",
            self.settings.persona or "未设置",
            self.settings.relationship_context or "未设置",
            f"回复风格: {self.settings.response_style or '自然、克制、像真人'}",
            "",
            "长期记忆:",
            self._render_memory(memory),
            "",
            "允许话题白名单:",
            *[f"- {item}" for item in allowed_topics],
            "禁止话题黑名单:",
            *[f"- {item}" for item in blocked_topics],
            "",
            "严格规则:",
            "- 不能超出允许话题白名单。",
            "- 如果当前没有合适内容，就返回 hold。",
            "- 不能承诺做不到的事情，不能暴露自己是 AI、机器人、脚本。",
            "- 回复必须结合最近聊天记录和当前时间语境。",
            "- 主动发起时，必须显得自然，不要突兀，不要连续追问。",
            f"- 外发消息最长 {self.settings.max_message_chars} 个字符。",
            "",
            "最近聊天记录:",
            history_lines,
            "",
            f"最新对方消息: {latest_partner_message or '无'}",
            "",
            "只返回 JSON，格式如下:",
            "{",
            f'  "action": "{action_hint}",',
            '  "topic": "必须从白名单里选一个；若 hold 则可为空",',
            '  "message": "准备发送的中文消息；若 hold 则为空",',
            '  "reason": "简要说明为什么这样判断",',
            '  "confidence": 0.0,',
            '  "risk": "low|medium|high"',
            "}",
        ])

    def summarize_memory(
        self,
        history: List[ConversationTurn],
        existing_memory: ConversationMemory,
        now: datetime,
    ) -> ConversationMemory:
        if len(history) < 6:
            return existing_memory

        prompt = "\n".join([
            "请根据下面的聊天记录更新长期记忆，只返回 JSON。",
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} ({self.settings.timezone_name})",
            "输出格式:",
            "{",
            '  "relationship_summary": "",',
            '  "salient_facts": [],',
            '  "open_loops": [],',
            '  "recent_topics": []',
            "}",
            "",
            "已有记忆:",
            self._render_memory(existing_memory),
            "",
            "最近聊天记录:",
            self._render_history(history),
            "",
            "要求:",
            "- 用中文，简洁。",
            "- 只保留稳定事实和仍值得延续的话题。",
            "- 不要臆造聊天记录里不存在的信息。",
        ])

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个谨慎的长期记忆整理器，只能输出 JSON。",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self._normalize_temperature(0.2),
                max_tokens=700,
            )
            data = extract_json_from_text(response.choices[0].message.content or "")
            if data is None:
                logger.warning("长期记忆摘要未返回有效 JSON，保留旧记忆")
                return existing_memory

            memory = ConversationMemory.from_dict(data)
            memory.last_refreshed_at = now.isoformat()
            memory.source_message_count = len(history)
            memory.interaction_notes = list(existing_memory.interaction_notes[-10:])
            return memory
        except Exception as exc:
            logger.error(f"长期记忆摘要失败: {exc}")
            return existing_memory

    def _render_history(self, history: List[ConversationTurn]) -> str:
        if not history:
            return "- 暂无历史消息"
        lines = []
        for turn in history[-self.settings.history_limit:]:
            lines.append(f"- [{turn.timestamp}] {turn.role}: {truncate_string(turn.text, 120)}")
        return "\n".join(lines)

    def _render_memory(self, memory: Optional[ConversationMemory]) -> str:
        if not memory:
            return "- 暂无长期记忆"

        parts = [
            f"- 关系摘要: {memory.relationship_summary or '暂无'}",
            f"- 重要事实: {'；'.join(memory.salient_facts) if memory.salient_facts else '暂无'}",
            f"- 未完话题: {'；'.join(memory.open_loops) if memory.open_loops else '暂无'}",
            f"- 最近主题: {'；'.join(memory.recent_topics) if memory.recent_topics else '暂无'}",
            f"- 交互注记: {'；'.join(memory.interaction_notes[-4:]) if memory.interaction_notes else '暂无'}",
        ]
        return "\n".join(parts)

    def _normalize_temperature(self, temperature: float) -> float:
        model_name = (self.model or "").lower()
        if model_name.startswith("kimi-"):
            return 1
        return temperature


class TelegramSafetyReviewer:
    """对即将外发的消息做二次审核"""

    RISK_ORDER = {
        "low": 0,
        "medium": 1,
        "high": 2,
    }

    def __init__(
        self,
        settings: TelegramUserSettings,
        client: Optional[OpenAI] = None,
        helper: Optional[TelegramLLMOrchestrator] = None,
    ):
        app_config = get_app_config()
        self.settings = settings
        self.model = app_config["api"]["kimi_text_model"]
        api_key = resolve_kimi_api_key(app_config)
        self.client = client or OpenAI(
            api_key=api_key,
            base_url=app_config["api"]["kimi_base_url"],
        )
        self.helper = helper or TelegramLLMOrchestrator(settings, client=self.client)

    def review(
        self,
        decision: ConversationDecision,
        mode: str,
        history: List[ConversationTurn],
        memory: ConversationMemory,
        now: datetime,
    ) -> SafetyReviewResult:
        review_settings = self.settings.safety_review
        if not review_settings.enabled:
            return SafetyReviewResult.allow_result("发送审核已关闭")

        if review_settings.block_if_topic_missing and not decision.topic.strip():
            return SafetyReviewResult(
                allow=False,
                reason="缺少明确的话题标签",
                risk="medium",
                confidence=1.0,
            )

        prompt = "\n".join([
            "请审核下面这条即将发送的 Telegram 消息是否允许发出，只返回 JSON。",
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} ({self.settings.timezone_name})",
            f"模式: {mode}",
            f"目标聊天对象: {self.settings.target_chat}",
            f"候选话题: {decision.topic or '无'}",
            f"候选消息: {decision.message}",
            "",
            "人设与关系设定:",
            self.settings.persona or "未设置",
            self.settings.relationship_context or "未设置",
            f"回复风格: {self.settings.response_style or '自然、克制、像真人'}",
            "",
            "允许话题白名单:",
            *[f"- {item}" for item in (self.settings.allowed_topics or ["未设置"])],
            "禁止话题黑名单:",
            *[f"- {item}" for item in (self.settings.blocked_topics or ["未设置"])],
            "",
            "长期记忆:",
            self.helper._render_memory(memory),
            "",
            "最近聊天记录:",
            self.helper._render_history(history),
            "",
            "审核重点:",
            "- 是否超出允许话题白名单。",
            "- 是否过度亲密、突兀、施压、像 AI。",
            "- 是否与最近上下文不连贯。",
            "- 是否存在明显风险。",
            "",
            "只返回 JSON:",
            "{",
            '  "allow": true,',
            '  "reason": "",',
            '  "risk": "low|medium|high",',
            '  "confidence": 0.0,',
            '  "suggested_message": ""',
            "}",
        ])

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个严谨的消息审核器，只能输出 JSON。",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self._normalize_temperature(0.2),
                max_tokens=700,
            )
            data = extract_json_from_text(response.choices[0].message.content or "")
            if data is None:
                return SafetyReviewResult(
                    allow=False,
                    reason="发送审核未返回有效 JSON",
                    risk="high",
                    confidence=0.0,
                )
        except Exception as exc:
            logger.error(f"发送审核失败: {exc}")
            return SafetyReviewResult(
                allow=False,
                reason=f"发送审核失败: {exc}",
                risk="high",
                confidence=0.0,
            )

        result = SafetyReviewResult.from_dict(data)
        max_risk = review_settings.max_risk
        if self.RISK_ORDER.get(result.risk, 2) > self.RISK_ORDER.get(max_risk, 1):
            return SafetyReviewResult(
                allow=False,
                reason=f"审核风险过高: {result.reason or result.risk}",
                risk=result.risk,
                confidence=result.confidence,
                suggested_message=result.suggested_message,
            )

        if result.confidence < review_settings.minimum_confidence:
            return SafetyReviewResult(
                allow=False,
                reason=f"审核置信度过低: {result.confidence:.2f}",
                risk=result.risk,
                confidence=result.confidence,
                suggested_message=result.suggested_message,
            )

        return result

    def _normalize_temperature(self, temperature: float) -> float:
        model_name = (self.model or "").lower()
        if model_name.startswith("kimi-"):
            return 1
        return temperature


class TelegramUserBot:
    """Telegram 用户账号机器人"""

    def __init__(
        self,
        settings: Optional[TelegramUserSettings] = None,
        orchestrator: Optional[TelegramLLMOrchestrator] = None,
        state_store: Optional[ConversationStateStore] = None,
    ):
        self.settings = settings or TelegramUserSettings.from_config()
        self.guard = ConversationGuard(self.settings)
        self.orchestrator = orchestrator or TelegramLLMOrchestrator(self.settings)
        self.reviewer = TelegramSafetyReviewer(
            self.settings,
            client=self.orchestrator.client,
            helper=self.orchestrator,
        )
        state_dir = DATA_DIR / "telegram_sessions"
        self.state_store = state_store or ConversationStateStore(
            state_dir / f"{self.settings.session_name}_state.json"
        )
        self.memory_store = ConversationMemoryStore(
            state_dir / f"{self.settings.session_name}_memory.json"
        )
        runtime_path, control_path = get_runtime_store_paths(self.settings.session_name)
        self.runtime_store = RuntimeDashboardStore(runtime_path)
        self.control_store = OperatorControlStore(control_path)
        self.state = self.state_store.load()
        self.memory = self.memory_store.load()
        self.runtime = self.runtime_store.load(
            session_name=self.settings.session_name,
            target_chat=self.settings.target_chat,
        )
        self.runtime.manual_review_enabled = self.settings.manual_review
        self._client = None
        self._events = None
        self._target_entity = None
        self._target_chat_id = 0
        self._job_queue: asyncio.Queue[ConversationJob] = asyncio.Queue()
        self._pending_job_ids: set[str] = set()
        self._active_job_id = ""
        self._active_job_mode = ""
        self._runtime_paused = False
        self._proactive_paused = False

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._ensure_target_chat()
        await self._connect()
        logger.banner("启动 Telegram 用户账号对话引擎")
        logger.info(f"Session: {self.settings.session_name}")
        logger.info(f"目标聊天: {self.settings.target_chat}")
        logger.info(f"主动对话: {self.settings.proactive.enabled}")
        logger.info(f"人工审核: {self.settings.manual_review}")
        logger.info(f"Dry Run: {self.settings.dry_run}")
        self._update_runtime(status="starting")

        await self._resolve_target_entity()
        await self._warmup_memory()
        self._register_handlers()

        logger.info("已连接 Telegram，开始监听指定聊天")
        worker_task = asyncio.create_task(self._worker_loop())
        scheduler_task = asyncio.create_task(self._scheduler_loop())
        operator_task = asyncio.create_task(self._operator_loop())
        self._update_runtime(status="running")

        try:
            await self._client.run_until_disconnected()
        finally:
            worker_task.cancel()
            scheduler_task.cancel()
            operator_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
            with contextlib.suppress(asyncio.CancelledError):
                await operator_task
            self._update_runtime(status="stopped")
            self.state_store.save(self.state)
            self.memory_store.save(self.memory)

    async def _connect(self) -> None:
        try:
            from telethon import TelegramClient, events
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "缺少 Telethon 依赖，请先执行 `pip install -r requirements.txt`"
            ) from exc

        session_dir = DATA_DIR / "telegram_sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_path = str(session_dir / self.settings.session_name)

        self._events = events
        self._client = TelegramClient(session_path, self.settings.api_id, self.settings.api_hash)
        await self._client.start(phone=self.settings.phone_number or None)

    async def _resolve_target_entity(self) -> None:
        resolved = None
        try:
            resolved = await self._client.get_entity(self.settings.target_chat)
        except Exception:
            resolved = None

        if resolved is not None:
            self._set_target_entity(resolved)
            return

        needle = self.settings.target_chat.strip().lower()
        candidates = []
        async for dialog in self._client.iter_dialogs(limit=100):
            label = " ".join(
                part for part in [
                    getattr(dialog, "name", "") or "",
                    getattr(getattr(dialog, "entity", None), "username", "") or "",
                ] if part
            ).strip()
            if needle and needle in label.lower():
                candidates.append(dialog)
            if len(candidates) >= 5:
                break

        if len(candidates) == 1:
            self._set_target_entity(candidates[0].entity)
            logger.info(f"目标聊天已自动匹配为: {candidates[0].name}")
            return

        if candidates:
            candidate_names = "、".join(dialog.name for dialog in candidates if dialog.name)
            raise ValueError(f"target_chat 存在歧义，请改成更精确的用户名或 ID。候选: {candidate_names}")

        raise ValueError(f"未找到目标聊天: {self.settings.target_chat}")

    def _register_handlers(self) -> None:
        @self._client.on(self._events.NewMessage())
        async def handle_new_message(event):
            if event.out:
                return

            if self._target_chat_id and int(getattr(event, "chat_id", 0) or 0) != self._target_chat_id:
                return

            text = (event.raw_text or "").strip()
            if not text:
                return

            message_id = int(getattr(event.message, "id", 0) or 0)
            if message_id and message_id <= self.state.last_processed_incoming_id:
                return

            incoming_at = self._to_local_time(getattr(event.message, "date", None))
            logger.info(f"收到目标聊天新消息: {truncate_string(text, 80)}")
            self.state.touch_incoming(incoming_at)
            self.memory.note_interaction(f"{incoming_at.strftime('%m-%d %H:%M')} 对方: {truncate_string(text, 60)}")
            self.runtime.note_message("user", text, incoming_at.strftime("%Y-%m-%d %H:%M"))
            self.state_store.save(self.state)
            self.memory_store.save(self.memory)
            self.runtime_store.save(self.runtime)

            await self._enqueue_job(
                ConversationJob(
                    job_id=f"reply:{message_id or incoming_at.isoformat()}",
                    mode="reply",
                    created_at=incoming_at.isoformat(),
                    latest_partner_message=text,
                    message_id=message_id,
                )
            )

    async def _scheduler_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.proactive.poll_interval_seconds)
            if self._runtime_paused or self._proactive_paused:
                logger.debug("自动化已暂停，跳过主动发起调度")
                continue
            now = self._now()
            allowed, reason = self.guard.can_initiate(now, self.state)
            if not allowed:
                logger.debug(f"跳过主动发起: {reason}")
                continue

            if self._has_pending_reply():
                logger.debug("存在待处理回复任务，跳过本轮主动发起")
                continue

            await self._enqueue_job(
                ConversationJob(
                    job_id="initiate:scheduled",
                    mode="initiate",
                    created_at=now.isoformat(),
                )
            )

    async def _operator_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            paused, proactive_paused, commands = self.control_store.pop_commands()
            self._runtime_paused = paused
            self._proactive_paused = proactive_paused
            self.runtime.automation_paused = paused
            self.runtime.proactive_paused = proactive_paused
            self.runtime.manual_review_enabled = self.settings.manual_review
            if paused and self.runtime.status == "running":
                self.runtime.status = "paused"
            elif not paused and self.runtime.status in {"paused", "running"}:
                self.runtime.status = "running"
            self.runtime_store.save(self.runtime)

            for command in commands:
                await self._handle_operator_command(command.action, command.payload)

    async def _worker_loop(self) -> None:
        while True:
            job = await self._job_queue.get()
            self._active_job_id = job.job_id
            self._active_job_mode = job.mode
            try:
                await self._process_job(job)
            except Exception as exc:
                logger.error(f"串行任务处理失败: {exc}")
            finally:
                self._pending_job_ids.discard(job.job_id)
                self._active_job_id = ""
                self._active_job_mode = ""
                self._job_queue.task_done()

    async def _process_job(self, job: ConversationJob) -> None:
        if self._runtime_paused:
            logger.info("自动化已暂停，跳过任务处理")
            return

        now = self._now()
        history = await self._fetch_history()
        await self._maybe_refresh_memory(history, now)

        if job.mode == "reply":
            if job.message_id and job.message_id <= self.state.last_processed_incoming_id:
                return
            decision = self.guard.validate_decision(
                self.orchestrator.decide_reply(
                    history,
                    job.latest_partner_message,
                    now,
                    memory=self.memory,
                ),
                mode="reply",
                history=history,
                state=self.state,
            )
            await self._maybe_send(decision, proactive=False, history=history)
            if job.message_id:
                self.state.last_processed_incoming_id = max(self.state.last_processed_incoming_id, job.message_id)
        else:
            job_created_at = self._parse_dt(job.created_at)
            last_incoming = self._parse_dt(self.state.last_incoming_at)
            if job_created_at and last_incoming and last_incoming > job_created_at:
                logger.debug("主动任务已过期：排队后出现了新的来信")
                return

            allowed, reason = self.guard.can_initiate(now, self.state)
            if not allowed:
                logger.debug(f"主动任务取消: {reason}")
                return

            decision = self.guard.validate_decision(
                self.orchestrator.decide_proactive(
                    history,
                    now,
                    memory=self.memory,
                ),
                mode="initiate",
                history=history,
                state=self.state,
            )
            await self._maybe_send(decision, proactive=True, history=history)

        self.state.last_decision_at = now.isoformat()
        if decision.topic:
            self.state.last_topic = decision.topic
        self.state_store.save(self.state)
        self.memory_store.save(self.memory)
        self.runtime.last_decision = truncate_string(decision.reason, 120)
        self.runtime_store.save(self.runtime)

    async def _maybe_send(
        self,
        decision: ConversationDecision,
        proactive: bool,
        history: Optional[List[ConversationTurn]] = None,
    ) -> None:
        logger.info(f"决策: {decision.action} / {decision.topic or '-'} / {truncate_string(decision.reason, 80)}")
        if decision.action == "hold":
            self.memory.note_interaction(f"{self._now().strftime('%m-%d %H:%M')} 系统: hold - {truncate_string(decision.reason, 60)}")
            self.runtime.last_decision = truncate_string(decision.reason, 120)
            self.runtime_store.save(self.runtime)
            return

        review = self.reviewer.review(
            decision=decision,
            mode="initiate" if proactive else "reply",
            history=history or [],
            memory=self.memory,
            now=self._now(),
        )
        if not review.allow:
            logger.warning(f"发送审核拦截: {review.reason}")
            self.memory.note_interaction(
                f"{self._now().strftime('%m-%d %H:%M')} 审核拦截: {truncate_string(review.reason, 60)}"
            )
            self.runtime.last_decision = f"审核拦截: {truncate_string(review.reason, 100)}"
            self.memory_store.save(self.memory)
            self.runtime_store.save(self.runtime)
            return

        if self.settings.manual_review:
            draft = PendingDraft(
                draft_id=f"draft:{datetime.now().timestamp()}",
                mode="initiate" if proactive else "reply",
                topic=decision.topic,
                message=decision.message,
                reason=decision.reason,
                created_at=self._now().isoformat(),
                risk=review.risk or decision.risk,
                confidence=max(review.confidence, decision.confidence),
                proactive=proactive,
            )
            self.runtime.pending_draft = draft
            self.runtime.last_decision = f"待人工审核: {truncate_string(decision.reason, 100)}"
            self.runtime_store.save(self.runtime)
            logger.info(f"消息已进入待审核草稿区: {truncate_string(draft.message, 80)}")
            return

        if not self.settings.dry_run and not proactive:
            await asyncio.sleep(self.settings.proactive.reply_delay_seconds)

        await self._dispatch_message(
            message=decision.message,
            topic=decision.topic,
            proactive=proactive,
            source_label="dry_run" if self.settings.dry_run else "auto_send",
        )

    async def _fetch_history(self) -> List[ConversationTurn]:
        messages = []
        async for message in self._client.iter_messages(self._target_entity, limit=self.settings.history_limit):
            text = (getattr(message, "message", "") or "").strip()
            if not text:
                continue
            messages.append(
                ConversationTurn(
                    role="assistant" if getattr(message, "out", False) else "user",
                    text=text,
                    timestamp=self._to_local_time(getattr(message, "date", None)).strftime("%Y-%m-%d %H:%M"),
                )
            )
        messages.reverse()
        return messages

    async def _enqueue_job(self, job: ConversationJob) -> None:
        if job.job_id in self._pending_job_ids or job.job_id == self._active_job_id:
            return
        self._pending_job_ids.add(job.job_id)
        await self._job_queue.put(job)

    async def _warmup_memory(self) -> None:
        history = await self._fetch_history()
        await self._maybe_refresh_memory(history, self._now(), force=True)

    async def _maybe_refresh_memory(
        self,
        history: List[ConversationTurn],
        now: datetime,
        force: bool = False,
    ) -> None:
        if len(history) < 6:
            return

        should_refresh = force or self._should_refresh_memory(history, now)
        if not should_refresh:
            return

        self.memory = self.orchestrator.summarize_memory(history, self.memory, now)
        self.memory_store.save(self.memory)

    def _should_refresh_memory(self, history: List[ConversationTurn], now: datetime) -> bool:
        if not self.memory.last_refreshed_at:
            return True

        try:
            last_refresh = datetime.fromisoformat(self.memory.last_refreshed_at)
        except ValueError:
            return True

        if len(history) - self.memory.source_message_count >= 6:
            return True

        return now - last_refresh >= timedelta(hours=12)

    def _has_pending_reply(self) -> bool:
        if self._active_job_mode == "reply":
            return True
        return any(job_id.startswith("reply:") for job_id in self._pending_job_ids)

    async def _handle_operator_command(self, action: str, payload: Dict[str, Any]) -> None:
        if action == "approve_draft":
            draft = self.runtime.pending_draft
            if not draft:
                return
            draft_id = str(payload.get("draft_id", "")).strip()
            if draft_id and draft.draft_id != draft_id:
                return
            message = str(payload.get("message", "")).strip() or draft.message
            await self._dispatch_message(
                message=message,
                topic=draft.topic,
                proactive=draft.proactive,
                source_label="manual_approve",
            )
            self.runtime.pending_draft = None
            self.runtime.last_decision = "草稿已人工批准并发送"
            self.runtime_store.save(self.runtime)
            return

        if action == "reject_draft":
            draft = self.runtime.pending_draft
            if not draft:
                return
            draft_id = str(payload.get("draft_id", "")).strip()
            if draft_id and draft.draft_id != draft_id:
                return
            self.runtime.pending_draft = None
            self.runtime.last_decision = "草稿已人工驳回"
            self.memory.note_interaction(f"{self._now().strftime('%m-%d %H:%M')} 人工驳回草稿")
            self.memory_store.save(self.memory)
            self.runtime_store.save(self.runtime)
            return

        if action == "switch_target":
            target_chat = str(payload.get("target_chat", "")).strip()
            if not target_chat:
                return
            old_target = self.settings.target_chat
            self.settings.target_chat = target_chat
            try:
                await self._resolve_target_entity()
            except Exception as exc:
                self.settings.target_chat = old_target
                await self._resolve_target_entity()
                self.runtime.last_error = f"切换目标聊天失败: {exc}"
                self.runtime_store.save(self.runtime)
                return

            config = get_app_config()
            telegram_user = dict(config.get("telegram_user", {}))
            telegram_user["target_chat"] = target_chat
            config["telegram_user"] = telegram_user
            save_app_config(config)
            self.runtime.target_chat = target_chat
            self.runtime.last_decision = f"已切换目标聊天到 {target_chat}"
            self.runtime.pending_draft = None
            self.runtime_store.save(self.runtime)
            logger.info(f"已切换目标聊天: {target_chat}")
            return

        if action == "manual_send":
            message = str(payload.get("message", "")).strip()
            if not message:
                return
            await self._dispatch_message(
                message=message,
                topic="manual_send",
                proactive=False,
                source_label="manual_send",
            )
            self.runtime.last_decision = "已执行人工发送"
            self.runtime_store.save(self.runtime)

    async def _dispatch_message(
        self,
        message: str,
        topic: str,
        proactive: bool,
        source_label: str,
    ) -> None:
        if self.settings.dry_run:
            logger.info(f"[Dry Run] 拟发送消息: {message}")
        else:
            await self._client.send_message(self._target_entity, message)
            logger.info(f"已发送消息: {truncate_string(message, 80)}")

        now = self._now()
        self.state.touch_outgoing(now, message, proactive=proactive)
        self.memory.note_topic(topic)
        self.memory.note_interaction(
            f"{now.strftime('%m-%d %H:%M')} {'主动' if proactive else '回复'}: {truncate_string(message, 60)}"
        )
        self.runtime.note_message("assistant", message, now.strftime("%Y-%m-%d %H:%M"))
        self.runtime.last_decision = f"{source_label}: {truncate_string(message, 100)}"
        self.runtime.pending_draft = None
        self.state_store.save(self.state)
        self.memory_store.save(self.memory)
        self.runtime_store.save(self.runtime)

    def _update_runtime(self, status: Optional[str] = None, error: str = "") -> None:
        if status:
            self.runtime.status = status
        self.runtime.last_error = error
        self.runtime.automation_paused = self._runtime_paused
        self.runtime.proactive_paused = self._proactive_paused
        self.runtime.manual_review_enabled = self.settings.manual_review
        self.runtime.target_chat = self.settings.target_chat
        self.runtime.session_name = self.settings.session_name
        self.runtime.last_updated_at = self._now().isoformat()
        self.runtime_store.save(self.runtime)

    def _set_target_entity(self, entity: Any) -> None:
        self._target_entity = entity
        self._target_chat_id = int(getattr(entity, "id", 0) or 0)

    def _parse_dt(self, value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _ensure_target_chat(self) -> None:
        if not self.settings.target_chat:
            raise ValueError("telegram_user.target_chat 未设置，请填写目标聊天用户名、ID 或备注名")

    def _now(self) -> datetime:
        if ZoneInfo:
            return datetime.now(ZoneInfo(self.settings.timezone_name))
        return datetime.now()

    def _to_local_time(self, value: Optional[datetime]) -> datetime:
        if value is None:
            return self._now()

        if ZoneInfo:
            if value.tzinfo is None:
                return value.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(self.settings.timezone_name))
            return value.astimezone(ZoneInfo(self.settings.timezone_name))
        return value


def validate_telegram_user_settings(config: Optional[Dict[str, Any]] = None) -> bool:
    """校验 Telegram 用户账号配置"""
    settings = TelegramUserSettings.from_config(config)
    if not settings.persona:
        raise ValueError("telegram_user.persona 未设置")
    if not settings.allowed_topics:
        raise ValueError("telegram_user.allowed_topics 不能为空")
    return True


async def _fetch_recent_dialog_choices_async(
    settings: TelegramUserSettings,
    limit: int = 15,
) -> List[DialogChoice]:
    try:
        from telethon import TelegramClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "缺少 Telethon 依赖，请先执行 `pip install -r requirements.txt`"
        ) from exc

    session_dir = DATA_DIR / "telegram_sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(session_dir / settings.session_name)

    client = TelegramClient(session_path, settings.api_id, settings.api_hash)
    await client.start(phone=settings.phone_number or None)

    choices: List[DialogChoice] = []
    try:
        async for dialog in client.iter_dialogs(limit=limit):
            entity = getattr(dialog, "entity", None)
            username = getattr(entity, "username", "") or ""
            title = (getattr(dialog, "name", "") or "").strip() or username or str(getattr(dialog, "id", ""))
            choices.append(
                DialogChoice(
                    title=title,
                    username=username,
                    dialog_id=int(getattr(dialog, "id", 0) or 0),
                )
            )
    finally:
        await client.disconnect()

    return choices


def fetch_recent_dialog_choices(
    settings: TelegramUserSettings,
    limit: int = 15,
) -> List[DialogChoice]:
    """同步获取最近聊天候选项，供交互 onboarding 使用"""
    return asyncio.run(_fetch_recent_dialog_choices_async(settings, limit=limit))
