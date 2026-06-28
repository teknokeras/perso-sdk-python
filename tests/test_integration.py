"""
Integration tests for perso-sdk-python against a real compiled perso.wasm binary.

Ports all 18 spec cases from perso/crates/policy-test/src/lib.rs (wasm_tests module)
through the Python SDK's public API — so this is genuine parity with the Rust core's
own spec suite, not a different/easier test set that happens to also pass.

Fixture setup:
    Run scripts/build_fixtures.sh to compile perso.wasm from the perso core repo and
    copy it alongside policies/example.json into tests/fixtures/. The tests skip
    gracefully (no failure) if the fixtures are absent.

Env var overrides (same pattern as Rust's PERSO_WASM):
    PERSO_WASM_PATH    — path to an already-compiled perso.wasm
    PERSO_POLICY_PATH  — path to the spec policy JSON (policies/example.json)

Run:
    pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from perso_sdk import Perso

# ── Fixture paths ─────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
WASM_PATH = Path(os.environ.get("PERSO_WASM_PATH", str(_FIXTURES / "perso.wasm")))
POLICY_PATH = Path(os.environ.get("PERSO_POLICY_PATH", str(_FIXTURES / "policy.json")))

if not WASM_PATH.exists():
    pytest.skip(
        f"perso.wasm not found at {WASM_PATH}.\n"
        "  Build it with: ./scripts/build_fixtures.sh\n"
        "  Or set PERSO_WASM_PATH=/path/to/perso.wasm",
        allow_module_level=True,
    )

if not POLICY_PATH.exists():
    pytest.skip(
        f"policy.json not found at {POLICY_PATH}.\n"
        "  Build it with: ./scripts/build_fixtures.sh\n"
        "  Or set PERSO_POLICY_PATH=/path/to/policy.json",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def perso() -> Perso:
    """One Perso engine, loaded once for the entire module."""
    return Perso.load(WASM_PATH, POLICY_PATH)


# ── Spec 01: init succeeds ────────────────────────────────────────────────────
# The Rust wasm_01 checks init returns ok:true; here Perso.load() raises if
# init fails, so a successful fixture load IS the assertion.

def test_01_init_succeeds(perso: Perso):
    assert perso.policy_version == "perso-1.0.0"


# ── Spec 02: role match, no condition → Allow ─────────────────────────────────

def test_02_role_match_no_condition_allows(perso: Perso):
    d = perso.evaluate("read_file", role="viewer")
    assert d.decision == "Allow"


# ── Spec 03: role mismatch → Deny (default_action) ───────────────────────────

def test_03_role_mismatch_denies(perso: Perso):
    d = perso.evaluate("read_file", role="admin")
    assert d.decision == "Deny"


# ── Spec 04: NumericCheck: amount=200, Lte 500 → Allow ───────────────────────

def test_04_numeric_check_pass_allows(perso: Perso):
    d = perso.evaluate("refund_user", args={"amount": 200}, role="supervisor")
    assert d.decision == "Allow"


# ── Spec 05: NumericCheck: amount=600, Lte 500 → Deny ────────────────────────

def test_05_numeric_check_fail_denies(perso: Perso):
    d = perso.evaluate("refund_user", args={"amount": 600}, role="supervisor")
    assert d.decision == "Deny"


# ── Spec 06: StringCheck NotIn: safe path → Allow ────────────────────────────

def test_06_string_not_in_safe_path_allows(perso: Perso):
    d = perso.evaluate(
        "read_restricted",
        args={"path": "/home/user/doc.txt"},
        role="viewer",
    )
    assert d.decision == "Allow"


# ── Spec 07: StringCheck NotIn: /etc/passwd → Deny ───────────────────────────

def test_07_string_not_in_blocked_path_denies(perso: Perso):
    d = perso.evaluate(
        "read_restricted",
        args={"path": "/etc/passwd"},
        role="viewer",
    )
    assert d.decision == "Deny"


# ── Spec 08: FieldPresent: field present → Allow ─────────────────────────────

def test_08_field_present_allows(perso: Perso):
    d = perso.evaluate(
        "sensitive_tool",
        role="supervisor",
        agent_attributes={"session_token": "tok123"},
    )
    assert d.decision == "Allow"


# ── Spec 09: FieldPresent: field missing → Deny ──────────────────────────────

def test_09_field_present_missing_denies(perso: Perso):
    d = perso.evaluate("sensitive_tool", role="supervisor")
    assert d.decision == "Deny"


# ── Spec 10: FieldEquals: values match → Allow ───────────────────────────────

def test_10_field_equals_match_allows(perso: Perso):
    d = perso.evaluate(
        "edit_document",
        role="admin",
        agent_attributes={"user_id": "u42"},
        resource_attributes={"owner_id": "u42"},
    )
    assert d.decision == "Allow"


# ── Spec 11: FieldEquals: mismatch, second Any branch also fails → Deny ──────

def test_11_field_equals_mismatch_denies(perso: Perso):
    d = perso.evaluate(
        "edit_document",
        role="admin",
        agent_attributes={"user_id": "u1", "role": "viewer"},
        resource_attributes={"owner_id": "u99"},
    )
    assert d.decision == "Deny"


# ── Spec 12: All: all conditions pass → Allow ────────────────────────────────

def test_12_all_conditions_pass_allows(perso: Perso):
    d = perso.evaluate(
        "guarded_tool",
        role="supervisor",
        agent_attributes={"env": "production", "mfa_verified": True},
    )
    assert d.decision == "Allow"


# ── Spec 13: All: one condition fails → Deny ─────────────────────────────────

def test_13_all_one_fail_denies(perso: Perso):
    d = perso.evaluate(
        "guarded_tool",
        role="supervisor",
        agent_attributes={"env": "staging", "mfa_verified": True},
    )
    assert d.decision == "Deny"


# ── Spec 14: Any: one condition passes → Allow ───────────────────────────────

def test_14_any_one_pass_allows(perso: Perso):
    d = perso.evaluate(
        "edit_document",
        role="admin",
        agent_attributes={"user_id": "u1", "role": "admin"},
        resource_attributes={"owner_id": "u99"},
    )
    assert d.decision == "Allow"


# ── Spec 15: Any: all conditions fail → Deny ─────────────────────────────────

def test_15_any_all_fail_denies(perso: Perso):
    d = perso.evaluate(
        "edit_document",
        role="admin",
        agent_attributes={"user_id": "u1", "role": "viewer"},
        resource_attributes={"owner_id": "u99"},
    )
    assert d.decision == "Deny"


# ── Spec 16a: Not: blocked_role in agent_attrs → Deny ────────────────────────

def test_16a_not_blocked_role_denies(perso: Perso):
    d = perso.evaluate(
        "open_tool",
        role="viewer",
        agent_attributes={"role": "blocked_role"},
    )
    assert d.decision == "Deny"


# ── Spec 16b: Not: normal role → Allow ───────────────────────────────────────

def test_16b_not_normal_role_allows(perso: Perso):
    d = perso.evaluate(
        "open_tool",
        role="viewer",
        agent_attributes={"role": "viewer"},
    )
    assert d.decision == "Allow"


# ── Spec 17: Glob expansion: glob_tool_* + admin → Allow ─────────────────────

def test_17_glob_expansion_allows(perso: Perso):
    da = perso.evaluate("glob_tool_alpha", role="admin")
    db = perso.evaluate("glob_tool_beta", role="admin")
    assert da.decision == "Allow", f"glob_tool_alpha returned {da}"
    assert db.decision == "Allow", f"glob_tool_beta returned {db}"


# ── Spec 18: Unknown tool → Deny (default_action) ────────────────────────────

def test_18_unknown_tool_denies(perso: Perso):
    d = perso.evaluate("totally_unknown_tool", role="admin")
    assert d.decision == "Deny"
