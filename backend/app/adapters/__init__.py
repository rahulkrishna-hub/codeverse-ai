from app.adapters.base import ComingSoonAdapter, LanguageAdapter
from app.adapters.python_adapter import PythonAdapter

REGISTRY: dict[str, LanguageAdapter] = {
    "python": PythonAdapter(),
    "javascript": ComingSoonAdapter("javascript", "JavaScript", "javascript"),
    "java": ComingSoonAdapter("java", "Java", "java"),
    "c": ComingSoonAdapter("c", "C", "c"),
}


def get_adapter(language: str) -> LanguageAdapter | None:
    return REGISTRY.get((language or "").lower())
