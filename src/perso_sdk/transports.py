"""
Pluggable audit transports.

None of these are required. perso has no built-in audit platform by
design — these are just shaped adapters for forwarding AuditEvents to
whatever logging/observability stack you already use. If you don't
pass a transport to Perso.load(), audit events are silently dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import AuditEvent


class ConsoleTransport:
    """Prints each AuditEvent as JSON to stdout. Useful in development."""

    def emit(self, event: AuditEvent) -> None:
        print(json.dumps(event.to_dict()))


class FileTransport:
    """Appends each AuditEvent as a newline-delimited JSON line to a file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def emit(self, event: AuditEvent) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")


class HttpTransport:
    """
    POSTs each AuditEvent as JSON to an HTTP endpoint you control.

    This is a generic forwarder — point it at your own log ingestion
    endpoint, SIEM, or observability platform. It is not a connection
    to any perso-operated service.

    Requires the `requests` package (perso_sdk[http] extra), or pass
    your own `session` implementing a `.post(url, json=..., headers=...,
    timeout=...)` method (e.g. an httpx.Client).
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
        session: Any | None = None,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout

        if session is not None:
            self._session = session
        else:
            try:
                import requests
            except ImportError as exc:  # pragma: no cover
                raise ImportError(
                    "HttpTransport needs the 'requests' package "
                    "(pip install perso-sdk[http]) or a custom session "
                    "object passed via session=..."
                ) from exc
            self._session = requests

    def emit(self, event: AuditEvent) -> None:
        self._session.post(
            self._url,
            json=event.to_dict(),
            headers=self._headers,
            timeout=self._timeout,
        )


def console_transport() -> ConsoleTransport:
    return ConsoleTransport()


def file_transport(path: str | Path) -> FileTransport:
    return FileTransport(path)


def http_transport(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
    session: Any | None = None,
) -> HttpTransport:
    return HttpTransport(url, headers=headers, timeout=timeout, session=session)