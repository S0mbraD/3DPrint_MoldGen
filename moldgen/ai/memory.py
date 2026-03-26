"""Agent 记忆管理 — 短期会话记忆 + 长期持久化记忆"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    key: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    ttl: float | None = None  # seconds, None = permanent

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return (time.time() - self.timestamp) > self.ttl


class ShortTermMemory:
    """会话级短期记忆 — 存储当前对话上下文与临时偏好"""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._max_entries = max_entries
        self._conversation_summary: str = ""

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._entries[key] = MemoryEntry(key=key, value=value, ttl=ttl)
        self._evict_expired()
        if len(self._entries) > self._max_entries:
            oldest_key = min(self._entries, key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest_key]

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            return default
        if entry.is_expired():
            del self._entries[key]
            return default
        return entry.value

    def has(self, key: str) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False
        if entry.is_expired():
            del self._entries[key]
            return False
        return True

    def delete(self, key: str) -> None:
        self._entries.pop(key, None)

    def get_all(self) -> dict[str, Any]:
        self._evict_expired()
        return {k: v.value for k, v in self._entries.items()}

    def clear(self) -> None:
        self._entries.clear()
        self._conversation_summary = ""

    @property
    def conversation_summary(self) -> str:
        return self._conversation_summary

    @conversation_summary.setter
    def conversation_summary(self, value: str) -> None:
        self._conversation_summary = value

    def _evict_expired(self) -> None:
        expired = [k for k, v in self._entries.items() if v.is_expired()]
        for k in expired:
            del self._entries[k]

    def to_dict(self) -> dict:
        return {
            "entries": {k: {"value": v.value, "ts": v.timestamp} for k, v in self._entries.items()},
            "summary": self._conversation_summary,
            "size": len(self._entries),
        }


class LongTermMemory:
    """持久化长期记忆 — 存储用户偏好、历史成功配置、常用参数"""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._path = storage_path or Path("data/cache/agent_memory.json")
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load long-term memory from %s", self._path)
        return {
            "user_defaults": {},
            "frequent_organs": [],
            "preferred_materials": ["silicone_a30"],
            "successful_configs": [],
            "agent_preferences": {},
            "usage_stats": {},
        }

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to save long-term memory")

    # ── User Defaults ──────────────────────────────────────────────────

    def set_default(self, key: str, value: Any) -> None:
        self._data["user_defaults"][key] = value
        self.save()

    def get_default(self, key: str, fallback: Any = None) -> Any:
        return self._data["user_defaults"].get(key, fallback)

    def get_all_defaults(self) -> dict[str, Any]:
        return dict(self._data["user_defaults"])

    # ── Successful Configurations ──────────────────────────────────────

    def record_success(self, config: dict) -> None:
        configs = self._data["successful_configs"]
        configs.append({**config, "timestamp": time.time()})
        if len(configs) > 50:
            configs[:] = configs[-50:]
        self.save()

    def get_recommendation(self, organ_type: str) -> dict | None:
        configs = self._data["successful_configs"]
        matches = [c for c in configs if c.get("organ_type") == organ_type]
        if matches:
            return matches[-1]
        return None

    # ── Frequent Items ────────────────────────────────────────────────

    def record_organ_use(self, organ: str) -> None:
        organs = self._data["frequent_organs"]
        if organ in organs:
            organs.remove(organ)
        organs.insert(0, organ)
        self._data["frequent_organs"] = organs[:20]
        self.save()

    def get_frequent_organs(self) -> list[str]:
        return list(self._data["frequent_organs"])

    # ── Agent Preferences ──────────────────────────────────────────────

    def set_agent_preference(self, agent_role: str, key: str, value: Any) -> None:
        prefs = self._data.setdefault("agent_preferences", {})
        prefs.setdefault(agent_role, {})[key] = value
        self.save()

    def get_agent_preference(self, agent_role: str, key: str, fallback: Any = None) -> Any:
        return self._data.get("agent_preferences", {}).get(agent_role, {}).get(key, fallback)

    # ── Usage Statistics ───────────────────────────────────────────────

    def record_usage(self, agent_role: str, tool_name: str, success: bool) -> None:
        stats = self._data.setdefault("usage_stats", {})
        agent_stats = stats.setdefault(agent_role, {})
        tool_stats = agent_stats.setdefault(tool_name, {"total": 0, "success": 0, "fail": 0})
        tool_stats["total"] += 1
        tool_stats["success" if success else "fail"] += 1

    def get_usage_stats(self) -> dict:
        return dict(self._data.get("usage_stats", {}))

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "user_defaults": self._data.get("user_defaults", {}),
            "frequent_organs": self._data.get("frequent_organs", []),
            "preferred_materials": self._data.get("preferred_materials", []),
            "n_successful_configs": len(self._data.get("successful_configs", [])),
            "agent_preferences": self._data.get("agent_preferences", {}),
        }


class AgentMemoryManager:
    """统一记忆管理器 — 为所有 Agent 提供记忆服务"""

    _instance: AgentMemoryManager | None = None

    def __new__(cls) -> AgentMemoryManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()

    def extract_preferences(self, message: str) -> dict[str, Any]:
        """从用户消息中提取参数偏好（规则式）"""
        prefs: dict[str, Any] = {}
        import re

        thickness_match = re.search(r"壁厚[用为]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", message)
        if thickness_match:
            prefs["wall_thickness"] = float(thickness_match.group(1))

        material_keywords = {
            "硅胶": "silicone_a30", "a10": "silicone_a10", "a30": "silicone_a30",
            "a50": "silicone_a50", "聚氨酯": "polyurethane", "环氧": "epoxy_resin",
        }
        for keyword, mat in material_keywords.items():
            if keyword.lower() in message.lower():
                prefs["material"] = mat

        if "全自动" in message or "自动完成" in message:
            prefs["execution_mode"] = "auto"
        elif "一步步" in message or "逐步" in message:
            prefs["execution_mode"] = "step"

        for key, value in prefs.items():
            self.short_term.set(f"pref_{key}", value)

        return prefs

    def build_context_summary(self) -> str:
        """构建当前记忆的上下文摘要（注入 Agent 系统提示词）"""
        parts: list[str] = []

        stm = self.short_term.get_all()
        pref_items = {k[5:]: v for k, v in stm.items() if k.startswith("pref_")}
        if pref_items:
            parts.append("用户当前偏好: " + ", ".join(f"{k}={v}" for k, v in pref_items.items()))

        if self.short_term.conversation_summary:
            parts.append(f"对话摘要: {self.short_term.conversation_summary}")

        freq = self.long_term.get_frequent_organs()[:5]
        if freq:
            parts.append(f"常用器官: {', '.join(freq)}")

        defaults = self.long_term.get_all_defaults()
        if defaults:
            parts.append("用户默认参数: " + ", ".join(f"{k}={v}" for k, v in defaults.items()))

        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "short_term": self.short_term.to_dict(),
            "long_term": self.long_term.to_dict(),
        }
