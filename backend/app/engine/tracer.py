"""sys.settrace based execution tracer producing CodeVerse trace events.

STDLIB ONLY, flat module (imported as ``tracer`` inside the worker).

Design
* Exactly ONE event is "pending" at a time. It is created when a trace event
  (line / call / return) arrives and finalised when the NEXT trace event arrives.
  That is what lets us record ``variables_after`` / ``stdout_delta`` / branch
  taken / loop exit without hardcoding anything.
* A statement that calls a user function is split: the call line, the function's
  own events, then a ``resume`` event for the remainder of the caller's line
  (this is when e.g. ``result = add(2, 3)`` actually stores the value).
"""
from __future__ import annotations

import ast
from typing import Any, Callable, Optional

import analysis as A
import serialize as S

MAX_STACK = 30


class TraceLimit(BaseException):
    """Raised from the trace hook when the event budget is exhausted."""


class OutputLimit(BaseException):
    """Raised from stdout capture when the output budget is exhausted."""


class OutputCapture:
    def __init__(self, limit: int):
        self.limit = limit
        self.total = 0
        self.buf: list[str] = []
        self.all: list[str] = []

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            s = str(s)
        self.total += len(s)
        if self.total > self.limit:
            keep = max(0, len(s) - (self.total - self.limit))
            if keep:
                self.buf.append(s[:keep])
                self.all.append(s[:keep])
            raise OutputLimit(f"Output limit of {self.limit} characters exceeded")
        self.buf.append(s)
        self.all.append(s)
        return len(s)

    def flush(self) -> None:
        pass

    def take(self) -> str:
        out = "".join(self.buf)
        self.buf = []
        return out

    def text(self) -> str:
        return "".join(self.all)


class Pending:
    __slots__ = ("ev", "frame", "node", "kind", "loop", "line", "is_header_loop")

    def __init__(self, ev: dict, frame, node, kind: str, loop: Optional[A.LoopInfo], line: int):
        self.ev, self.frame, self.node, self.kind, self.loop, self.line = ev, frame, node, kind, loop, line


class Tracer:
    def __init__(self, idx: A.Index, emit: Callable[[dict], None], out: OutputCapture, max_events: int,
                 on_current: Optional[Callable[[int], None]] = None):
        self.idx = idx
        self.emit = emit
        self.on_current = on_current or (lambda line: None)
        self.out = out
        self.max_events = max_events
        self.count = 0
        self.pending: Optional[Pending] = None
        self.loop_counters: dict = {}     # (frame, loop.line) -> iteration
        self.loop_totals: dict = {}       # (frame, loop.line) -> total or None
        self.seen_exc: dict = {}          # id(exc) -> seq id
        self._keepalive: list = []
        self.exc_events: dict = {}        # seq id -> event_index where first raised
        self.unwinding: set = set()
        self.truncated = False

    # ------------------------------------------------------------------ hooks
    def global_trace(self, frame, event, arg):
        code = frame.f_code
        if code.co_filename != A.USER_FILE or code.co_name in ("<lambda>", "<genexpr>", "<listcomp>",
                                                               "<dictcomp>", "<setcomp>"):
            return None
        if event == "call":
            self._on_call(frame)
        return self.local_trace

    def local_trace(self, frame, event, arg):
        if event == "line":
            self._on_line(frame)
        elif event == "return":
            self._on_return(frame, arg)
        elif event == "exception":
            self._on_exception(frame, arg)
        return self.local_trace

    # ------------------------------------------------------------------ event helpers
    def _scope(self, frame) -> dict:
        return S.snapshot_scope(frame.f_locals)

    def _globals_of(self, frame) -> dict:
        return frame.f_globals

    def _stack(self, frame, line: int) -> list[dict]:
        frames = []
        f = frame
        while f is not None and f.f_code.co_filename == A.USER_FILE:
            if f.f_code.co_name not in ("<lambda>", "<genexpr>", "<listcomp>", "<dictcomp>", "<setcomp>"):
                frames.append(f)
            f = f.f_back
        frames.reverse()
        entries = []
        for i, f in enumerate(frames):
            is_cur = (i == len(frames) - 1)
            entries.append({
                "function": "<module>" if f.f_code.co_name == "<module>" else f.f_code.co_name,
                "line": line if is_cur else f.f_lineno,
                "is_current": is_cur,
                "variables": None if is_cur else self._scope(f),
            })
        if len(entries) > MAX_STACK:
            cut = len(entries) - (MAX_STACK - 5)
            entries = entries[:5] + [{"function": f"... {cut - 5} more frames ...", "line": 0, "is_current": False,
                                      "variables": {}, "omitted": cut - 5}] + entries[cut:]
        return entries

    def _check_budget(self):
        if self.count >= self.max_events:
            self.truncated = True
            raise TraceLimit(f"Stopped after {self.max_events} steps (possible infinite loop?)")

    def _loop_context(self, frame, line: int) -> Optional[dict]:
        scope = A.scope_key_for_frame(frame.f_code)
        loops = A.enclosing_loops(self.idx, scope, line)
        # forget counters for loops of this frame that we have left
        live = {(frame, lp.line) for lp in loops}
        for key in [k for k in self.loop_counters if k[0] is frame and k not in live]:
            self.loop_counters.pop(key, None)
            self.loop_totals.pop(key, None)
        if not loops:
            return None
        node = self.idx.stmt_by_line.get(line)
        out = []
        for lp in loops:
            key = (frame, lp.line)
            is_header = node is lp.node
            if is_header:
                self.loop_counters[key] = self.loop_counters.get(key, 0) + 1
                if key not in self.loop_totals:
                    total = None
                    if lp.kind == "for" and lp.iter_node is not None:
                        ok, it = A.try_eval(lp.iter_node, frame.f_locals, frame.f_globals)
                        if ok and hasattr(it, "__len__"):
                            try:
                                total = len(it)
                            except Exception:
                                total = None
                    self.loop_totals[key] = total
            out.append({"line": lp.line, "kind": lp.kind, "iteration": self.loop_counters.get(key, 0),
                        "total": self.loop_totals.get(key), "variable": lp.variable,
                        "is_header": is_header, "exiting": None,
                        "header": self.idx.source_line(lp.line).strip()})
        return {"loops": out, "depth": len(out)}

    def _new_event(self, frame, etype: str, line: int, node, extra_ctx: Optional[dict] = None,
                   with_calc: bool = True, loop_ctx: Optional[dict] = None) -> dict:
        self._check_budget()
        scope = frame.f_locals
        ctx = A.describe_statement(self.idx, node, scope, frame.f_globals, with_calc)
        ctx["enclosing"] = A.enclosing_blocks(self.idx, node)
        if extra_ctx:
            ctx.update(extra_ctx)
        ev = {
            "event_index": self.count,
            "line_number": line,
            "event_type": etype,
            "source_line": self.idx.source_line(line),
            "scope": "<module>" if frame.f_code.co_name == "<module>" else frame.f_code.co_name,
            "variables_before": self._scope(frame),
            "variables_after": None,
            "stdout_delta": "",
            "explanation_context": ctx,
            "call_stack": self._stack(frame, line),
            "loop_context": loop_ctx,
            "status": "ok",
            "error": None,
        }
        self.count += 1
        return ev

    # ------------------------------------------------------------------ finalise
    def _finalize(self, nxt_kind: str, nxt_frame=None, nxt_line: Optional[int] = None):
        p = self.pending
        if p is None:
            return
        self.pending = None
        ev = p.ev
        after = self._scope(p.frame)
        ev["variables_after"] = after
        ev["stdout_delta"] = self.out.take()
        ctx = ev["explanation_context"]
        ctx["changes"] = S.diff_scopes(ev["variables_before"], after)
        ev["call_stack"][-1]["variables"] = after
        # branch / loop-exit inference from where control goes next
        same_frame_line = nxt_line if (nxt_kind == "line" and nxt_frame is p.frame) else None
        if p.kind in ("if", "elif") and isinstance(p.node, ast.If):
            body_start, body_end = p.node.body[0].lineno, (p.node.body[-1].end_lineno or p.node.body[-1].lineno)
            if same_frame_line is not None and same_frame_line != p.line:
                ctx["branch_taken"] = body_start <= same_frame_line <= body_end
            elif nxt_kind == "return":
                ctx["branch_taken"] = False
            else:
                truth = (ctx.get("condition") or {}).get("truth")
                ctx["branch_taken"] = truth if nxt_kind != "call" else None
        if p.loop is not None and ev["loop_context"]:
            lp = p.loop
            exiting = None
            if same_frame_line is not None and same_frame_line != p.line:
                exiting = not (lp.body_start <= same_frame_line <= lp.body_end)
            elif nxt_kind == "return":
                exiting = True
            if p.kind in ("for", "while"):
                for entry in ev["loop_context"]["loops"]:
                    if entry["line"] == lp.line and entry["is_header"]:
                        entry["exiting"] = exiting
                if p.kind == "while":
                    truth = (ctx.get("condition") or {}).get("truth")
                    ctx["branch_taken"] = (not exiting) if exiting is not None else truth
        self.emit(ev)

    # ------------------------------------------------------------------ trace events
    def _on_line(self, frame):
        self.unwinding.discard(frame)
        line = frame.f_lineno
        node = self.idx.stmt_by_line.get(line)
        src = self.idx.source_line(line)
        kind = A.event_type_for(self.idx, node, src)
        p = self.pending
        # one-line comprehensions / same-line jumps are collapsed into the current step
        if p is not None and p.frame is frame and p.line == line and kind not in ("for", "while"):
            return
        self._finalize("line", frame, line)
        loop_ctx = self._loop_context(frame, line)
        loop = None
        if kind in ("for", "while"):
            loop = next((lp for lp in self.idx.loops if lp.node is node), None)
        ev = self._new_event(frame, kind, line, node, loop_ctx=loop_ctx)
        self.pending = Pending(ev, frame, node, kind, loop, line)
        self.on_current(line)

    def _on_call(self, frame):
        # first: close the caller's pending line (it is "calling a function")
        parent_ev = self.pending
        if parent_ev is not None:
            parent_ev.ev["explanation_context"]["calls_function"] = frame.f_code.co_name
        self._finalize("call", frame, None)
        code = frame.f_code
        if code.co_name == "<module>":
            return
        def_node = self.idx.funcs_by_firstline.get(code.co_firstlineno)
        def_line = def_node.lineno if def_node is not None else code.co_firstlineno
        args = {k: v for k, v in frame.f_locals.items()}
        ctx = {"function": {"name": code.co_name, "params": list(code.co_varnames[: code.co_argcount])},
               "args": [{"name": k, "value": S.describe(v)} for k, v in args.items()],
               "caller_line": frame.f_back.f_lineno if frame.f_back is not None else None,
               "enclosing": []}
        ev = self._new_event(frame, "call", def_line, None, extra_ctx=ctx)
        # call events are complete immediately (nothing executes on this step)
        ev["variables_before"] = {}
        after = self._scope(frame)
        ev["variables_after"] = after
        ev["call_stack"][-1]["variables"] = after
        ev["explanation_context"]["changes"] = S.diff_scopes({}, after)
        ev["stdout_delta"] = self.out.take()
        self.emit(ev)

    def _on_return(self, frame, value):
        code = frame.f_code
        p = self.pending
        unwinding = frame in self.unwinding
        self.unwinding.discard(frame)
        for key in [k for k in self.loop_counters if k[0] is frame]:
            self.loop_counters.pop(key, None)
            self.loop_totals.pop(key, None)
        if code.co_name == "<module>":
            self._finalize("return", frame, None)
            return
        ret_desc = S.describe(value)
        if p is not None and p.frame is frame and p.kind == "return" and not unwinding:
            p.ev["explanation_context"]["return_value"] = ret_desc
            self._finalize("return", frame, None)
        else:
            self._finalize("return", frame, None)
            ev = self._new_event(frame, "return", frame.f_lineno, None, extra_ctx={
                "return_value": None if unwinding else ret_desc, "implicit": not unwinding,
                "unwinding": unwinding, "function": {"name": code.co_name}})
            after = self._scope(frame)
            ev["variables_after"] = after
            ev["call_stack"][-1]["variables"] = after
            ev["explanation_context"]["changes"] = []
            ev["stdout_delta"] = self.out.take()
            self.emit(ev)
        parent = frame.f_back
        if parent is not None and parent.f_code.co_filename == A.USER_FILE and not unwinding \
                and parent.f_code.co_name not in ("<lambda>", "<genexpr>"):
            line = parent.f_lineno
            node = self.idx.stmt_by_line.get(line)
            kind = "resume"
            ev = self._new_event(parent, kind, line, node, with_calc=False,
                                 extra_ctx={"returned_from": code.co_name, "return_value": ret_desc,
                                            "resumed_statement_kind": A.event_type_for(self.idx, node, self.idx.source_line(line))},
                                 loop_ctx=self._loop_context_noinc(parent, line))
            self.pending = Pending(ev, parent, node, A.event_type_for(self.idx, node, self.idx.source_line(line)), None, line)
            # keep "if/while" branch inference working on the resumed half
            if node is not None and isinstance(node, (ast.If, ast.While, ast.For)):
                self.pending.loop = next((lp for lp in self.idx.loops if lp.node is node), None)

    def _loop_context_noinc(self, frame, line: int) -> Optional[dict]:
        scope = A.scope_key_for_frame(frame.f_code)
        loops = A.enclosing_loops(self.idx, scope, line)
        if not loops:
            return None
        out = []
        for lp in loops:
            key = (frame, lp.line)
            out.append({"line": lp.line, "kind": lp.kind, "iteration": self.loop_counters.get(key, 0),
                        "total": self.loop_totals.get(key), "variable": lp.variable,
                        "is_header": False, "exiting": None, "header": self.idx.source_line(lp.line).strip()})
        return {"loops": out, "depth": len(out)}

    def _on_exception(self, frame, arg):
        exc_type, exc, _tb = arg
        self.unwinding.add(frame)
        key = id(exc)
        if key in self.seen_exc:
            return
        seq = len(self.seen_exc) + 1
        self.seen_exc[key] = seq
        self._keepalive.append(exc)
        if len(self._keepalive) > 500:
            self._keepalive.pop(0)
        p = self.pending
        info = {"id": seq, "type": exc_type.__name__, "message": _exc_message(exc)}
        if p is not None and p.frame is frame:
            p.ev["explanation_context"]["exception"] = info
            p.ev["error"] = {"type": info["type"], "message": info["message"]}
            self.exc_events[seq] = p.ev["event_index"]
        elif p is not None:
            # raised by a frame whose own line was already closed (should be rare)
            p.ev["explanation_context"]["exception"] = info
            self.exc_events[seq] = p.ev["event_index"]


def _exc_message(exc: BaseException) -> str:
    try:
        return str(exc)
    except Exception:
        return "<unprintable exception>"
