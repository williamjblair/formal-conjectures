"""Strict, content-addressed JSON helpers for review evidence.

The profile is the integer-only I-JSON subset used by the extracted review
engine.  It rejects duplicate keys, floating-point values, oversized inputs,
and ambiguous UTF-8 before computing a canonical SHA-256 identity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence


MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_CONTAINER_ITEMS = 100_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991


class AuditError(ValueError):
    """Raised when retained review evidence violates the closed contract."""


def _pairs_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_number(token: str) -> Any:
    raise AuditError(f"non-integer JSON number is not supported: {token!r}")


def _validate(value: Any, location: str = "$", depth: int = 0) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise AuditError(f"JSON nesting exceeds {MAX_JSON_DEPTH} at {location}")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise AuditError(f"integer outside canonical profile at {location}")
        return value
    if isinstance(value, float):
        raise AuditError(f"floating-point number at {location}")
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as error:
            raise AuditError(f"lone surrogate at {location}") from error
        return value
    if isinstance(value, list):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise AuditError(f"array has more than {MAX_CONTAINER_ITEMS} items at {location}")
        return [_validate(item, f"{location}[{index}]", depth + 1) for index, item in enumerate(value)]
    if isinstance(value, dict):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise AuditError(f"object has more than {MAX_CONTAINER_ITEMS} members at {location}")
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise AuditError(f"non-string key at {location}")
            key = _validate(raw_key, f"{location}.<key>", depth + 1)
            if key in result:
                raise AuditError(f"duplicate key at {location}: {key!r}")
            result[key] = _validate(item, f"{location}.{key}", depth + 1)
        return result
    raise AuditError(f"unsupported JSON value at {location}: {type(value).__name__}")


def parse_json_bytes(raw: bytes, *, label: str = "input") -> Any:
    if len(raw) > MAX_INPUT_BYTES:
        raise AuditError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{label} has a UTF-8 BOM")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise AuditError(f"{label} is not strict UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except AuditError:
        raise
    except json.JSONDecodeError as error:
        raise AuditError(f"malformed JSON in {label}: {error.msg}") from error
    return _validate(value)


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be", "strict")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise AuditError("integer outside canonical profile")
        return str(value)
    if isinstance(value, str):
        return json.dumps(_validate(value), ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        normalized = _validate(value)
        return "{" + ",".join(
            _encode(key) + ":" + _encode(normalized[key])
            for key in sorted(normalized, key=_utf16_sort_key)
        ) + "}"
    raise AuditError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return _encode(_validate(value)).encode("utf-8", "strict")


def sha256_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def content_root(value: Any) -> str:
    return sha256_digest(canonical_bytes(value))


def write_canonical(path: str | Path, value: Any, *, sidecar: bool = False) -> None:
    destination = Path(path)
    raw = canonical_bytes(value) + b"\n"
    destination.write_bytes(raw)
    if sidecar:
        destination.with_name(destination.name + ".sha256").write_text(
            sha256_digest(raw) + "\n", encoding="utf-8"
        )
