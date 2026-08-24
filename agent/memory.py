# agent/memory.py
# 会话记忆：记录对话与工具观察，向 LLM 提供滚动上下文。
#
#   - 短时记忆：本轮/近几轮消息列表（默认保留最近 N 条）；
#   - 长时记忆（轻量）：可从多轮中积累的"事实/结论"备注，便于跨轮引用。

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ConversationMemory:
    max_turns: int = 10
    messages: List[Dict[str, str]] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        # 裁剪到最近 max_turns 条
        if len(self.messages) > self.max_turns:
            self.messages = self.messages[-self.max_turns:]

    def add_user(self, text: str) -> None:
        self.add("user", text)

    def add_assistant(self, text: str) -> None:
        self.add("assistant", text)

    def add_observation(self, tool: str, result: str) -> None:
        self.add("observation", f"[{tool}] {result[:600]}")

    def remember(self, fact: str) -> None:
        if fact and fact not in self.facts:
            self.facts.append(fact)

    def history(self) -> List[Dict[str, str]]:
        return list(self.messages)

    def context(self) -> str:
        """把消息与已积累事实拼成一段上下文文本，供 LLM 参考。"""
        parts = []
        if self.facts:
            parts.append("已积累结论: " + "；".join(self.facts))
        for m in self.messages:
            parts.append(f"{m['role']}: {m['content']}")
        return "\n".join(parts)

    def clear(self) -> None:
        self.messages.clear()
        self.facts.clear()
