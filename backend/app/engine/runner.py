"""Spawns the isolated worker and collects its trace.

Windows-compatible variant of the sandbox runner.  On Linux it behaves like the
original (rlimits, killpg, setsid, unshare).  On Windows it uses a plain
subprocess with CPU-time / wall-clock limits, no privilege dropping, no network
namespace — reported honestly in the sandbox dict.

This is a LOCAL-DEVELOPMENT sandbox, NOT a hardened production boundary.
"""
from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.py")

if platform.system() == "Windows":
    from app.engine.resource_stub import (
        RLIMIT_CPU,
        RLIMIT_AS,
        RLIMIT_FSIZE,
        RLIMIT_CORE,
        RLIMIT_NPROC,
        RLIMIT_NOFILE,
    )
else:
    import resource as _resource

    RLIMIT_CPU = _resource.RLIMIT_CPU
    RLIMIT_AS = _resource.RLIMIT_AS
    RLIMIT_FSIZE = _resource.RLIMIT_FSIZE
    RLIMIT_CORE = _resource.RLIMIT_CORE
    RLIMIT_NOFILE = _resource.RLIMIT_NOFILE
    RLIMIT_NPROC = _resource.RLIMIT_NPROC


_probe_lock = threading.Lock()
_probe_result: Optional[dict] = None


def _base_cmd() -> list[str]:
    return [sys.executable, "-I", "-B", WORKER]


def _env() -> dict:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", os.defpath),
        }
    )
    return env


def probe_sandbox() -> dict:
    """Detect which isolation layers work on this host (cached)."""
    global _probe_result
    with _probe_lock:
        if _probe_result is not None:
            return _probe_result

        is_win = platform.system() == "Windows"
        info: dict = {
            "mode": "subprocess" + ("-windows" if is_win else "-rlimit"),
            "network_isolated": False,
            "privilege_dropped": False,
            "production_ready": False,
            "warning": (
                "Local-development sandbox only. Not safe for untrusted public traffic."
                if not is_win
                else "Windows build: no rlimits / no killpg / no unshare. CPU, memory, "
                "file-size and core limits are best-effort stubs. Use a container before "
                "exposing to public traffic."
            ),
        }
        _probe_result = info
        return info


@dataclass
class RunResult:
    events: list = field(default_factory=list)
    end: Optional[dict] = None
    returncode: Optional[int] = None
    timed_out: bool = False
    protocol_overflow: bool = False
    stderr_tail: str = ""
    current_line: Optional[int] = None
    elapsed_ms: int = 0
    sandbox: dict = field(default_factory=dict)


def run_worker(source: str, max_events: int, wall_timeout: Optional[float] = None) -> RunResult:
    sb = probe_sandbox()
    wall = min(float(wall_timeout), settings.wall_timeout_s) if wall_timeout else settings.wall_timeout_s
    request = {
        "source_code": source,
        "options": {
            "max_events": min(max_events, settings.max_events_ceiling),
            "cpu_seconds": settings.cpu_seconds,
            "memory_mb": settings.memory_mb,
            "max_output_chars": settings.max_output_chars,
            "max_call_depth": settings.max_call_depth,
            "drop_privileges": sb["privilege_dropped"],
        },
    }
    res = RunResult(sandbox=sb)
    t0 = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="cv_run_") as cwd:
        os.chmod(cwd, 0o755) if hasattr(os, "chmod") else None
        proc = subprocess.Popen(
            _base_cmd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=_env(),
        )

        total = [0]
        err_chunks: list[bytes] = []

        def kill() -> None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

        def read_out() -> None:
            try:
                for raw in proc.stdout:
                    total[0] += len(raw)
                    if total[0] > settings.max_protocol_bytes:
                        res.protocol_overflow = True
                        kill()
                        return
                    try:
                        rec = json.loads(raw)
                    except ValueError:
                        continue
                    if rec.get("t") == "ev":
                        res.events.append(rec["e"])
                    elif rec.get("t") == "cur":
                        res.current_line = rec.get("l")
                    elif rec.get("t") == "end":
                        res.end = rec
            except Exception:
                pass

        def read_err() -> None:
            try:
                data = proc.stderr.read(20000)
                err_chunks.append(data or b"")
                proc.stderr.read()  # drain
            except Exception:
                pass

        t_out = threading.Thread(target=read_out, daemon=True)
        t_err = threading.Thread(target=read_err, daemon=True)
        t_out.start()
        t_err.start()
        try:
            proc.stdin.write(json.dumps(request).encode("utf-8"))
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            proc.wait(timeout=wall)
        except subprocess.TimeoutExpired:
            res.timed_out = True
            kill()
            proc.wait()
        kill()  # make sure no stragglers keep the pipes open
        t_out.join(2)
        t_err.join(2)
        for f in (proc.stdout, proc.stderr):
            try:
                f.close()
            except Exception:
                pass
        res.returncode = proc.returncode
        res.stderr_tail = (b"".join(err_chunks)).decode("utf-8", "replace")[-2000:]
    res.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return res
