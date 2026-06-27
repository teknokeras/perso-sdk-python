"""
perso_sdk — Python SDK for perso, an embedded WASM ABAC policy engine
for MCP tool-call authorization.

    from perso_sdk import Perso, console_transport

    perso = Perso.load("perso.wasm", "policy.json",
                        audit=AuditConfig(transport=console_transport()))

    decision = perso.evaluate(tool="delete_file", args={"path": "/etc/passwd"},
                               role="viewer")
"""

from .client import Perso
from .transports import (
    ConsoleTransport,
    FileTransport,
    HttpTransport,
    console_transport,
    file_transport,
    http_transport,
)
from .types import AuditConfig, AuditEvent, Decision

__all__ = [
    "Perso",
    "AuditConfig",
    "AuditEvent",
    "Decision",
    "ConsoleTransport",
    "FileTransport",
    "HttpTransport",
    "console_transport",
    "file_transport",
    "http_transport",
]

__version__ = "0.1.0"