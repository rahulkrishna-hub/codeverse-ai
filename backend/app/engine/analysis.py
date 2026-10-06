"""Static (AST) analysis for the CodeVerse Python tracer.

STDLIB ONLY and no relative imports: this module is loaded both by the API
process (``app.engine.analysis``) and by the isolated worker process, which
imports it as a flat module (``import analysis``).

Responsibilities
* syntax / supported-subset checks (before anything is executed)
* mapping source lines -> statements, classification into event types
* loop / enclosing-block metadata
* ``pure_eval``: side-effect-free evaluation of simple sub-expressions so the
  frontend can animate ``10 + 20 = 30`` *before* the statement runs
"""
from __future__ import annotations

import ast
import builtins
import math
from dataclasses import dataclass, field
from typing import Any, Optional

USER_FILE = "<user_code>"

SUPPORTED_FEATURES = [
    "assignments (incl. tuple unpacking, augmented, subscript targets)",
    "arithmetic, comparison and boolean expressions, f-strings",
    "print() with captured console output",
    "if / elif / else",
    "for loops (with break / continue / else) and while loops",
    "functions: def, parameters, return, recursion, lambda",
    "lists, tuples, dicts, sets and nested combinations",
    "list / dict / set comprehensions (executed as ONE step)",
    "try / except / finally / raise, assert, del, pass",
    "import of: math, random, string, itertools, collections, heapq, bisect",
]

UNSUPPORTED_NODES: dict[type, str] = {
    ast.ClassDef: "Classes (class ...) are not supported in this first release.",
    ast.With: "'with' blocks are not supported in this first release.",
    ast.AsyncFunctionDef: "async functions are not supported.",
    ast.AsyncFor: "async for is not supported.",
    ast.AsyncWith: "async with is not supported.",
    ast.Await: "await is not supported.",
    ast.Yield: "Generators (yield) are not supported in this first release.",
    ast.YieldFrom: "Generators (yield from) are not supported in this first release.",
    ast.Match: "match statements are not supported in this first release.",
}
if hasattr(ast, "TryStar"):
    UNSUPPORTED_NODES[ast.TryStar] = "except* is not supported."

ALLOWED_MODULES = {"math", "random", "string", "itertools", "collections", "heapq", "bisect"}

# builtins that pure_eval may call (no side effects on their own)
PURE_BUILTINS = {"len", "range", "abs", "min", "max", "sum", "int", "float", "str", "bool",
                 "round", "sorted", "list", "tuple", "set"}


@dataclass
class Issue:
    kind: str            # "syntax_error" | "unsupported"
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    hint: Optional[str] = None

    def as_dict(self) -> dict:
        return {"type": "SyntaxError" if self.kind == "syntax_error" else "UnsupportedSyntax",
                "kind": self.kind, "message": self.message, "line": self.line,
                "column": self.column, "hint": self.hint}


def parse_source(source: str) -> tuple[Optional[ast.Module], Optional[Issue]]:
    """Parse without executing. Returns (tree, None) or (None, Issue)."""
    try:
        tree = ast.parse(source, filename=USER_FILE, mode="exec")
    except SyntaxError as e:
        return None, Issue("syntax_error", e.msg or "invalid syntax", e.lineno, e.offset,
                           _syntax_hint(e))
    except (ValueError, RecursionError, MemoryError) as e:  # null bytes, absurd nesting
        return None, Issue("syntax_error", f"Could not parse the program ({type(e).__name__}).")
    return tree, None


def _syntax_hint(e: SyntaxError) -> Optional[str]:
    msg = (e.msg or "").lower()
    if "expected ':'" in msg:
        return "A line that starts a block (if, for, while, def) must end with a colon ':'."
    if "indent" in msg:
        return "Check the spaces at the start of the line - lines inside a block must line up."
    if "was never closed" in msg or "unterminated" in msg:
        return "Something was opened ( [ { or a quote but never closed."
    if "invalid syntax" in msg:
        return "Python could not understand this line. Look for a missing symbol or a typo."
    return None


def check_supported(tree: ast.Module) -> Optional[Issue]:
    """Reject syntax outside the documented subset.

    The dunder checks are defence in depth ONLY. The real security boundary is the
    process sandbox (see runner.py); AST filtering is not relied on for safety.
    """
    for node in ast.walk(tree):
        msg = UNSUPPORTED_NODES.get(type(node))
        if msg:
            return Issue("unsupported", msg, getattr(node, "lineno", None),
                         getattr(node, "col_offset", None) and node.col_offset + 1)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_MODULES:
                    return Issue("unsupported", f"Importing '{alias.name}' is not allowed. "
                                 f"Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}.", node.lineno)
        if isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_MODULES:
                return Issue("unsupported", f"Importing from '{node.module}' is not allowed. "
                             f"Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}.", node.lineno)
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return Issue("unsupported", f"Access to private/special attribute '{node.attr}' is not allowed.",
                         node.lineno, node.col_offset + 1)
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return Issue("unsupported", f"The name '{node.id}' is not allowed.", node.lineno, node.col_offset + 1)
    return None


# --------------------------------------------------------------------------- index

@dataclass
class LoopInfo:
    node: ast.AST
    kind: str                 # "for" | "while"
    line: int
    end_line: int
    scope: tuple              # ("module",) or ("fn", co_firstlineno)
    variable: Optional[str]
    iter_node: Optional[ast.AST]
    body_start: int
    body_end: int


@dataclass
class Index:
    source: str
    lines: list
    tree: ast.Module
    stmt_by_line: dict = field(default_factory=dict)       # line -> ast.stmt (innermost)
    loops: list = field(default_factory=list)
    parents: dict = field(default_factory=dict)           # id(node) -> parent node
    funcs_by_firstline: dict = field(default_factory=dict)  # co_firstlineno -> FunctionDef/Lambda

    def source_line(self, line: int) -> str:
        return self.lines[line - 1] if 1 <= line <= len(self.lines) else ""


def _stmt_span(node: ast.stmt) -> tuple[int, int]:
    start = node.lineno
    for d in getattr(node, "decorator_list", []) or []:
        start = min(start, d.lineno)
    return start, getattr(node, "end_lineno", node.lineno) or node.lineno


def build_index(source: str, tree: ast.Module) -> Index:
    idx = Index(source=source, lines=source.split("\n"), tree=tree)
    best: dict[int, tuple[int, ast.stmt]] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            idx.parents[id(child)] = parent
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            s, e = _stmt_span(node)
            span = e - s
            for ln in range(s, e + 1):
                cur = best.get(ln)
                if cur is None or span < cur[0]:
                    best[ln] = (span, node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            idx.funcs_by_firstline[_stmt_span(node)[0]] = node
        if isinstance(node, ast.Lambda):
            idx.funcs_by_firstline.setdefault(node.lineno, node)
    idx.stmt_by_line = {ln: n for ln, (_, n) in best.items()}
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            idx.loops.append(LoopInfo(
                node=node, kind="for" if isinstance(node, ast.For) else "while",
                line=node.lineno, end_line=node.end_lineno or node.lineno,
                scope=_scope_of(idx, node),
                variable=_target_names(node.target)[0] if isinstance(node, ast.For) and _target_names(node.target) else None,
                iter_node=node.iter if isinstance(node, ast.For) else None,
                body_start=node.body[0].lineno,
                body_end=node.body[-1].end_lineno or node.body[-1].lineno))
    return idx


def _scope_of(idx: Index, node: ast.AST) -> tuple:
    cur = idx.parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ("fn", _stmt_span(cur)[0])
        cur = idx.parents.get(id(cur))
    return ("module",)


def scope_key_for_frame(code) -> tuple:
    return ("module",) if code.co_name == "<module>" else ("fn", code.co_firstlineno)


def enclosing_loops(idx: Index, scope: tuple, line: int) -> list[LoopInfo]:
    out = [lp for lp in idx.loops if lp.scope == scope and lp.line <= line <= lp.end_line]
    out.sort(key=lambda lp: (lp.line, -lp.end_line))
    return out


# --------------------------------------------------------------------------- classification

def event_type_for(idx: Index, node: Optional[ast.stmt], source_line: str) -> str:
    if node is None:
        return "statement"
    if isinstance(node, ast.Assign):
        return "assign"
    if isinstance(node, ast.AugAssign):
        return "aug_assign"
    if isinstance(node, ast.AnnAssign):
        return "assign"
    if isinstance(node, ast.Expr):
        v = node.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "print":
            return "print"
        return "expr"
    if isinstance(node, ast.If):
        return "elif" if source_line.lstrip().startswith("elif") else "if"
    if isinstance(node, ast.For):
        return "for"
    if isinstance(node, ast.While):
        return "while"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "function_def"
    mapping = {ast.Return: "return", ast.Break: "break", ast.Continue: "continue", ast.Pass: "pass",
               ast.Import: "import", ast.ImportFrom: "import", ast.Assert: "assert",
               ast.Delete: "delete", ast.Raise: "raise", ast.Try: "try",
               ast.Global: "global", ast.Nonlocal: "global"}
    return mapping.get(type(node), "statement")


def _target_names(t: ast.AST) -> list[str]:
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        out: list[str] = []
        for e in t.elts:
            out.extend(_target_names(e))
        return out
    if isinstance(t, ast.Starred):
        return _target_names(t.value)
    if isinstance(t, (ast.Subscript, ast.Attribute)):
        try:
            return [ast.unparse(t)]
        except Exception:
            return []
    return []


def enclosing_blocks(idx: Index, node: Optional[ast.stmt]) -> list[dict]:
    """Static answer to 'why does this line run?': the blocks it sits inside."""
    out: list[dict] = []
    if node is None:
        return out
    child = node
    parent = idx.parents.get(id(child))
    while parent is not None and not isinstance(parent, ast.Module):
        header = idx.source_line(getattr(parent, "lineno", 0)).strip()
        if isinstance(parent, ast.If):
            where = "if-body" if child in parent.body else "else-body"
            is_elif_child = (where == "else-body" and isinstance(child, ast.If)
                             and idx.source_line(child.lineno).lstrip().startswith("elif"))
            if not is_elif_child:      # an elif is part of the same chain, not a separate nesting level
                out.append({"kind": where, "line": parent.lineno, "header": header})
        elif isinstance(parent, (ast.For, ast.While)):
            where = ("for" if isinstance(parent, ast.For) else "while")
            part = "body" if child in parent.body else "else"
            out.append({"kind": f"{where}-{part}", "line": parent.lineno, "header": header})
        elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({"kind": "function", "line": parent.lineno, "header": header, "name": parent.name})
        elif isinstance(parent, ast.Try):
            part = "try-body" if child in parent.body else "handler/finally"
            out.append({"kind": part, "line": parent.lineno, "header": header})
        child, parent = parent, idx.parents.get(id(parent))
    out.reverse()
    return out


# --------------------------------------------------------------------------- pure evaluation

class NotPure(Exception):
    pass


_BIN = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_BIN_SYM = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//",
            ast.Mod: "%", ast.Pow: "**"}
_CMP = {
    ast.Eq: (lambda a, b: a == b, "=="), ast.NotEq: (lambda a, b: a != b, "!="),
    ast.Lt: (lambda a, b: a < b, "<"), ast.LtE: (lambda a, b: a <= b, "<="),
    ast.Gt: (lambda a, b: a > b, ">"), ast.GtE: (lambda a, b: a >= b, ">="),
    ast.In: (lambda a, b: a in b, "in"), ast.NotIn: (lambda a, b: a not in b, "not in"),
    ast.Is: (lambda a, b: a is b, "is"), ast.IsNot: (lambda a, b: a is not b, "is not"),
}
_SEQ = (str, bytes, list, tuple)
_MAX_STEPS = 400


def pure_eval(node: ast.AST, scope: dict, glob: dict, _budget: Optional[list] = None) -> Any:
    """Evaluate a side-effect-free expression against REAL runtime values.

    Raises NotPure for anything it cannot guarantee is side-effect free
    (user function calls, attribute access, comprehensions, huge results ...).
    """
    if _budget is None:
        _budget = [_MAX_STEPS]
    _budget[0] -= 1
    if _budget[0] < 0:
        raise NotPure("too complex")
    ev = lambda n: pure_eval(n, scope, glob, _budget)  # noqa: E731

    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in scope:
            return scope[node.id]
        if node.id in glob:
            return glob[node.id]
        raise NotPure(node.id)
    try:
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in _BIN:
                raise NotPure("op")
            a, b = ev(node.left), ev(node.right)
            if op is ast.Mult and ((isinstance(a, _SEQ) and isinstance(b, int) and abs(b) > 10_000) or
                                   (isinstance(b, _SEQ) and isinstance(a, int) and abs(a) > 10_000)):
                raise NotPure("big repeat")
            if op is ast.Pow and isinstance(b, (int, float)) and (abs(b) > 1000 or (isinstance(a, int) and abs(a) > 10**6 and b > 50)):
                raise NotPure("big pow")
            return _BIN[op](a, b)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -v
            if isinstance(node.op, ast.UAdd):
                return +v
            if isinstance(node.op, ast.Not):
                return not v
            if isinstance(node.op, ast.Invert):
                return ~v
            raise NotPure("unary")
        if isinstance(node, ast.BoolOp):
            result: Any = None
            for i, v in enumerate(node.values):
                result = ev(v)
                if isinstance(node.op, ast.And) and not result:
                    return result
                if isinstance(node.op, ast.Or) and result:
                    return result
            return result
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                fn = _CMP.get(type(op))
                if fn is None:
                    raise NotPure("cmp")
                right = ev(comp)
                if not fn[0](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return ev(node.body) if ev(node.test) else ev(node.orelse)
        if isinstance(node, ast.Subscript):
            base = ev(node.value)
            sl = node.slice
            if isinstance(sl, ast.Slice):
                key: Any = slice(ev(sl.lower) if sl.lower else None, ev(sl.upper) if sl.upper else None,
                                 ev(sl.step) if sl.step else None)
            else:
                key = ev(sl)
            return base[key]
        if isinstance(node, ast.List):
            return [ev(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(ev(e) for e in node.elts)
        if isinstance(node, ast.Set):
            return {ev(e) for e in node.elts}
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                raise NotPure("dict unpack")
            return {ev(k): ev(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                elif isinstance(v, ast.FormattedValue):
                    val = ev(v.value)
                    if v.conversion == ord("r"):
                        val = repr(val)
                    elif v.conversion == ord("s"):
                        val = str(val)
                    elif v.conversion == ord("a"):
                        val = ascii(val)
                    spec = ""
                    if v.format_spec is not None:
                        spec = ev(v.format_spec)
                    parts.append(format(val, spec))
                else:
                    raise NotPure("fstring")
            return "".join(parts)
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in PURE_BUILTINS):
                raise NotPure("call")
            name = node.func.id
            if name in scope or name in glob:      # shadowed by user code
                raise NotPure("shadowed")
            if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                raise NotPure("star")
            args = [ev(a) for a in node.args]
            kwargs = {k.arg: ev(k.value) for k in node.keywords}
            for a in args:
                try:
                    if len(a) > 10_000:
                        raise NotPure("big arg")
                except TypeError:
                    pass
            if name == "range" and any(isinstance(a, int) and abs(a) > 10**15 for a in args):
                raise NotPure("range")
            return getattr(builtins, name)(*args, **kwargs)
    except NotPure:
        raise
    except Exception as e:  # any runtime error => not safely evaluable (the real run will report it)
        raise NotPure(type(e).__name__)
    raise NotPure(type(node).__name__)


def try_eval(node: Optional[ast.AST], scope: dict, glob: dict) -> tuple[bool, Any]:
    if node is None:
        return False, None
    try:
        return True, pure_eval(node, scope, glob)
    except NotPure:
        return False, None
    except RecursionError:
        return False, None


def short_repr(v: Any, limit: int = 80) -> str:
    try:
        r = repr(v)
    except Exception:
        r = "<unrepresentable>"
    return r if len(r) <= limit else r[: limit - 1] + "…"


def _operand(node: ast.AST, scope: dict, glob: dict) -> dict:
    ok, val = try_eval(node, scope, glob)
    try:
        src = ast.unparse(node)
    except Exception:
        src = "?"
    return {"source": src, "value": short_repr(val) if ok else None,
            "type": type(val).__name__ if ok else None}


def describe_calculation(expr: Optional[ast.AST], scope: dict, glob: dict) -> Optional[dict]:
    """Break the top operation of an expression into operands/operator/result."""
    if expr is None:
        return None
    try:
        src = ast.unparse(expr)
    except Exception:
        return None
    ok, val = try_eval(expr, scope, glob)
    result = short_repr(val) if ok else None
    operands: list[dict] = []
    operator: Optional[str] = None
    if isinstance(expr, ast.BinOp) and type(expr.op) in _BIN_SYM:
        operands = [_operand(expr.left, scope, glob), _operand(expr.right, scope, glob)]
        operator = _BIN_SYM[type(expr.op)]
    elif isinstance(expr, ast.Compare) and len(expr.ops) == 1 and type(expr.ops[0]) in _CMP:
        operands = [_operand(expr.left, scope, glob), _operand(expr.comparators[0], scope, glob)]
        operator = _CMP[type(expr.ops[0])][1]
    elif isinstance(expr, ast.BoolOp):
        operands = [_operand(v, scope, glob) for v in expr.values]
        operator = "and" if isinstance(expr.op, ast.And) else "or"
    elif isinstance(expr, ast.UnaryOp):
        operands = [_operand(expr.operand, scope, glob)]
        operator = {ast.USub: "-", ast.UAdd: "+", ast.Not: "not", ast.Invert: "~"}.get(type(expr.op))
    if not operands and not ok:
        return None
    return {"expression": src, "operands": operands, "operator": operator,
            "result": result, "result_type": type(val).__name__ if ok else None}


def describe_statement(idx: Index, node: Optional[ast.stmt], scope: dict, glob: dict,
                       with_calculation: bool = True) -> dict:
    """Facts about the statement about to run; consumed by the explainer + UI."""
    ctx: dict = {}
    if node is None:
        return ctx
    if isinstance(node, ast.Assign):
        names: list[str] = []
        for t in node.targets:
            names.extend(_target_names(t))
        ctx["targets"] = names
        ctx["value_source"] = ast.unparse(node.value)
        if with_calculation:
            ctx["calculation"] = describe_calculation(node.value, scope, glob)
    elif isinstance(node, ast.AnnAssign):
        ctx["targets"] = _target_names(node.target)
        if node.value is not None:
            ctx["value_source"] = ast.unparse(node.value)
            if with_calculation:
                ctx["calculation"] = describe_calculation(node.value, scope, glob)
    elif isinstance(node, ast.AugAssign):
        ctx["targets"] = _target_names(node.target)
        sym = _BIN_SYM.get(type(node.op), "?")
        ctx["operator"] = sym + "="
        ctx["value_source"] = ast.unparse(node.value)
        if with_calculation:
            cur_ok, cur = try_eval(ast.Name(id=node.target.id), scope, glob) if isinstance(node.target, ast.Name) else (False, None)
            val_ok, val = try_eval(node.value, scope, glob)
            res = None
            if cur_ok and val_ok and type(node.op) in _BIN:
                try:
                    res = short_repr(_BIN[type(node.op)](cur, val))
                except Exception:
                    res = None
            ctx["calculation"] = {
                "expression": f"{ast.unparse(node.target)} {sym} {ast.unparse(node.value)}",
                "operands": [{"source": ast.unparse(node.target), "value": short_repr(cur) if cur_ok else None,
                              "type": type(cur).__name__ if cur_ok else None},
                             _operand(node.value, scope, glob)],
                "operator": sym, "result": res, "result_type": None}
    elif isinstance(node, ast.Expr):
        v = node.value
        if isinstance(v, ast.Call):
            if isinstance(v.func, ast.Name) and v.func.id == "print":
                args = [_operand(a, scope, glob) for a in v.args]
                ctx["print"] = {"args": args}
            elif isinstance(v.func, ast.Attribute):
                ctx["method_call"] = {"object": ast.unparse(v.func.value), "method": v.func.attr,
                                      "args": [_operand(a, scope, glob) for a in v.args]}
            else:
                ctx["call"] = {"function": ast.unparse(v.func),
                               "args": [_operand(a, scope, glob) for a in v.args]}
    elif isinstance(node, (ast.If, ast.While)):
        ctx["condition"] = describe_calculation(node.test, scope, glob) or {"expression": ast.unparse(node.test)}
        ok, val = try_eval(node.test, scope, glob)
        ctx["condition"]["truth"] = bool(val) if ok else None
    elif isinstance(node, ast.For):
        ctx["iterable_source"] = ast.unparse(node.iter)
        ctx["targets"] = _target_names(node.target)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        ctx["function"] = {"name": node.name, "params": [a.arg for a in node.args.args]}
    elif isinstance(node, ast.Return):
        if node.value is not None:
            ctx["value_source"] = ast.unparse(node.value)
            if with_calculation:
                ctx["calculation"] = describe_calculation(node.value, scope, glob)
    elif isinstance(node, ast.Assert):
        ctx["condition"] = describe_calculation(node.test, scope, glob) or {"expression": ast.unparse(node.test)}
    elif isinstance(node, ast.Delete):
        ctx["targets"] = [n for t in node.targets for n in _target_names(t)]
    elif isinstance(node, ast.Raise):
        ctx["value_source"] = ast.unparse(node.exc) if node.exc is not None else None
    # user-function calls inside this statement (static): used for "why" explanations
    calls = []
    for sub in ast.walk(node) if not isinstance(node, (ast.If, ast.For, ast.While, ast.FunctionDef)) else ast.walk(_header_of(node)):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id != "print":
            calls.append(sub.func.id)
    if calls:
        ctx["calls"] = calls
    return ctx


def _header_of(node: ast.stmt) -> ast.AST:
    if isinstance(node, (ast.If, ast.While)):
        return node.test
    if isinstance(node, ast.For):
        return node.iter
    return ast.Pass()
