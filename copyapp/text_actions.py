"""Bounded text-input action used by UI replay and evidence validation."""

import hashlib


TYPE_ACTION = "type_text"


def type_params(step: dict) -> dict:
    if not isinstance(step, dict) or step.get("action") != TYPE_ACTION:
        raise ValueError("unsupported text action")
    unknown = set(step) - {"action", "text", "wait_ms"}
    if unknown:
        raise ValueError(f"unsupported text parameters: {sorted(unknown)}")
    value = step.get("text")
    if (not isinstance(value, str) or not value or len(value) > 128 or
            any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("type_text requires 1–128 printable characters")
    encoded = value.encode("utf-8")
    if len(encoded) > 512:
        raise ValueError("type_text exceeds 512 UTF-8 bytes")
    return {"action": TYPE_ACTION, "text_sha256": hashlib.sha256(encoded).hexdigest(),
            "characters": len(value), "utf8_bytes": len(encoded)}
