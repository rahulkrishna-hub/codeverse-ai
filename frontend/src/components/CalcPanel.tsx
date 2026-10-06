import { forwardRef } from "react";
import type { Calc, TraceEvent } from "../types";

export const OP_LABEL: Record<string, string> = {
  assign: "Assign a value", print: "Print to console", if: "Check a condition", elif: "Check a condition", while: "Check loop condition",
  for: "Loop: take the next item", call: "Function call", return: "Return a value", resume: "Back in the caller", function_def: "Define a function",
  expr: "Evaluate an expression", augassign: "Update a variable", pass: "Do nothing", break: "Break out of the loop", continue: "Skip to next iteration",
  raise: "Raise an error", error: "Error",
};

export function calcOf(e: TraceEvent | null): (Calc & { kind: "calc" | "condition" }) | null {
  if (!e) return null;
  const c = e.explanation_context;
  if (c.condition) return { ...c.condition, kind: "condition" };
  const k = c.calculation;
  if (k && (k.operator || k.operands.length > 0)) return { ...k, kind: "calc" };
  return null;
}

export const CalcPanel = forwardRef<HTMLDivElement, { event: TraceEvent | null; idx: number }>(function CalcPanel({ event, idx }, ref) {
  const c = calcOf(event);
  if (!event) return null;
  const ctx = event.explanation_context;
  return (
    <div ref={ref} className="calc" data-testid="calc" key={idx}>
      <div className="calc-title">{OP_LABEL[event.event_type] ?? event.event_type}<span className="calc-line">line {event.line_number}</span></div>
      <code className="calc-src">{event.source_line.trim()}</code>
      {c && (
        <div className="calc-row" data-testid="calc-row">
          <span className="calc-expr" style={{ animationDelay: "0ms" }}>{c.expression}</span>
          <span className="calc-eqs">⇒</span>
          {c.operands.map((o, i) => (
            <span key={i} className="calc-pair">
              {i > 0 && c.operator && <span className="chip op" style={{ animationDelay: `${i * 260}ms` }}>{c.operator}</span>}
              <span className="chip operand" style={{ animationDelay: `${i * 260 + 120}ms` }} title={`${o.source} (${o.type})`}>{o.value}</span>
            </span>
          ))}
          <span className="chip eq" style={{ animationDelay: `${c.operands.length * 260 + 140}ms` }}>=</span>
          <span className={"chip result" + (c.kind === "condition" ? (c.truth ? " yes" : " no") : "")} style={{ animationDelay: `${c.operands.length * 260 + 320}ms` }} data-testid="calc-result">{c.result}</span>
        </div>
      )}
      {ctx.print && <div className="calc-row">{ctx.print.args.map((a, i) => <span key={i} className="chip operand" style={{ animationDelay: `${i * 200}ms` }}>{a.value}</span>)}<span className="chip eq" style={{ animationDelay: `${ctx.print.args.length * 200}ms` }}>→ console</span></div>}
      {ctx.args && ctx.args.length > 0 && <div className="calc-row">{ctx.args.map((a, i) => <span key={i} className="chip operand" style={{ animationDelay: `${i * 200}ms` }}>{a.name} = {a.value.repr}</span>)}</div>}
      {ctx.return_value && !c && <div className="calc-row"><span className="chip result">{ctx.return_value.repr}</span></div>}
    </div>
  );
});
