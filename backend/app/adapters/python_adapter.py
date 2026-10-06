"""Python adapter: AST pre-checks in this process, execution + tracing in the isolated worker."""
from __future__ import annotations

import signal
import sys
from typing import Optional

from app.adapters.base import LanguageAdapter
from app.config import settings
from app.engine import analysis as A
from app.engine import runner

_IS_WINDOWS = sys.platform == "win32"

class PythonAdapter(LanguageAdapter):
    id = "python"
    name = "Python"
    status = "available"
    file_extension = ".py"
    monaco_language = "python"

    @property
    def supported_features(self) -> list[str]:
        return list(A.SUPPORTED_FEATURES)

    def check(self, source: str) -> Optional[dict]:
        tree, issue = A.parse_source(source)          # parsing never executes anything
        if issue is None:
            issue = A.check_supported(tree)
        return issue.as_dict() if issue else None

    def execute(self, source: str, options: dict) -> dict:
        max_events = int(options.get("max_events") or settings.max_events)
        max_events = max(10, min(max_events, settings.max_events_ceiling))
        res = runner.run_worker(source, max_events, options.get("wall_timeout_s"))
        events = res.events
        end = res.end or {}
        status = end.get("status")
        error = end.get("error")
        stdout = end.get("stdout")
        final_vars = end.get("final_variables")

        if res.end is None:   # worker never finished: classify why
            partial_out = "".join(e.get("stdout_delta", "") for e in events)
            stdout = partial_out
            last_vars = {}
            for e in reversed(events):
                if e.get("scope") == "<module>" and e.get("variables_after") is not None:
                    last_vars = e["variables_after"]
                    break
            final_vars = last_vars
            if _IS_WINDOWS:
                cpu_kill = False
            else:
                cpu_signals = tuple(-s for s in (signal.SIGXCPU, signal.SIGKILL) if s is not None)
                cpu_kill = res.returncode in cpu_signals and not res.timed_out and not res.protocol_overflow
            if res.timed_out or cpu_kill:
                status = "timeout"
                error = {"type": "Timeout", "kind": "timeout",
                         "message": f"The program ran longer than the time limit and was stopped. "
                                    "It may contain an infinite loop or a very heavy calculation.",
                         "line": res.current_line, "traceback": []}
            elif res.protocol_overflow:
                status = "truncated"
                error = {"type": "TraceTooLarge", "kind": "truncated",
                         "message": "The execution trace became too large and was stopped.", "line": None, "traceback": []}
            else:
                status = "crashed"
                error = {"type": "WorkerCrash", "kind": "crashed",
                         "message": "The isolated execution worker stopped unexpectedly (possibly out of memory).",
                         "line": None, "traceback": [], "detail": res.stderr_tail[-400:]}
        else:
            fi = end.get("failed_event_index")
            if fi is not None and 0 <= fi < len(events):
                events[fi]["status"] = "failed"
                if error is not None:
                    error["event_index"] = fi
            if status == "error" and error is not None and error.get("event_index") is None and events:
                # fall back to the last event on the failing line
                for e in reversed(events):
                    if e["line_number"] == error.get("line"):
                        e["status"] = "failed"; error["event_index"] = e["event_index"]; break

        stderr = _format_traceback(error) if status in ("error",) and error else ""
        return {
            "execution_status": status, "trace_events": events, "final_variables": final_vars or {},
            "stdout": stdout or "", "stderr": stderr, "error": error,
            "truncated": bool(end.get("truncated")) or status in ("truncated", "timeout"),
            "sandbox": res.sandbox,
            "stats": {"event_count": len(events), "elapsed_ms": res.elapsed_ms},
            "limits": {"max_events": max_events, "wall_timeout_s": settings.wall_timeout_s,
                       "cpu_seconds": settings.cpu_seconds, "memory_mb": settings.memory_mb,
                       "max_output_chars": settings.max_output_chars},
        }


def _format_traceback(err: dict) -> str:
    lines = ["Traceback (most recent call last):"]
    for t in err.get("traceback", []):
        lines.append(f'  File "<your code>", line {t["line"]}, in {t["function"]}')
        if t.get("source"):
            lines.append(f'    {t["source"]}')
    lines.append(f'{err.get("type")}: {err.get("message")}')
    return "\n".join(lines)
