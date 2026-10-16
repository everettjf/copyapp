"""Rank local Objective-C instance methods as possible UI action entry points."""

import hashlib
import json
import re
from pathlib import Path
from typing import List, Optional


def _score(class_name: str, selector: str) -> tuple:
    name = selector.lower()
    cls = class_name.lower()
    reasons = []
    score = 0
    if re.search(r"buttonpressed|buttonpressed:|buttondidpress", name):
        score, reasons = 120, ["explicit button press handler"]
    elif re.search(r"(^|:)tapped|didtap|ontap|tapped$|tapped:", name):
        score, reasons = 110, ["explicit tap handler"]
    elif re.search(r"(^|:)pressed|didpress|clicked|didclick", name):
        score, reasons = 100, ["explicit press or click handler"]
    elif "didselect" in name or "selectionchanged" in name:
        score, reasons = 90, ["selection event handler"]
    elif name.startswith("touchesended:"):
        score, reasons = 75, ["UIKit touch completion handler"]
    elif name.startswith(("show", "open", "navigate", "add", "reset", "save",
                          "delete", "increment", "decrement")):
        score, reasons = 35, ["possible navigation or state-change handler"]
    elif "action" in name or "button" in name:
        score, reasons = 45, ["possible action or button method"]
    if not score:
        return 0, []
    if name.startswith(("set", "get", "can", "is", "has", "accessibility")):
        score -= 55
        reasons.append("property, capability or accessibility method penalty")
    if any(part in cls for part in ("appdelegate", "application", "scene")):
        score -= 35
        reasons.append("application lifecycle class penalty")
    if any(part in cls for part in ("controller", "model", "view")):
        score += 5
        reasons.append("UI or model class")
    return max(score, 0), reasons


def _label_matches(selector: str, label: str) -> bool:
    """Accept only an exact action suffix present as a UI label word."""
    action = re.fullmatch(
        r"(show|open|navigate|add|reset|save|delete|increment|decrement)"
        r"([A-Z][A-Za-z0-9]*):?", selector)
    if action is None:
        return False
    words = [word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9]*", label)
             if len(word) >= 3]
    if not words:
        return False
    if words[0] in {"show", "open", "navigate", "add", "reset", "save",
                    "delete", "increment", "decrement"} and words[0] != action.group(1):
        return False
    return action.group(2).casefold() in words


def scout_methods(objc_index: Path, limit: int = 20,
                  tap_labels: Optional[List[str]] = None) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("method scout limit must be between 1 and 100")
    index = json.loads(objc_index.read_text(encoding="utf-8"))
    if (index.get("schema_version") != 1 or
            not isinstance(index.get("binary_sha256"), str) or
            not isinstance(index.get("classes"), list)):
        raise ValueError("invalid Objective-C method index")
    ranked = []
    seen = set()
    for cls in index["classes"]:
        if not isinstance(cls, dict) or not isinstance(cls.get("name"), str):
            continue
        for method in cls.get("instance_methods", []):
            if not isinstance(method, dict) or not isinstance(method.get("selector"), str):
                continue
            key = (cls["name"], method["selector"])
            if key in seen:
                continue
            seen.add(key)
            score, reasons = _score(*key)
            if score:
                ranked.append({"class": key[0], "selector": key[1],
                               "method": key[0] + "::" + key[1],
                               "static_address": method.get("imp"),
                               "score": score, "reasons": reasons})
    ranked.sort(key=lambda item: (-item["score"], item["class"], item["selector"]))
    leader = ranked[0] if ranked else None
    runner = ranked[1] if len(ranked) > 1 else None
    margin = leader["score"] - runner["score"] if runner else None
    strong = leader if leader and leader["score"] >= 100 and (margin is None or margin >= 20) else None
    selected = [strong] if strong else []
    label_matches = []
    ambiguous_labels = []
    for label in tap_labels or []:
        if not isinstance(label, str):
            continue
        matches = [item for item in ranked if _label_matches(item["selector"], label)]
        if len(matches) == 1:
            label_matches.append({"label": label, "method": matches[0]["method"]})
            if matches[0] not in selected:
                selected.append(matches[0])
        elif len(matches) > 1:
            ambiguous_labels.append(label)
    if ambiguous_labels and strong is None:
        selected = []
    if len(selected) > 32:
        selected = []
    selection_basis = ("combined_high_score_and_labels" if strong and label_matches else
                       "unique_high_score_action" if strong else
                       "unique_exact_tap_labels" if selected else None)
    return {"schema_version": 1, "kind": "objc_ui_method_scout",
            "binary_sha256": index["binary_sha256"],
            "selection_policy": "unique action method with score >=100 and >=20 lead, plus unique exact action suffix matches for tap labels; ambiguous labels stop auto-selection unless a strong action exists; heuristic only",
            "status": "selected" if selected else "needs_review",
            "selected_method": selected[0]["method"] if len(selected) == 1 else None,
            "selected_methods": [item["method"] for item in selected],
            "selection_basis": selection_basis, "label_matches": label_matches,
            "ambiguous_labels": ambiguous_labels,
            "top_score_margin": margin, "ranked": ranked[:limit],
            "limitation": "Names suggest possible UI entry points; they do not prove a method handles the supplied flow. An ambiguous label without a strong action, or more than 32 matches, stops before device interaction."}


def _class_leaf(name: str) -> str:
    """Return the final Swift/Objective-C class component when unambiguous."""
    if name.startswith("_TtC"):
        cursor = 4
        parts = []
        while cursor < len(name) and name[cursor].isdigit():
            end = cursor
            while end < len(name) and name[end].isdigit():
                end += 1
            length = int(name[cursor:end])
            part = name[end:end + length]
            if length < 1 or len(part) != length:
                return ""
            parts.append(part)
            cursor = end + length
        return parts[-1] if cursor == len(name) and parts else ""
    return name.rsplit(".", 1)[-1]


def refine_scout_with_view_tree(scout: dict, objc_index: Path,
                                view_tree: Path, tap_labels: List[str]) -> dict:
    """Use exact visible button classes to choose unique action-method leads.

    The output remains a candidate selection; only the later runtime trace can
    show whether that method was called during the gesture.
    """
    index = json.loads(objc_index.read_text(encoding="utf-8"))
    raw_tree = view_tree.read_bytes()
    tree = json.loads(raw_tree)
    nodes = tree.get("nodes")
    if (index.get("binary_sha256") != scout.get("binary_sha256") or
            tree.get("type") != "view_tree" or not isinstance(nodes, list) or
            not 1 <= len(nodes) <= 500):
        raise ValueError("runtime view tree or Objective-C index is invalid")
    actions = {}
    for cls in index.get("classes", []):
        if not isinstance(cls, dict) or not isinstance(cls.get("name"), str):
            continue
        leaf = _class_leaf(cls["name"])
        if not leaf:
            continue
        for method in cls.get("instance_methods", []):
            selector = method.get("selector") if isinstance(method, dict) else None
            if not isinstance(selector, str):
                continue
            score, _ = _score(cls["name"], selector)
            if score >= 100:
                actions.setdefault(leaf, set()).add(cls["name"] + "::" + selector)
    matches = []
    for label in dict.fromkeys(item for item in tap_labels
                               if isinstance(item, str) and item):
        candidates = set()
        origin_ids = []
        for position, node in enumerate(nodes):
            if (not isinstance(node, dict) or node.get("id") != position or
                    (node.get("parent") is not None and
                     (type(node["parent"]) is not int or
                      not 0 <= node["parent"] < position))):
                raise ValueError("runtime view tree node order is invalid")
            if label not in (node.get("accessibility_label"), node.get("text"),
                             node.get("title")):
                continue
            origin_ids.append(position)
            current = position
            while current is not None:
                ancestor = nodes[current]
                leaf = _class_leaf(str(ancestor.get("class_name") or ""))
                methods = actions.get(leaf, set())
                if methods:
                    candidates.update(methods)
                    break
                current = ancestor.get("parent")
        if len(candidates) == 1:
            matches.append({"label": label, "node_ids": origin_ids,
                            "method": next(iter(candidates))})
    selected = list(dict.fromkeys(item["method"] for item in matches))
    result = dict(scout)
    result["runtime_view_sha256"] = hashlib.sha256(raw_tree).hexdigest()
    result["runtime_view_matches"] = matches
    if selected and len(selected) <= 32:
        result.update({"status": "selected", "selected_method": selected[0] if
                       len(selected) == 1 else None, "selected_methods": selected,
                       "selection_basis": "runtime_visible_class_unique_action"})
    return result
