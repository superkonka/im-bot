#!/usr/bin/env python3
"""
DOM 驱动聊天场景下的轻量文本回复器

- 本地从页面 DOM 提取少量上下文
- 只把最近消息文本、时间和约束发给文本模型
- 模型失败时回退到平台内置回复
"""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI

from .config import DATA_DIR, get_app_config, resolve_kimi_api_key
from .utils.helpers import extract_json_from_text, truncate_string
from .utils.logger import logger


@dataclass
class DOMChatReply:
    """DOM 聊天回复结果"""

    message: str
    topic: str = ""
    reason: str = ""
    source: str = "fallback"


@dataclass
class DOMChatMemory:
    """Web 锁定聊天模式下的本地长期记忆"""

    chat_label: str = ""
    relationship_summary: str = ""
    salient_facts: List[str] = field(default_factory=list)
    open_loops: List[str] = field(default_factory=list)
    recent_topics: List[str] = field(default_factory=list)
    last_refreshed_at: str = ""
    source_message_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DOMChatMemory":
        return cls(
            chat_label=str(data.get("chat_label", "")).strip(),
            relationship_summary=str(data.get("relationship_summary", "")).strip(),
            salient_facts=[str(item).strip() for item in data.get("salient_facts", []) if str(item).strip()],
            open_loops=[str(item).strip() for item in data.get("open_loops", []) if str(item).strip()],
            recent_topics=[str(item).strip() for item in data.get("recent_topics", []) if str(item).strip()],
            last_refreshed_at=str(data.get("last_refreshed_at", "")).strip(),
            source_message_count=int(data.get("source_message_count", 0) or 0),
        )


class DOMChatMemoryStore:
    """按聊天对象保存 Web 模式记忆"""

    def __init__(self, platform_name: str, base_dir: Optional[Path] = None):
        self.platform_name = platform_name
        self.base_dir = (base_dir or (DATA_DIR / "web_chat_memory")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def load(self, chat_label: str) -> DOMChatMemory:
        path = self._path_for_chat(chat_label)
        if not path.exists():
            return DOMChatMemory(chat_label=chat_label.strip())
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            memory = DOMChatMemory.from_dict(payload)
            if not memory.chat_label:
                memory.chat_label = chat_label.strip()
            return memory
        except (OSError, json.JSONDecodeError):
            return DOMChatMemory(chat_label=chat_label.strip())

    def save(self, memory: DOMChatMemory) -> None:
        if not memory.chat_label.strip():
            return
        path = self._path_for_chat(memory.chat_label)
        path.write_text(json.dumps(asdict(memory), ensure_ascii=False, indent=2), encoding="utf-8")

    def path_for_chat(self, chat_label: str) -> Path:
        return self._path_for_chat(chat_label)

    def clear(self, chat_label: str) -> bool:
        path = self._path_for_chat(chat_label)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    def _path_for_chat(self, chat_label: str) -> Path:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", chat_label.strip()).strip("_").lower()
        normalized = normalized or "unknown_chat"
        return self.base_dir / f"{self.platform_name}_{normalized}.json"


class DOMChatAgent:
    """用于 Web 锁定聊天模式的轻量文本回复器"""

    def __init__(
        self,
        platform_name: str,
        client: Optional[OpenAI] = None,
        app_config: Optional[Dict[str, Any]] = None,
    ):
        self.platform_name = platform_name
        self.app_config = app_config or get_app_config()
        api_cfg = self.app_config["api"]
        self.model = api_cfg["kimi_text_model"]
        self.max_chars = int(self.app_config.get("telegram_user", {}).get("max_message_chars", 180))
        self.api_key = resolve_kimi_api_key(self.app_config)
        self.client = client or OpenAI(
            api_key=self.api_key,
            base_url=api_cfg["kimi_base_url"],
        )

    def generate_reply(
        self,
        latest_message: str,
        history: List[Dict[str, str]],
        target_label: str,
        memory: Optional[DOMChatMemory],
        fallback_reply: Callable[[], str],
        now: Optional[datetime] = None,
    ) -> DOMChatReply:
        """根据最近聊天记录生成短回复"""
        try:
            prompt = self._build_prompt(
                latest_message=latest_message,
                history=history,
                target_label=target_label,
                memory=memory,
                now=now or datetime.now(),
            )
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0.4,
                max_tokens=220,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            payload = extract_json_from_text(content)
            if not payload:
                raise ValueError("LLM 未返回有效 JSON")

            message = truncate_string(str(payload.get("reply", "")).strip(), self.max_chars)
            if not message:
                raise ValueError("LLM 返回空回复")

            return DOMChatReply(
                message=message,
                topic=str(payload.get("topic", "")).strip(),
                reason=str(payload.get("reason", "")).strip(),
                source="llm",
            )
        except Exception as exc:
            logger.warning(f"DOM 文本回复生成失败，回退到平台默认回复: {exc}")
            return DOMChatReply(
                message=truncate_string(fallback_reply(), self.max_chars),
                reason="fallback",
                source="fallback",
            )

    def summarize_history(
        self,
        history: List[Dict[str, str]],
        target_label: str,
        existing_memory: Optional[DOMChatMemory] = None,
        now: Optional[datetime] = None,
    ) -> DOMChatMemory:
        """根据最近聊天记录生成本地摘要记忆"""
        base_memory = existing_memory or DOMChatMemory(chat_label=target_label)
        current_time = now or datetime.now()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0.3,
                max_tokens=320,
                messages=[
                    {"role": "system", "content": self._memory_system_prompt()},
                    {
                        "role": "user",
                        "content": self._build_memory_prompt(
                            history=history,
                            target_label=target_label,
                            existing_memory=base_memory,
                            now=current_time,
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            payload = extract_json_from_text(content)
            if not payload:
                raise ValueError("LLM 未返回有效 JSON")
            return DOMChatMemory(
                chat_label=target_label.strip(),
                relationship_summary=str(payload.get("relationship_summary", "")).strip(),
                salient_facts=[
                    str(item).strip() for item in payload.get("salient_facts", []) if str(item).strip()
                ][:8],
                open_loops=[
                    str(item).strip() for item in payload.get("open_loops", []) if str(item).strip()
                ][:6],
                recent_topics=[
                    str(item).strip() for item in payload.get("recent_topics", []) if str(item).strip()
                ][:6],
                last_refreshed_at=current_time.isoformat(),
                source_message_count=len(history),
            )
        except Exception as exc:
            logger.warning(f"DOM 聊天记忆摘要失败，回退到简化摘要: {exc}")
            return self._fallback_memory(history, target_label, base_memory, current_time)

    def _system_prompt(self) -> str:
        if self.platform_name == "telegram":
            tg = self.app_config.get("telegram_user", {})
            persona = str(tg.get("persona", "")).strip() or "自然、克制、像真人一样聊天，不暴露自己是 AI。"
            relationship_context = (
                str(tg.get("relationship_context", "")).strip() or "承接既有关系自然聊天，不冒进，不施压。"
            )
            response_style = (
                str(tg.get("response_style", "")).strip() or "简洁、自然、口语化，优先回应当前上下文。"
            )
            allowed_topics = [str(item).strip() for item in tg.get("allowed_topics", []) if str(item).strip()]
            blocked_topics = [str(item).strip() for item in tg.get("blocked_topics", []) if str(item).strip()]
        else:
            persona = "自然、简洁、友好地聊天。"
            relationship_context = "仅承接对方最近消息，不夸张，不跑题。"
            response_style = "一句到两句，简洁即可。"
            allowed_topics = ["日常寒暄", "当前消息相关话题"]
            blocked_topics = ["医疗诊断", "投资建议", "成人内容"]

        return (
            "你是一个 DOM 聊天回复助手。你不会控制页面，也不会分析截图。"
            "你只根据给定的最近聊天文本生成一条短回复。"
            f"\n人设: {persona}"
            f"\n关系约束: {relationship_context}"
            f"\n回复风格: {response_style}"
            f"\n允许话题: {'、'.join(allowed_topics) if allowed_topics else '跟随最近消息'}"
            f"\n禁止话题: {'、'.join(blocked_topics)}"
            "\n只返回 JSON，格式为: "
            '{"reply":"...", "topic":"...", "reason":"..."}'
        )

    def _memory_system_prompt(self) -> str:
        return (
            "你是一个聊天摘要助手。你不会写回复，只负责把最近聊天记录整理成短摘要。"
            "请严格返回 JSON，格式为 "
            '{"relationship_summary":"...", "salient_facts":["..."], "open_loops":["..."], "recent_topics":["..."]}'
        )

    def _build_prompt(
        self,
        latest_message: str,
        history: List[Dict[str, str]],
        target_label: str,
        memory: Optional[DOMChatMemory],
        now: datetime,
    ) -> str:
        recent_lines = []
        for item in history[-10:]:
            role = item.get("role", "unknown")
            text = truncate_string(item.get("text", "").strip(), 120)
            if not text:
                continue
            role_label = {
                "user": "对方",
                "assistant": "我方",
            }.get(role, "未知")
            recent_lines.append(f"{role_label}: {text}")

        history_text = "\n".join(recent_lines) if recent_lines else "暂无历史"
        memory_summary = memory.relationship_summary.strip() if memory else ""
        salient_facts = "；".join(memory.salient_facts) if memory and memory.salient_facts else "暂无"
        open_loops = "；".join(memory.open_loops) if memory and memory.open_loops else "暂无"
        recent_topics = "；".join(memory.recent_topics) if memory and memory.recent_topics else "暂无"
        return (
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"当前锁定聊天: {target_label}\n"
            f"关系摘要: {memory_summary or '暂无'}\n"
            f"已知事实: {salient_facts}\n"
            f"未完话题: {open_loops}\n"
            f"近期话题: {recent_topics}\n"
            f"最近聊天记录:\n{history_text}\n\n"
            f"对方最新消息: {latest_message}\n\n"
            f"要求:\n"
            f"1. 回复控制在 {self.max_chars} 字以内。\n"
            "2. 只承接当前上下文，不引入新设定。\n"
            "3. 语气自然，不像客服。\n"
            "4. 如果不适合回复，也要给出一条简短、安全的自然回应，不要返回空。"
        )

    def _build_memory_prompt(
        self,
        history: List[Dict[str, str]],
        target_label: str,
        existing_memory: DOMChatMemory,
        now: datetime,
    ) -> str:
        recent_lines = []
        for item in history[-16:]:
            role_label = "对方" if item.get("role") == "user" else "我方"
            text = truncate_string(item.get("text", "").strip(), 120)
            if text:
                recent_lines.append(f"{role_label}: {text}")
        history_text = "\n".join(recent_lines) if recent_lines else "暂无历史"
        return (
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"聊天对象: {target_label}\n"
            f"已有摘要: {existing_memory.relationship_summary or '暂无'}\n"
            f"已有事实: {'；'.join(existing_memory.salient_facts) or '暂无'}\n"
            f"已有未完话题: {'；'.join(existing_memory.open_loops) or '暂无'}\n"
            f"最近聊天记录:\n{history_text}\n\n"
            "请基于最近聊天，提炼稳定事实、未完话题和近期主题。"
            "不要编造没有出现过的个人信息。"
        )

    def _fallback_memory(
        self,
        history: List[Dict[str, str]],
        target_label: str,
        existing_memory: DOMChatMemory,
        now: datetime,
    ) -> DOMChatMemory:
        recent_user_messages = [
            truncate_string(item.get("text", "").strip(), 80)
            for item in history
            if item.get("role") == "user" and item.get("text", "").strip()
        ]
        recent_topics = recent_user_messages[-3:]
        summary = existing_memory.relationship_summary or (
            f"与 {target_label} 的聊天主要围绕最近几轮对话自然延续。"
        )
        salient_facts = existing_memory.salient_facts or recent_user_messages[-2:]
        open_loops = existing_memory.open_loops
        return DOMChatMemory(
            chat_label=target_label.strip(),
            relationship_summary=summary,
            salient_facts=salient_facts[:8],
            open_loops=open_loops[:6],
            recent_topics=recent_topics[:6],
            last_refreshed_at=now.isoformat(),
            source_message_count=len(history),
        )
