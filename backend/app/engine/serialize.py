"""Turn live Python values into JSON-safe, size-bounded descriptors.

STDLIB ONLY, flat module (imported as ``serialize`` inside the worker).

Descriptor shape (always has ``type`` and ``repr``):
  int/float/str/bool/NoneType -> {"type","repr","value"}
  list/tuple/set/frozenset    -> {"type","repr","len","items":[desc...],"truncated"}
  dict                        -> {"type","repr","len","entries":[{"key":desc,"value":desc}],"truncated"}
  function                    -> {"type":"function","repr","name","params"}
  anything else               -> {"type": <class name>,"repr"}
"""
from __future__ import annotations

import math
import types
from typing import Any

MAX_DEPTH = 4
MAX_ITEMS = 40
MAX_STR = 120
MAX_REPR = 160


def _safe_repr(v: Any, limit: int = MAX_REPR) -> str:
    try:
        r = repr(v)
    except Exception:
        return "<unrepresentable>"
    return r if len(r) <= limit else r[: limit - 1] + "…"


def describe(v: Any, depth: int = 0) -> dict:
    t = type(v)
    name = t.__name__
    if v is None:
        return {"type": "NoneType", "repr": "None", "value": None}
    if t is bool:
        return {"type": "bool", "repr": repr(v), "value": v}
    if t is int:
        r = _safe_repr(v)
        return {"type": "int", "repr": r, "value": v if abs(v) < 2**53 else None}
    if t is float:
        return {"type": "float", "repr": repr(v), "value": v if math.isfinite(v) else None}
    if t is str:
        d = {"type": "str", "repr": _safe_repr(v), "value": v[:MAX_STR]}
        if len(v) > MAX_STR:
            d["truncated"] = True
        return d
    if isinstance(v, types.FunctionType):
        try:
            params = list(v.__code__.co_varnames[: v.__code__.co_argcount])
        except Exception:
            params = []
        return {"type": "function", "repr": f"<function {v.__name__}>", "name": v.__name__, "params": params}
    if t in (list, tuple, set, frozenset):
        items = list(v) if t in (list, tuple) else _sorted_set(v)
        d = {"type": name, "repr": _safe_repr(v), "len": len(v), "truncated": len(items) > MAX_ITEMS}
        d["items"] = [] if depth >= MAX_DEPTH else [describe(x, depth + 1) for x in items[:MAX_ITEMS]]
        if depth >= MAX_DEPTH and len(v):
            d["truncated"] = True
        return d
    if t is dict:
        d = {"type": "dict", "repr": _safe_repr(v), "len": len(v), "truncated": len(v) > MAX_ITEMS}
        if depth >= MAX_DEPTH:
            d["entries"] = []
            d["truncated"] = d["truncated"] or len(v) > 0
        else:
            entries = []
            for i, (k, val) in enumerate(v.items()):
                if i >= MAX_ITEMS:
                    break
                entries.append({"key": describe(k, depth + 1), "value": describe(val, depth + 1)})
            d["entries"] = entries
        return d
    return {"type": name, "repr": _safe_repr(v)}


def _sorted_set(s) -> list:
    items = list(s)
    try:
        return sorted(items)
    except Exception:
        return sorted(items, key=lambda x: _safe_repr(x, 60))


def snapshot_scope(mapping) -> dict:
    """Snapshot a frame's variables, hiding dunder names and the builtins reference."""
    out = {}
    try:
        items = list(mapping.items())
    except Exception:
        return out
    for k, v in items:
        if isinstance(k, str) and k.startswith("__"):
            continue
        # modules (from `import math`) are shown as a small card, not expanded
        if isinstance(v, types.ModuleType):
            out[k] = {"type": "module", "repr": f"<module '{getattr(v, '__name__', k)}'>"}
            continue
        out[k] = describe(v)
    return out


def descriptor_equal(a: dict, b: dict) -> bool:
    return a.get("type") == b.get("type") and a.get("repr") == b.get("repr") and \
        a.get("items") == b.get("items") and a.get("entries") == b.get("entries")


def diff_scopes(before: dict, after: dict) -> list[dict]:
    changes = []
    for name, d in after.items():
        if name not in before:
            changes.append({"name": name, "kind": "created", "previous": None, "current": d})
        elif not descriptor_equal(before[name], d):
            changes.append({"name": name, "kind": "updated", "previous": before[name], "current": d})
    for name, d in before.items():
        if name not in after:
            changes.append({"name": name, "kind": "deleted", "previous": d, "current": None})
    return changes
