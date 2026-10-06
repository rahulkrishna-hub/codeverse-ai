"""Isolated execution worker.  Run as:  python -I worker.py  (request JSON on stdin).

It is spawned by runner.py inside a throw-away process (own session, rlimits,
no network namespace if available, unprivileged uid if possible). It writes
newline-delimited JSON records to the REAL stdout pipe:

    {"t": "ev",  "e": {...trace event...}}
    {"t": "end", ...summary...}

User ``print`` output never touches the real stdout: it is captured in-process.
This file is NOT a security boundary by itself - see runner.py / README.
"""
import builtins
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analysis as A      # noqa: E402
import serialize as S     # noqa: E402
import tracer as T        # noqa: E402

import resource_stub as resource

SAFE_BUILTIN_NAMES = """
abs all any ascii bin bool bytes callable chr complex dict divmod enumerate filter float format
frozenset hash hex int isinstance issubclass iter len list map max min next oct ord pow print range
repr reversed round set slice sorted str sum tuple zip
True False None Ellipsis NotImplemented
""".split()


def _exception_names():
    return [n for n in dir(builtins) if isinstance(getattr(builtins, n), type)
            and issubclass(getattr(builtins, n), BaseException)]


def build_builtins():
    safe = {n: getattr(builtins, n) for n in SAFE_BUILTIN_NAMES if hasattr(builtins, n)}
    for n in _exception_names():
        safe[n] = getattr(builtins, n)

    def _input(*_a, **_k):
        raise RuntimeError("input() is not supported in the visualizer. "
                           "Put your test values in variables instead (for example: name = 'Asha').")

    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0 or name.split(".")[0] not in A.ALLOWED_MODULES:
            raise ImportError(f"Importing '{name}' is not allowed. Allowed modules: "
                              f"{', '.join(sorted(A.ALLOWED_MODULES))}.")
        return real_import(name, globals, locals, fromlist, level)

    safe["input"] = _input
    safe["__import__"] = _import
    safe["__name__"] = "builtins"
    return safe


def apply_limits(opts):
    cpu = int(opts.get("cpu_seconds", 4))
    mem = int(opts.get("memory_mb", 768)) * 1024 * 1024
    for res, val in ((resource.RLIMIT_CPU, (cpu, cpu + 1)),
                     (resource.RLIMIT_AS, (mem, mem)),
                     (resource.RLIMIT_FSIZE, (0, 0)),
                     (resource.RLIMIT_CORE, (0, 0)),
                     (resource.RLIMIT_NOFILE, (32, 32))):
        try:
            resource.setrlimit(res, val)
        except (ValueError, OSError):
            pass


def main():
    req = json.loads(sys.stdin.read())
    source = req["source_code"]
    opts = req.get("options", {})

    # Platform-independent stdout proxy: replace sys.stdout with a pipe we own,
    # and buffer all send() output here.  On Unix the original code used fd dup/
    # dup2 tricks; on Windows those APIs are unavailable, so we take the simpler
    # route of writing to the real sys.stdout via a dedicated writer.
    _send_buf = []

    def send(obj):
        line = json.dumps(obj, allow_nan=False, separators=(",", ":")) + "\n"
        _send_buf.append(line)

    # Flush accumulated send() output to the REAL stdout at the very end, after
    # user stdout/stderr have been restored.
    def _flush():
        try:
            encoded = "".join(_send_buf).encode("utf-8")
            os.write(1, encoded)
        except Exception:
            pass

    import random, math, string, itertools, collections, heapq, bisect   # noqa: F401  preload before dropping rights
    apply_limits(opts)
    if opts.get("drop_privileges") and os.geteuid() == 0:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
        os.chdir("/")
    sys.set_int_max_str_digits(5000)
    sys.setrecursionlimit(int(opts.get("max_call_depth", 200)))

    tree, issue = A.parse_source(source)
    if issue is None:
        issue = A.check_supported(tree)
    if issue is not None:
        send({"t": "end", "status": "syntax_error" if issue.kind == "syntax_error" else "unsupported",
              "error": issue.as_dict(), "stdout": "", "stderr": "", "final_variables": {},
              "event_count": 0, "failed_event_index": None, "truncated": False})
        return

    idx = A.build_index(source, tree)
    out = T.OutputCapture(int(opts.get("max_output_chars", 20000)))
    tracer = T.Tracer(idx, lambda ev: send({"t": "ev", "e": ev}), out, int(opts.get("max_events", 1500)),
                      on_current=lambda ln: send({"t": "cur", "l": ln}))

    import random
    random.seed(0)                       # deterministic traces where practical

    code = compile(tree, A.USER_FILE, "exec")
    g = {"__builtins__": build_builtins(), "__name__": "__main__"}
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = out
    sys.stderr = T.OutputCapture(5000)
    status, error, exc_obj = "completed", None, None
    sys.settrace(tracer.global_trace)
    try:
        exec(code, g)
    except T.TraceLimit as e:
        status = "truncated"
        error = {"type": "StepLimit", "message": str(e), "line": None, "traceback": []}
    except T.OutputLimit as e:
        status = "truncated"
        error = {"type": "OutputLimit", "message": str(e), "line": None, "traceback": []}
    except BaseException as e:           # noqa: BLE001 - user code may raise anything
        status, exc_obj = "error", e
    finally:
        sys.settrace(None)
        sys.stdout, sys.stderr = real_stdout, real_stderr
    try:
        tracer._finalize("return", None, None)          # flush the last pending event
    except T.TraceLimit:
        pass

    # Restore the real stdout/stderr BEFORE flushing our protocol messages so the
    # parent process receives them on the pipe.
    sys.stdout, sys.stderr = real_stdout, real_stderr

    failed_idx = None
    if exc_obj is not None:
        tb_entries = []
        tb = exc_obj.__traceback__
        last_line = None
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == A.USER_FILE:
                last_line = tb.tb_lineno
                name = tb.tb_frame.f_code.co_name
                tb_entries.append({"function": "<module>" if name == "<module>" else name,
                                   "line": tb.tb_lineno, "source": idx.source_line(tb.tb_lineno).strip()})
            tb = tb.tb_next
        seq = tracer.seen_exc.get(id(exc_obj))
        failed_idx = tracer.exc_events.get(seq) if seq else None
        error = {"type": type(exc_obj).__name__, "message": T._exc_message(exc_obj),
                 "line": last_line, "traceback": tb_entries, "column": None}
    final_vars = {}
    try:
        final_vars = S.snapshot_scope(g)
    except BaseException:
        pass
    send({"t": "end", "status": status, "error": error, "stdout": out.text(),
          "stderr": "", "final_variables": final_vars, "event_count": tracer.count,
          "failed_event_index": failed_idx, "truncated": tracer.truncated or status == "truncated"})
    _flush()


if __name__ == "__main__":
    main()
