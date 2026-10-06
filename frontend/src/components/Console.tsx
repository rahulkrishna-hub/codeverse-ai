import { useEffect, useRef } from "react";
import type { ExecError, TraceEvent } from "../types";
import { flyChip } from "../fly";

type Props = {
  text: string; lastDelta: string; idx: number; event: TraceEvent | null; error: ExecError | null; atEnd: boolean;
  fly: { n: number; dir: "fwd" | "jump" }; speed: number; onClear: () => void; stale: boolean; sandboxWarning?: string;
};

export function Console({ text, lastDelta, idx, event, error, atEnd, fly, speed, onClear, stale, sandboxWarning }: Props) {
  const box = useRef<HTMLPreElement>(null);
  const tail = useRef<HTMLSpanElement>(null);
  const lastFly = useRef(0);
  useEffect(() => { box.current?.scrollTo({ top: 1e9, behavior: "smooth" }); }, [text]);
  // The value "travels" from its variable card (or the executing line) into the console.
  useEffect(() => {
    if (fly.n === lastFly.current) return;
    lastFly.current = fly.n;
    if (fly.dir !== "fwd" || !lastDelta || !event) return;
    const args = event.explanation_context.print?.args ?? [];
    const named = args.map((a) => document.querySelector<HTMLElement>(`[data-card-name="${CSS.escape(a.source)}"]`)).find(Boolean);
    const from = named ?? document.querySelector<HTMLElement>("[data-fly-src=line]");
    const to = tail.current ?? box.current;
    if (from && to) flyChip(from.getBoundingClientRect(), to.getBoundingClientRect(), lastDelta.trim().slice(0, 24), speed);
  }, [fly, lastDelta, event, speed]);

  const failed = event?.status === "failed" ? event.error : null;
  const shownError = failed ?? (atEnd && error && error.line != null && !event ? error : null);
  const body = text.endsWith("\n") ? text.slice(0, -1) : text;
  const fresh = lastDelta ? lastDelta.replace(/\n$/, "") : "";
  const head = fresh && body.endsWith(fresh) ? body.slice(0, body.length - fresh.length) : body;
  return (
    <div className="console" data-testid="console">
      <div className="console-bar"><span>Console output</span>
        {stale && <span className="pill warn">code changed — Run again</span>}
        <button className="mini" onClick={onClear} title="Clear output">Clear</button></div>
      <pre ref={box} className="console-body" data-testid="console-text">
        {head}
        {fresh && head.length < body.length && <span key={idx} className="fresh" ref={tail}>{fresh}</span>}
        {!text && !shownError && <span className="muted">Nothing printed yet. print() output appears here.</span>}
        {(text || shownError) && <span className="caret" ref={fresh ? undefined : tail}>▍</span>}
        {shownError && <div className="console-err" data-testid="console-error"><b>{shownError.type}:</b> {shownError.message}{error?.traceback ? "\n" + error.traceback.map((t) => `  line ${t.line}, in ${t.function}: ${t.source}`).join("\n") : ""}</div>}
      </pre>
      {sandboxWarning && <div className="console-foot">⚠ {sandboxWarning}</div>}
    </div>
  );
}
