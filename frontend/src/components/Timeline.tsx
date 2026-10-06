import { useEffect, useRef } from "react";
import type { TraceEvent } from "../types";
import { stepStatus } from "../player";
import { LuCircle, LuCircleCheck, LuCircleX, LuCircleDot } from "react-icons/lu";

export function Timeline({ events, idx, onJump }: { events: TraceEvent[]; idx: number; onJump: (i: number) => void }) {
  const cur = useRef<HTMLButtonElement>(null);
  useEffect(() => { cur.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [idx]);
  if (!events.length) return <div className="empty-state small">The execution timeline appears after you run the code.</div>;
  return (
    <ol className="timeline" data-testid="timeline">
      {events.map((e, i) => {
        const st = stepStatus(events, i, idx);
        const lc = e.loop_context?.loops.at(-1);
        return (
          <li key={i}>
            <button ref={st === "current" || (st === "failed" && i === idx) ? cur : undefined} className={"tl " + st} data-status={st} onClick={() => onJump(i)} title="Jump to this step (time travel)">
              <span className="tl-ico">{st === "completed" ? <LuCircleCheck /> : st === "current" ? <LuCircleDot /> : st === "failed" ? <LuCircleX /> : <LuCircle />}</span>
              <span className="tl-n">{i + 1}</span>
              <span className="tl-line">L{e.line_number}</span>
              <span className={"tl-type ty-" + e.event_type}>{e.event_type}</span>
              <code className="tl-src">{e.source_line.trim()}</code>
              {lc && <span className="tl-loop">{lc.kind} #{lc.iteration}</span>}
              {e.scope !== "<module>" && <span className="tl-scope">{e.scope}()</span>}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
