"""Central configuration. Every value can be overridden with an environment variable
(see .env.example). Nothing here contains secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # execution limits (hard server-side ceilings; requests may only lower them)
    max_source_chars: int = _int("CV_MAX_SOURCE_CHARS", 20000)
    max_events: int = _int("CV_MAX_EVENTS", 1500)
    max_events_ceiling: int = _int("CV_MAX_EVENTS_CEILING", 3000)
    wall_timeout_s: float = float(os.environ.get("CV_WALL_TIMEOUT_S", 6))
    cpu_seconds: int = _int("CV_CPU_SECONDS", 4)
    memory_mb: int = _int("CV_MEMORY_MB", 768)
    max_output_chars: int = _int("CV_MAX_OUTPUT_CHARS", 20000)
    max_protocol_bytes: int = _int("CV_MAX_PROTOCOL_BYTES", 24 * 1024 * 1024)
    max_call_depth: int = _int("CV_MAX_CALL_DEPTH", 200)
    nproc_limit: int = _int("CV_NPROC_LIMIT", 100)
    # sandbox layers (all best-effort and reported honestly in every response)
    use_network_isolation: bool = os.environ.get("CV_NETWORK_ISOLATION", "1") == "1"
    drop_privileges: bool = os.environ.get("CV_DROP_PRIVILEGES", "1") == "1"
    # AI provider
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_model: str = os.environ.get("CODEVERSE_LLM_MODEL", "claude-sonnet-5-5")
    # storage
    data_dir: str = os.environ.get("CV_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
    database_url: str = os.environ.get("DATABASE_URL", "")


settings = Settings()
