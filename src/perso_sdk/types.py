"""
Shared types for @teknokeras/perso-sdk (Python).

Mirrors the schema used by perso-sdk-node so audit events and decisions
look the same shape regardless of which SDK produced them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

DecisionValue = Literal["Allow", "Deny"]

SDK_VERSION = "0.1.0"


@dataclass(frozen=True)
class Decision:
    """Result of a single perso.evaluate() call."""

    decision: DecisionValue
    reason: str

    def __getitem__(self, key: str) -> Any:
        # Allows dict-style access (decision["decision"]) for anyone
        # porting code over from the Node/TS SDK examples.
        return getattr(self, key)


@dataclass(frozen=True)
class AuditEvent:
    """Structured record of a single evaluation, emitted to a transport."""

    id: str
    trace_id: str
    timestamp: str
    tool: str
    args: dict[str, Any] | str
    role: str
    agent_attributes: dict[str, Any]
    resource_attributes: dict[str, Any]
    decision: DecisionValue
    reason: str
    sdk_version: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "traceId": self.trace_id,
            "timestamp": self.timestamp,
            "tool": self.tool,
            "args": self.args,
            "role": self.role,
            "agentAttributes": self.agent_attributes,
            "resourceAttributes": self.resource_attributes,
            "decision": self.decision,
            "reason": self.reason,
            "sdkVersion": self.sdk_version,
            "policyVersion": self.policy_version,
        }


class Transport(Protocol):
    """Anything with an `emit(event)` method works as a transport."""

    def emit(self, event: AuditEvent) -> None: ...


def new_trace_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class AuditConfig:
    """Audit configuration passed to Perso.load()."""

    transport: Transport | None = None
    hash_args: bool = False
    enabled: bool = True