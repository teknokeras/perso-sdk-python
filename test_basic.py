"""
Tests that don't require a compiled perso.wasm binary — they cover the
parts of the SDK that are pure Python (types, transports, hashing).

Full integration tests against a real perso.wasm + policy.json belong
in a separate test module (test_integration.py) and should set
PERSO_WASM_PATH / PERSO_POLICY_PATH env vars, following the same
pattern as the wasm_tests in the core perso repo.
"""

from __future__ import annotations

import json

from perso_sdk.client import _hash_args, _load_policy_text
from perso_sdk.transports import ConsoleTransport, FileTransport
from perso_sdk.types import AuditConfig, AuditEvent, Decision, new_trace_id, now_iso


def test_decision_dict_access():
    d = Decision(decision="Allow", reason="ok")
    assert d["decision"] == "Allow"
    assert d["reason"] == "ok"


def test_hash_args_is_deterministic():
    a = {"amount": 500, "id": "x"}
    b = {"id": "x", "amount": 500}  # different key order
    assert _hash_args(a) == _hash_args(b)


def test_load_policy_text_from_raw_json():
    raw = '{"version": "perso-1.0.0", "default_action": "Deny", "tools": [], "rules": []}'
    assert _load_policy_text(raw) == raw


def test_load_policy_text_from_file(tmp_path):
    policy_path = tmp_path / "policy.json"
    payload = {"version": "perso-1.0.0", "default_action": "Deny", "tools": [], "rules": []}
    policy_path.write_text(json.dumps(payload))

    loaded = _load_policy_text(policy_path)
    assert json.loads(loaded) == payload


def test_console_transport_emits(capsys):
    event = AuditEvent(
        id=new_trace_id(),
        trace_id=new_trace_id(),
        timestamp=now_iso(),
        tool="view_customer",
        args={"id": "C-1"},
        role="agent",
        agent_attributes={},
        resource_attributes={},
        decision="Allow",
        reason="ok",
        sdk_version="0.1.0",
        policy_version="perso-1.0.0",
    )
    ConsoleTransport().emit(event)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["tool"] == "view_customer"
    assert parsed["decision"] == "Allow"


def test_file_transport_appends(tmp_path):
    path = tmp_path / "audit.log"
    transport = FileTransport(path)

    event = AuditEvent(
        id=new_trace_id(),
        trace_id=new_trace_id(),
        timestamp=now_iso(),
        tool="process_refund",
        args={"amount": 200},
        role="agent",
        agent_attributes={},
        resource_attributes={},
        decision="Allow",
        reason="ok",
        sdk_version="0.1.0",
        policy_version="perso-1.0.0",
    )
    transport.emit(event)
    transport.emit(event)

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert parsed["tool"] == "process_refund"


def test_audit_config_defaults():
    config = AuditConfig()
    assert config.transport is None
    assert config.enabled is True
    assert config.hash_args is False