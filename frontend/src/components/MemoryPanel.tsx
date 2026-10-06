import { useRef } from "react";
import type { Change, TraceEvent } from "../types";
import type { FrameView } from "../player";
import { ValueView, Prim, isContainer } from "./ValueView";

type Props = {
  frames: FrameView[]; changes: Map<string, Change>; idx: number; event: TraceEvent | null;
  registerCard: (key: string, el: HTMLElement | null) => void;
};

export function MemoryPanel({ frames, changes, idx, event, registerCard }: Props) {
  if (!event) return <div className="empty-state" data-testid="memory-empty">Press <b>Run</b> or <b>Step</b> — variables will appear here as memory cards.</div>;
  return (
    <div className="frames" data-testid="memory">
      {frames.map((f, depth) => (
        <section key={f.id} className={"frame" + (f.isCurrent ? " current" : "")} style={{ marginLeft: Math.min(depth, 3) * 10 }}>
          <header><span className="fname">{f.name === "<module>" ? "Global memory" : `${f.name}()`}</span>
            {depth > 0 && <span className="fbadge">call depth {depth}</span>}</header>
          <div className="cards">
            {Object.keys(f.vars).length === 0 && !(f.isCurrent && [...changes.values()].some(c => c.kind === "deleted")) && <span className="empty">no variables yet</span>}
            {Object.entries(f.vars).map(([name, d]) => {
              const ch = f.isCurrent ? changes.get(name) : undefined;
              const kind = ch?.kind === "created" ? "new" : ch?.kind === "updated" ? "updated" : "";
              const prev = ch?.kind === "updated" ? ch.previous : null;
              return (
                <div key={name} ref={(el) => registerCard(`${f.id}:${name}`, el)} data-card-name={f.isCurrent ? name : undefined}
                  data-kind={kind || "same"} data-testid={`card-${name}`}
                  className={"card " + kind + (isContainer(d) ? " wide" : "")}>
                  {/* keyed by idx so the CSS animation replays on every step that touches this variable */}
                  <div key={kind ? idx : "static"} className={kind ? "card-anim" : ""}>
                    <div className="card-head">
                      <span className="vname">{name}</span><span className="arrow">→</span>
                      <span className="vtype">{d.type}</span>
                      {kind && <span className={"badge " + kind} data-testid={`badge-${name}`}>{kind === "new" ? "NEW" : "UPDATED"}</span>}
                    </div>
                    <div className="card-body">
                      {prev && !isContainer(d) ? (
                        <div className="valswap"><span className="v-old"><Prim d={prev} /></span><span className="v-new"><ValueView d={d} /></span></div>
                      ) : <ValueView d={d} prev={prev} />}
                    </div>
                    {prev && <div className="was">was <Prim d={prev} /></div>}
                  </div>
                </div>
              );
            })}
            {f.isCurrent && [...changes.values()].filter((c) => c.kind === "deleted").map((c) => (
              <div key={"del-" + c.name + idx} className="card deleted"><div className="card-head"><span className="vname">{c.name}</span><span className="badge deleted">DELETED</span></div></div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
