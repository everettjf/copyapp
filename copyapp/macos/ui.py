"""Measured UI settings for comparable Mac runs; no settings are changed here."""

import math


def validate_ui(value: dict):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "appearance", "locale", "preferred_languages",
                                                    "display_bounds", "display_pixels", "backing_scale"} or
            type(value.get("schema_version")) is not int or value["schema_version"] != 1 or
            value.get("appearance") not in {"light", "dark"} or
            not isinstance(value.get("locale"), str) or not 1 <= len(value["locale"]) <= 128):
        raise ValueError("invalid measured Mac UI settings")
    languages = value["preferred_languages"]
    if (not isinstance(languages, list) or not 1 <= len(languages) <= 128 or
            any(not isinstance(item, str) or not 1 <= len(item) <= 128 for item in languages)):
        raise ValueError("invalid preferred languages")
    frame(value["display_bounds"])
    pixels = value["display_pixels"]
    if (not isinstance(pixels, dict) or set(pixels) != {"width", "height"} or
            any(type(pixels[key]) is not int or not 0 < pixels[key] <= 32768 for key in pixels) or
            type(value["backing_scale"]) not in {int, float} or not 0 < value["backing_scale"] <= 8):
        raise ValueError("invalid display pixels or scale")


def frame(value: dict):
    if (not isinstance(value, dict) or set(value) != {"x", "y", "width", "height"} or
            any(type(item) not in {int, float} or not math.isfinite(item) for item in value.values()) or
            value["width"] <= 0 or value["height"] <= 0):
        raise ValueError("invalid window/display frame")


def check_ui(expected: dict, health: dict):
    validate_ui(expected)
    actual = health["response"]["result"].get("ui_environment")
    validate_ui(actual)
    if actual != expected:
        raise ValueError("guest UI settings differ from the frozen comparison conditions")


def check_window(tree: dict, expected: dict):
    frame(expected)
    index = tree.get("focused_window_node")
    if (tree.get("source_channel") != "ax" or tree.get("truncated") is not False or
            type(index) is not int or not 0 <= index < len(tree.get("nodes", []))):
        raise ValueError("a complete focused-window observation is required")
    node = tree["nodes"][index]
    if node.get("role") != "AXWindow" or node.get("frame") != expected:
        raise ValueError("initial focused window differs from the declared placement")
