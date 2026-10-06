"""Language adapter interface.

A language adapter owns three things for one programming language:
  1. parsing / static checks        -> ``check``
  2. isolated execution + tracing   -> ``execute``
  3. a description of what it can visualise -> ``supported_features``
New languages (Java, JavaScript, C) implement this interface and register in
``app/adapters/__init__.py``; the HTTP layer and the frontend do not change because
every adapter must return the same trace-event schema (see README / schemas.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LanguageAdapter(ABC):
    id: str = ""
    name: str = ""
    status: str = "available"          # "available" | "coming_soon"
    file_extension: str = ""
    monaco_language: str = ""

    @property
    @abstractmethod
    def supported_features(self) -> list[str]: ...

    @abstractmethod
    def check(self, source: str) -> Optional[dict]:
        """Static check. Return an error dict (same shape as ``error`` in the response) or None."""

    @abstractmethod
    def execute(self, source: str, options: dict) -> dict:
        """Run + trace. Must return the full /api/execute result body (without execution_id)."""

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "status": self.status,
                "monaco_language": self.monaco_language, "supported_features": self.supported_features}


class ComingSoonAdapter(LanguageAdapter):
    status = "coming_soon"

    def __init__(self, id: str, name: str, monaco_language: str):
        self.id, self.name, self.monaco_language = id, name, monaco_language

    @property
    def supported_features(self) -> list[str]:
        return []

    def check(self, source: str) -> Optional[dict]:
        return {"type": "LanguageNotAvailable", "kind": "language_unavailable",
                "message": f"{self.name} execution is not implemented yet (coming soon). Only Python runs today.",
                "line": None, "column": None, "hint": None}

    def execute(self, source: str, options: dict) -> dict:
        raise NotImplementedError(f"{self.name} adapter is not implemented")
