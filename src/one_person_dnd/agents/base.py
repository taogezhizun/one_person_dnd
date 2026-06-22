from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
