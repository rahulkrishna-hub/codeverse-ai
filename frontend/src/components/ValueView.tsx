import { useState } from "react";
import type { Desc } from "../types";

const PRIMS = new Set(["int", "float", "str", "bool", "NoneType"]);
export const isContainer = (d: Desc) => d.items !== undefined || d.entries !== undefined;

export function Prim({ d }: { d: Desc }) {
  if (d.type === "function") return <span className="v v-fn">def {d.name}({(d.params ?? []).join(", ")})</span>;
  return <span className={"v v-" + (PRIMS.has(d.type) ? d.type : "obj")}>{d.repr}</span>;
}

/** Lists/tuples/sets -> indexed cells, dicts -> key/value rows, nested containers -> expandable. */
export function ValueView({ d, prev, depth = 0 }: { d: Desc; prev?: Desc | null; depth?: number }) {
  if (!isContainer(d)) return <Prim d={d} />;
  if (d.entries) {
    const prevMap = new Map((prev?.entries ?? []).map((e) => [e.key.repr, e.value]));
    return (
      <div className="dict" data-kind="dict">
        {d.entries.length === 0 && <span className="empty">empty dict</span>}
        {d.entries.map((e, i) => {
          const before = prevMap.get(e.key.repr);
          const cls = !prev ? "" : before === undefined ? " cell-new" : before.repr !== e.value.repr ? " cell-changed" : "";
          return (
            <div className={"drow" + cls} key={i}>
              <span className="dkey"><Prim d={e.key} /></span><span className="darrow">→</span>
              <Nested d={e.value} prev={before} depth={depth + 1} />
            </div>
          );
        })}
        {d.truncated && <span className="empty">…more</span>}
      </div>
    );
  }
  const items = d.items ?? [];
  const showIdx = d.type !== "set";
  return (
    <div className="seq" data-kind={d.type}>
      <span className="seq-open">{d.type === "list" ? "[" : d.type === "tuple" ? "(" : "{"}</span>
      {items.length === 0 && <span className="empty">empty {d.type}</span>}
      {items.map((it, i) => {
        const before = prev?.items?.[i];
        const cls = !prev || !prev.items ? "" : before === undefined ? " cell-new" : before.repr !== it.repr ? " cell-changed" : "";
        return (
          <div className={"cell" + cls} key={i + ":" + it.repr}>
            {showIdx && <span className="cidx">{i}</span>}
            <div className="cval"><Nested d={it} prev={before} depth={depth + 1} /></div>
          </div>
        );
      })}
      {d.truncated && <span className="empty">…{(d.len ?? 0) - items.length} more</span>}
      <span className="seq-open">{d.type === "list" ? "]" : d.type === "tuple" ? ")" : "}"}</span>
    </div>
  );
}

function Nested({ d, prev, depth }: { d: Desc; prev?: Desc | null; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  if (!isContainer(d)) return <Prim d={d} />;
  return (
    <div className="nested">
      <button className="exp" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "▾" : "▸"} <span className="tname">{d.type}</span>{!open && <span className="v v-obj"> {d.repr}</span>}
      </button>
      {open && <ValueView d={d} prev={prev} depth={depth} />}
    </div>
  );
}
