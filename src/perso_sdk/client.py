"""
Public SDK surface for @teknokeras/perso-sdk (Python).

Wraps the raw WASM ABI behind a clean, synchronous API and adds
structured audit logging with pluggable transports — mirroring
perso-sdk-node's shape, in idiomatic Python.

Everything here runs in-process. Perso.evaluate() is a plain Python
function call into the loaded WASM module; nothing crosses the network
unless you've explicitly configured an audit transport that does.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ._wasm import _PersoWasm
from .types import AuditConfig, AuditEvent, Decision, SDK_VERSION, new_trace_id, now_iso


def _load_policy_text(policy: str | Path) -> str:
    """Accept either a raw JSON string or a path to a policy file."""
    text = str(policy)
    stripped = text.strip()
    if stripped.startswith("{"):
        return text
    return Path(policy).read_text(encoding="utf-8")


def _hash_args(args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Perso:
    """
    A loaded perso engine instance: one compiled WASM module plus one
    active policy, ready to evaluate tool calls in-process.

    Use Perso.load(...) to construct one — don't call __init__ directly.
    """

    def __init__(self, wasm: _PersoWasm, audit: AuditConfig, policy_version: str) -> None:
        self._wasm = wasm
        self._audit = audit
        self._policy_version = policy_version

    # -- Construction -----------------------------------------------------

    @classmethod
    def load(
        cls,
        wasm_path: str | Path,
        policy: str | Path,
        audit: AuditConfig | None = None,
    ) -> "Perso":
        """
        Load the perso WASM engine and initialise it with a policy.

        Args:
            wasm_path: path to the compiled perso.wasm engine binary.
            policy: a file path to a policy JSON file, or a raw JSON string.
            audit: optional AuditConfig (transport, hash_args, enabled).
                   If omitted, no transport is configured and audit
                   events are silently dropped — same default as the
                   Node SDK.

        Returns:
            A ready-to-use Perso instance.
        """
        wasm = _PersoWasm(wasm_path)
        policy_json = _load_policy_text(policy)
        init_result = wasm.init(policy_json)

        policy_doc = json.loads(policy_json)
        policy_version = policy_doc.get("version", init_result.get("version", "unknown"))

        return cls(wasm, audit or AuditConfig(), policy_version)

    # -- Evaluation ---------------------------------------------------------

    def evaluate(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        role: str = "",
        agent_attributes: dict[str, Any] | None = None,
        resource_attributes: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Decision:
        """
        Evaluate a single tool call against the loaded policy.

        This is an in-process call — it does not reach out to any
        external service. An audit event is emitted automatically
        afterward if a transport is configured.
        """
        args = args or {}
        agent_attributes = agent_attributes or {}
        resource_attributes = resource_attributes or {}
        trace_id = trace_id or new_trace_id()

        context = {
            "role": role,
            "agent_attrs": agent_attributes,
            "resource_attrs": resource_attributes,
        }

        raw = self._wasm.evaluate(tool, args, context)
        decision = Decision(decision=raw["decision"], reason=raw["reason"])

        self._emit_audit_event(
            trace_id=trace_id,
            tool=tool,
            args=args,
            role=role,
            agent_attributes=agent_attributes,
            resource_attributes=resource_attributes,
            decision=decision,
        )

        return decision

    # -- Hot reload -----------------------------------------------------

    def reload(self, policy: str | Path) -> None:
        """
        Hot-reload the policy without recreating the engine instance.

        Accepts a file path or a raw JSON string, same as load().
        """
        policy_json = _load_policy_text(policy)
        self._wasm.init(policy_json)
        policy_doc = json.loads(policy_json)
        self._policy_version = policy_doc.get("version", self._policy_version)

    # -- Properties -----------------------------------------------------

    @property
    def policy_version(self) -> str:
        """The `version` field from the currently loaded policy."""
        return self._policy_version

    # -- Internal ---------------------------------------------------------

    def _emit_audit_event(
        self,
        trace_id: str,
        tool: str,
        args: dict[str, Any],
        role: str,
        agent_attributes: dict[str, Any],
        resource_attributes: dict[str, Any],
        decision: Decision,
    ) -> None:
        if not self._audit.enabled or self._audit.transport is None:
            return

        event_args: dict[str, Any] | str = args
        if self._audit.hash_args:
            event_args = _hash_args(args)

        event = AuditEvent(
            id=new_trace_id(),
            trace_id=trace_id,
            timestamp=now_iso(),
            tool=tool,
            args=event_args,
            role=role,
            agent_attributes=agent_attributes,
            resource_attributes=resource_attributes,
            decision=decision.decision,
            reason=decision.reason,
            sdk_version=SDK_VERSION,
            policy_version=self._policy_version,
        )

        self._audit.transport.emit(event)