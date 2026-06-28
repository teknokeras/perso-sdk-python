# perso-sdk (Python)

Python SDK for [perso](https://github.com/teknokeras/perso) — an embedded WebAssembly ABAC policy engine for MCP tool calls, with no control plane and no network call in the decision path.

Wraps the raw WASM ABI (`alloc`/`dealloc`/`init`/`evaluate`) behind a clean, synchronous API and adds structured audit logging with pluggable transports — same shape as [`@teknokeras/perso-sdk`](https://github.com/teknokeras/perso-sdk-node) for Node, in idiomatic Python.

The engine and policy load directly into your own Python process via [wasmtime](https://pypi.org/project/wasmtime/). `perso.evaluate()` is a plain function call, not a request to any service.

## Install

```bash
pip install perso-sdk
```

There's nothing else to install or sign up for. No account, no API key for perso itself. You need a compiled `perso.wasm` binary and a policy JSON file — both produced by the [core perso repo](https://github.com/teknokeras/perso) — and that's the whole dependency surface.

For the optional HTTP audit transport:

```bash
pip install "perso-sdk[http]"
```

## Quick start

```python
from perso_sdk import Perso, AuditConfig, console_transport

perso = Perso.load(
    "path/to/perso.wasm",
    "path/to/policy.json",
    audit=AuditConfig(transport=console_transport()),
)

decision = perso.evaluate(
    tool="delete_file",
    args={"path": "/etc/passwd"},
    role="viewer",
    trace_id="req-abc-123",
)

print(decision)
# Decision(decision='Deny', reason='...')
```

## API

### `Perso.load(wasm_path, policy, audit=None)`

Loads the perso WASM engine and initialises it with a policy. Returns a `Perso` instance. Both the engine and the policy live in your process's memory after this call — there's no handshake with an external service.

```python
from perso_sdk import Perso, AuditConfig, console_transport

perso = Perso.load(
    "path/to/perso.wasm",
    "path/to/policy.json",        # file path or raw JSON string
    audit=AuditConfig(
        transport=console_transport(),  # where to send audit events
        hash_args=False,                # set True to SHA-256 hash args (PII protection)
        enabled=True,                   # set False to disable audit entirely
    ),
)
```

### `perso.evaluate(tool, args=None, role="", agent_attributes=None, resource_attributes=None, trace_id=None)`

Evaluates a tool call against the loaded policy. Emits an audit event automatically if a transport is configured. The decision itself is computed in-process — the only thing that ever leaves the process is the audit event, and only if you've wired up a transport for it.

```python
decision = perso.evaluate(
    tool="delete_file",
    args={"path": "/etc/passwd"},
    role="viewer",
    agent_attributes={"user_id": "u-123", "mfa_verified": True},
    resource_attributes={"owner_id": "u-456"},
    trace_id="req-abc-123",  # optional — auto-generated if omitted
)
# Decision(decision='Deny', reason='...')

decision.decision  # 'Allow' | 'Deny'
decision.reason    # human-readable string
decision["decision"]  # dict-style access also works
```

### `perso.reload(policy)`

Hot-reloads the policy without recreating the `Perso` instance. Accepts a file path or raw JSON string. No coordination with any external service — the new policy is loaded straight into the running WASM instance.

```python
perso.reload("path/to/updated-policy.json")
```

### `perso.policy_version`

The `version` field from the currently loaded policy.

```python
print(perso.policy_version)  # e.g. "perso-1.0.0"
```

## Transports

perso has no built-in audit platform — it deliberately doesn't ship a dashboard, a hosted log store, or any default destination for audit events. That's a decision, not a gap: wiring storage/observability to your own stack is the host's job. The transports below are just shaped adapters for plugging audit events into whatever you already use.

| Transport | Description |
|---|---|
| `console_transport()` | JSON to stdout — useful in development |
| `http_transport(url, headers=None, timeout=5.0)` | POST events to any HTTP endpoint you control |
| `file_transport(path)` | Append newline-delimited JSON to a file |

No transport is configured by default — audit events are silently dropped unless you explicitly pass one.

### `http_transport` — forwarding to your own logging/observability stack

`http_transport` just POSTs the `AuditEvent` JSON to a URL you provide. It's a generic forwarder, not a connection to a perso-operated service — point it at your own log ingestion endpoint, SIEM, or observability platform. Requires the `requests` package (`pip install perso-sdk[http]`), or pass your own `session=` object implementing `.post(url, json=..., headers=..., timeout=...)`.

```python
from perso_sdk import Perso, AuditConfig, http_transport
import os

perso = Perso.load(
    "perso.wasm",
    "policy.json",
    audit=AuditConfig(
        transport=http_transport(
            "https://logs.your-company.example/events",
            headers={"Authorization": f"Bearer {os.environ['YOUR_LOGGING_API_KEY']}"},
            timeout=5.0,
        ),
    ),
)
```

### Custom transport

Anything with an `emit(event)` method works as a transport — no base class required (it's a `Protocol`, structurally typed):

```python
class MyTransport:
    def emit(self, event):
        db.insert("audit_events", event.to_dict())

perso = Perso.load("perso.wasm", "policy.json", audit=AuditConfig(transport=MyTransport()))
```

## AuditEvent schema

Every evaluation emits a structured event (when a transport is configured):

```python
@dataclass(frozen=True)
class AuditEvent:
    id: str                                  # UUID per event
    trace_id: str                            # correlates decisions across an agent run
    timestamp: str                           # ISO 8601 UTC
    tool: str                                # tool name
    args: dict | str                         # raw args, or SHA-256 hex if hash_args=True
    role: str                                # caller role
    agent_attributes: dict                   # session data
    resource_attributes: dict                # resource data
    decision: Literal["Allow", "Deny"]
    reason: str                              # human-readable string from perso WASM
    sdk_version: str                         # e.g. "0.1.0"
    policy_version: str                      # e.g. "perso-1.0.0"
```

`event.to_dict()` returns the camelCase JSON shape (`traceId`, `agentAttributes`, etc.) to match the schema emitted by `perso-sdk-node`, so events from both SDKs land in the same format if you're forwarding to a shared sink.

## Why synchronous?

The Node SDK exposes an `async` API because Node's WASM bindings are commonly used in async contexts. In Python, the underlying `wasmtime` calls are synchronous and the actual evaluation is microseconds — wrapping it in `asyncio` would add overhead without a real benefit. If you're calling this from an async codebase (e.g. an `asyncio`-based MCP server), wrap calls with `asyncio.to_thread(perso.evaluate, ...)` or just call it directly — the call is fast enough that it won't meaningfully block an event loop for typical policies.

## Requirements

- Python 3.10+
- A compiled `perso.wasm` binary — see [teknokeras/perso](https://github.com/teknokeras/perso) for build instructions

## Development

Install the package in editable mode with dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the pure-Python tests (no WASM required):

```bash
pytest test_basic.py
```

## Testing

### Unit tests (no binary required)

`test_basic.py` covers pure-Python behaviour — types, transports, argument hashing — without a compiled `perso.wasm`. These always run in CI:

```bash
pytest test_basic.py -v
```

### Integration tests (real WASM, real policy)

`tests/test_integration.py` ports the **18 spec cases** from the perso core repo's own `wasm_tests` suite (`perso/crates/policy-test/src/lib.rs`), driving each scenario through the Python SDK's public API against a real compiled `perso.wasm` binary. This is parity testing, not a looser alternative: the same tool names, args, roles, agent and resource attributes, and expected Allow/Deny decisions as the Rust WASM boundary tests.

**Step 1 — build the fixtures** (one-time, needs a local clone of the perso core repo):

```bash
# assumes ../perso exists; override with PERSO_REPO_PATH=/path/to/perso
./scripts/build_fixtures.sh
```

This compiles `policy_runtime.wasm` from the perso repo's policy-compiler crate (requires Rust + the `wasm32-unknown-unknown` target) and copies the output alongside `policies/example.json` into `tests/fixtures/`. The fixtures are `.gitignore`d — each developer builds them locally.

**Step 2 — run the integration tests:**

```bash
pytest tests/test_integration.py -v
```

If `tests/fixtures/perso.wasm` is absent the suite skips gracefully with a message explaining how to build it — it does **not** fail CI. You can also point the tests at any pre-built binary:

```bash
PERSO_WASM_PATH=/path/to/perso.wasm \
PERSO_POLICY_PATH=/path/to/policies/example.json \
pytest tests/test_integration.py -v
```

**What it proves:** the Python ABI wrapper (`_wasm.py`) and public `Perso.evaluate()` method produce the same Allow/Deny decisions as the Rust core for all 18 spec scenarios — not just "it imports successfully." 19 test functions cover the 18 numbered cases (spec 16 has two sub-cases, a and b, matching the Rust source exactly).

## License

MIT