"""Flowchart generation from the Python AST (no execution).

Returns ``{"charts": [{"name", "nodes", "edges"}]}`` - one chart for the main program plus one per function.
node: {id, kind: start|end|process|io|decision|loop|call|return, label, line}
edge: {from, to, label, back}   (back=True for loop-return edges, used by the layout)
Node ``line`` lets the UI highlight the box that is executing right now.
"""
from __future__ import annotations

import ast


class _Chart:
    def __init__(self, name: str):
        self.name = name
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.loops: list[dict] = []        # stack of {"head": id, "breaks": [exits]}

    def node(self, kind: str, label: str, line: int | None) -> str:
        nid = f"n{len(self.nodes)}"
        self.nodes.append({"id": nid, "kind": kind, "label": label[:46] + ("…" if len(label) > 46 else ""), "line": line})
        return nid

    def link(self, entries, to: str):
        for src, lab in entries:
            self.edges.append({"from": src, "to": to, "label": lab, "back": False})

    def block(self, stmts, entries):
        for s in stmts:
            if not entries:
                break                       # unreachable (after return/break/raise)
            entries = self.stmt(s, entries)
        return entries

    def seg(self, node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return "…"

    def stmt(self, s: ast.stmt, entries):
        line = getattr(s, "lineno", None)
        if isinstance(s, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            n = self.node("process", self.seg(s), line); self.link(entries, n); return [(n, "")]
        if isinstance(s, ast.Expr):
            is_print = isinstance(s.value, ast.Call) and isinstance(s.value.func, ast.Name) and s.value.func.id == "print"
            kind = "io" if is_print else ("call" if isinstance(s.value, ast.Call) else "process")
            n = self.node(kind, self.seg(s.value), line); self.link(entries, n); return [(n, "")]
        if isinstance(s, ast.FunctionDef):
            n = self.node("call", f"define {s.name}({', '.join(a.arg for a in s.args.args)})", line); self.link(entries, n); return [(n, "")]
        if isinstance(s, ast.If):
            d = self.node("decision", self.seg(s.test) + " ?", line); self.link(entries, d)
            yes = self.block(s.body, [(d, "Yes")])
            no = self.block(s.orelse, [(d, "No")]) if s.orelse else [(d, "No")]
            return yes + no
        if isinstance(s, (ast.While, ast.For)):
            label = (self.seg(s.test) + " ?") if isinstance(s, ast.While) else f"for {self.seg(s.target)} in {self.seg(s.iter)}"
            h = self.node("loop" if isinstance(s, ast.For) else "decision", label, line); self.link(entries, h)
            self.loops.append({"head": h, "breaks": []})
            body_exits = self.block(s.body, [(h, "Yes" if isinstance(s, ast.While) else "next item")])
            for src, lab in body_exits:
                self.edges.append({"from": src, "to": h, "label": lab, "back": True})
            ctx = self.loops.pop()
            done = [(h, "No" if isinstance(s, ast.While) else "done")]
            if s.orelse:
                done = self.block(s.orelse, done)
            return done + ctx["breaks"]
        if isinstance(s, ast.Break):
            n = self.node("process", "break", line); self.link(entries, n)
            if self.loops:
                self.loops[-1]["breaks"].append((n, ""))
            return []
        if isinstance(s, ast.Continue):
            n = self.node("process", "continue", line); self.link(entries, n)
            if self.loops:
                self.edges.append({"from": n, "to": self.loops[-1]["head"], "label": "", "back": True})
            return []
        if isinstance(s, ast.Return):
            n = self.node("return", "return " + (self.seg(s.value) if s.value else ""), line); self.link(entries, n)
            self.returns.append((n, "")); return []
        if isinstance(s, ast.Raise):
            n = self.node("process", self.seg(s), line); self.link(entries, n); self.returns.append((n, "raise")); return []
        if isinstance(s, ast.Try):
            t = self.node("process", "try", line); self.link(entries, t)
            exits = self.block(s.body, [(t, "")])
            for h in s.handlers:
                exits += self.block(h.body, [(t, "except " + (self.seg(h.type) if h.type else ""))])
            if s.orelse:
                exits = self.block(s.orelse, exits)
            if s.finalbody:
                exits = self.block(s.finalbody, exits)
            return exits
        if isinstance(s, ast.Pass):
            n = self.node("process", "pass", line); self.link(entries, n); return [(n, "")]
        n = self.node("process", self.seg(s).split("\n")[0], line); self.link(entries, n); return [(n, "")]

    returns: list


def _build(name: str, body: list[ast.stmt], title: str) -> _Chart:
    c = _Chart(name)
    c.returns = []
    start = c.node("start", title, None)
    exits = c.block(body, [(start, "")])
    end = c.node("end", "end" if name == "main" else "return", None)
    c.link(exits + c.returns, end)
    return c


def build(source: str) -> dict:
    tree = ast.parse(source)
    charts = [_build("main", tree.body, "start")]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            charts.append(_build(node.name, node.body, f"{node.name}({', '.join(a.arg for a in node.args.args)})"))
    return {"charts": [{"name": c.name, "nodes": c.nodes, "edges": c.edges} for c in charts]}
