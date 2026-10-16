"""Bounded point-space gesture contract shared by replay and evidence gates."""

import math
from typing import Optional


GESTURE_ACTIONS = frozenset({"swipe", "long_press", "double_tap"})


def gesture_params(step: dict, width: Optional[float] = None,
                   height: Optional[float] = None) -> dict:
    action = step.get("action")
    if action not in GESTURE_ACTIONS:
        raise ValueError("unsupported gesture action")
    if width is None or height is None:
        width = height = 10000
    if (type(width) not in (int, float) or type(height) not in (int, float) or
            not math.isfinite(width) or not math.isfinite(height) or
            width <= 0 or height <= 0):
        raise ValueError("invalid gesture screen bounds")
    points = ("from_x", "from_y", "to_x", "to_y") if action == "swipe" else ("x", "y")
    result = {"action": action}
    for name in points:
        value = step.get(name)
        bound = width if name.endswith("x") else height
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= bound:
            raise ValueError(f"invalid {action} coordinate: {name}")
        result[name] = value
    if action == "swipe":
        delta_x = result["to_x"] - result["from_x"]
        delta_y = result["to_y"] - result["from_y"]
        if math.hypot(delta_x, delta_y) < 15:
            raise ValueError("swipe movement is too short")
        if delta_x != 0 and delta_y != 0:
            raise ValueError("swipe must be horizontal or vertical for both UI backends")
        defaults = {"duration_ms": 300, "steps": 20}
        limits = {"duration_ms": (100, 2000), "steps": (2, 60)}
    elif action == "long_press":
        defaults = {"duration_ms": 800}
        limits = {"duration_ms": (300, 3000)}
    else:
        defaults = {"interval_ms": 100}
        limits = {"interval_ms": (50, 300)}
    allowed = {"action", "wait_ms", *points, *defaults}
    if set(step) - allowed:
        raise ValueError(f"unsupported {action} parameters: {sorted(set(step) - allowed)}")
    for name, default in defaults.items():
        value = step.get(name, default)
        low, high = limits[name]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"invalid {action} parameter: {name}")
        result[name] = value
    return result
