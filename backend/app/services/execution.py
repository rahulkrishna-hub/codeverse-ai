"""Framework-neutral execution service used by the HTTP layer."""
from __future__ import annotations

import uuid

from app.adapters import REGISTRY, get_adapter
from app.config import settings


def _err(kind: str, type_: str, message: str, status: str, language: str = "python") -> dict:
    return {
        "execution_id": uuid.uuid4().hex, "execution_status": status, "language": language,
        "trace_events": [], "final_variables": {}, "stdout": "", "stderr": "",
        "error": {"type": type_, "kind": kind, "message": message, "line": None, "column": None, "hint": None},
        "supported_features": [], "truncated": False, "sandbox": None, "stats": {"event_count": 0, "elapsed_ms": 0},
    }


def execute(source_code: str, language: str = "python", execution_options: dict | None = None) -> dict:
    options = execution_options or {}
    adapter = get_adapter(language)
    if adapter is None:
        valid = ", ".join(sorted(REGISTRY))
        return _err("invalid_language", "InvalidLanguage",
                    f"Unknown language '{language}'. Choose one of: {valid}.", "invalid_language", language)
    if adapter.status != "available":
        e = adapter.check(source_code) or {}
        out = _err("language_unavailable", "LanguageNotAvailable", e.get("message", "Language not available."),
                   "language_unavailable", adapter.id)
        return out
    if not source_code or not source_code.strip():
        return _err("empty", "EmptyCode", "There is no code to run. Write a few lines first.", "empty", adapter.id)
    if len(source_code) > settings.max_source_chars:
        return _err("too_large", "SourceTooLarge",
                    f"The code is longer than {settings.max_source_chars} characters.", "too_large", adapter.id)
    pre = adapter.check(source_code)
    if pre is not None:
        out = _err(pre["kind"], pre["type"], pre["message"], pre["kind"], adapter.id)
        out["error"].update({k: pre.get(k) for k in ("line", "column", "hint")})
        out["supported_features"] = adapter.supported_features
        return out
    result = adapter.execute(source_code, options)
    result.update({"execution_id": uuid.uuid4().hex, "language": adapter.id,
                   "supported_features": adapter.supported_features})
    return result
