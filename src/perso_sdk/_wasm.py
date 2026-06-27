"""
Low-level wrapper around the perso WASM ABI.

Implements the alloc -> write -> call -> read -> dealloc cycle described
in the perso core repo. This module has no knowledge of audit transports
or the public SDK surface — it only knows how to talk to the compiled
.wasm binary through wasmtime.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from wasmtime import Engine, Linker, Module, Store


class PersoWasmError(RuntimeError):
    """Raised when the WASM engine returns an error response."""


class _PersoWasm:
    """Thin ABI binding. Not part of the public API — see client.Perso."""

    def __init__(self, wasm_path: str | Path) -> None:
        self._engine = Engine()
        module = Module.from_file(self._engine, str(wasm_path))
        linker = Linker(self._engine)
        self._store = Store(self._engine)
        instance = linker.instantiate(self._store, module)

        exports = instance.exports(self._store)
        self._alloc = exports["alloc"]
        self._dealloc = exports["dealloc"]
        self._init_fn = exports["init"]
        self._evaluate_fn = exports["evaluate"]
        self._memory = exports["memory"]

    # -- ABI helpers ---------------------------------------------------

    def _write_string(self, s: str) -> tuple[int, int]:
        data = s.encode("utf-8")
        ptr = self._alloc(self._store, len(data))
        self._memory.write(self._store, data, ptr)
        return ptr, len(data)

    def _read_response(self, ptr: int) -> dict[str, Any]:
        header = bytes(self._memory.read(self._store, ptr, ptr + 4))
        length = struct.unpack_from("<I", header)[0]
        body = bytes(self._memory.read(self._store, ptr + 4, ptr + 4 + length))
        self._dealloc(self._store, ptr, 4 + length)
        return json.loads(body)

    # -- Public ABI calls -----------------------------------------------

    def init(self, policy_json: str) -> dict[str, Any]:
        ptr, length = self._write_string(policy_json)
        result = self._read_response(self._init_fn(self._store, ptr, length))
        if "error" in result:
            raise PersoWasmError(result["error"])
        return result

    def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tp, tl = self._write_string(tool_name)
        ap, al = self._write_string(json.dumps(args))
        cp, cl = self._write_string(json.dumps(context))
        result = self._read_response(
            self._evaluate_fn(self._store, tp, tl, ap, al, cp, cl)
        )
        if "error" in result:
            raise PersoWasmError(result["error"])
        return result