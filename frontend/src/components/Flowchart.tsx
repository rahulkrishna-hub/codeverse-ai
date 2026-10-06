import { useEffect, useMemo, useState } from "react";
import { getFlowchart } from "../api";
import type { FlowChart, FlowNode } from "../types";

const W = 168, H = 44, DH = 62, GX = 190, GY = 84;
type Pos = { x: number; y: number; w: number; h: number };

/** Layered layout: rank = longest forward path; x = mean of predecessors, colliding nodes are pushed apart. */
function layout(ch: FlowChart): { pos: Map<string, Pos>; width: number; height: number } {
  const fwd = ch.edges.filter((e) => !e.back);
  const rank = new Map<string, number>(ch.nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < ch.nodes.length; pass++) {
    let changed = false;
    for (const e of fwd) { const r = rank.get(e.from)! + 1; if (r > rank.get(e.to)!) { rank.set(e.to, r); changed = true; } }
    if (!changed) break;
  }
  const x = new Map<string, number>();
  const rows = new Map<number, FlowNode[]>();
  ch.nodes.forEach((n) => rows.set(rank.get(n.id)!, [...(rows.get(rank.get(n.id)!) ?? []), n]));
  const maxRank = Math.max(...rows.keys());
  for (let r = 0; r <= maxRank; r++) {
    const row = rows.get(r) ?? [];
    const want = new Map<string, number>();
    row.forEach((n) => {
      const preds = fwd.filter((e) => e.to === n.id).map((e) => x.get(e.from)).filter((v): v is number => v !== undefined);
      want.set(n.id, preds.length ? preds.reduce((a, b) => a + b, 0) / preds.length : 0);
    });
    row.sort((a, b) => want.get(a.id)! - want.get(b.id)! || ch.nodes.indexOf(a) - ch.nodes.indexOf(b));
    const cur = row.map((n) => want.get(n.id)!);
    for (let i = 1; i < cur.length; i++) cur[i] = Math.max(cur[i], cur[i - 1] + GX);
    const shift = row.reduce((s, n) => s + want.get(n.id)!, 0) / row.length - cur.reduce((s, v) => s + v, 0) / cur.length;
    row.forEach((n, i) => x.set(n.id, cur[i] + shift));
  }
  const minX = Math.min(...x.values());
  const pos = new Map<string, Pos>();
  let maxX = 0;
  ch.nodes.forEach((n) => {
    const h = n.kind === "decision" ? DH : H;
    const px = x.get(n.id)! - minX + W / 2 + 30;
    pos.set(n.id, { x: px, y: rank.get(n.id)! * GY + 30 + h / 2, w: W, h });
    maxX = Math.max(maxX, px);
  });
  return { pos, width: maxX + W / 2 + 70, height: (maxRank + 1) * GY + 40 };
}

function Shape({ n, p }: { n: FlowNode; p: Pos }) {
  const { x, y, w, h } = p; const l = x - w / 2, t = y - h / 2;
  switch (n.kind) {
    case "start": case "end": return <rect x={l} y={t} width={w} height={h} rx={h / 2} />;
    case "decision": return <polygon points={`${x},${t} ${l + w},${y} ${x},${t + h} ${l},${y}`} />;
    case "io": return <polygon points={`${l + 14},${t} ${l + w},${t} ${l + w - 14},${t + h} ${l},${t + h}`} />;
    case "loop": return <polygon points={`${l + 16},${t} ${l + w - 16},${t} ${l + w},${y} ${l + w - 16},${t + h} ${l + 16},${t + h} ${l},${y}`} />;
    case "call": return <g><rect x={l} y={t} width={w} height={h} rx={6} /><line x1={l + 8} y1={t} x2={l + 8} y2={t + h} /><line x1={l + w - 8} y1={t} x2={l + w - 8} y2={t + h} /></g>;
    default: return <rect x={l} y={t} width={w} height={h} rx={6} />;
  }
}

export function Flowchart({ source, activeLine, activeScope }: { source: string; activeLine: number | null; activeScope: string | null }) {
  const [charts, setCharts] = useState<FlowChart[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pick, setPick] = useState("main");
  useEffect(() => {
    const ac = new AbortController();
    const h = setTimeout(() => {
      getFlowchart(source, ac.signal).then((r) => { setCharts(r.charts); setErr(null); }, (e) => { if (e.name !== "AbortError") setErr(e.message); });
    }, 250);
    return () => { clearTimeout(h); ac.abort(); };
  }, [source]);
  const scope = activeScope && activeScope !== "<module>" ? activeScope : "main";
  const name = charts?.some((c) => c.name === scope) && activeLine != null ? scope : charts?.some((c) => c.name === pick) ? pick : "main";
  const chart = charts?.find((c) => c.name === name) ?? null;
  const lay = useMemo(() => (chart ? layout(chart) : null), [chart]);
  if (err) return <div className="banner err" data-testid="flow-error">Flowchart unavailable: {err}</div>;
  if (!chart || !lay) return <div className="empty-state small">Building flowchart…</div>;
  return (
    <div className="flow" data-testid="flowchart">
      {charts!.length > 1 && <div className="flow-tabs">{charts!.map((c) => <button key={c.name} className={"seg" + (c.name === name ? " on" : "")} onClick={() => setPick(c.name)}>{c.name === "main" ? "Main program" : `${c.name}()`}</button>)}</div>}
      <svg viewBox={`0 0 ${lay.width} ${lay.height}`} width="100%" style={{ maxWidth: lay.width }} role="img" aria-label="Program flowchart">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor" /></marker></defs>
        {chart.edges.map((e, i) => {
          const a = lay.pos.get(e.from)!, b = lay.pos.get(e.to)!;
          let d: string, lx: number, ly: number;
          if (e.back) {
            const rx = Math.max(a.x, b.x) + W / 2 + 24;
            const sy = a.y + a.h / 2, ey = b.y;
            d = `M${a.x},${sy} C${a.x},${sy + 26} ${rx},${sy + 26} ${rx},${(sy + ey) / 2} S${rx},${ey} ${b.x + b.w / 2},${ey}`;
            lx = rx + 4; ly = (sy + ey) / 2;
          } else {
            const sx = a.x, sy = a.y + a.h / 2, ex = b.x, ey = b.y - b.h / 2, my = (sy + ey) / 2;
            d = Math.abs(sx - ex) < 2 ? `M${sx},${sy} L${ex},${ey}` : `M${sx},${sy} C${sx},${my} ${ex},${my} ${ex},${ey}`;
            lx = Math.abs(sx - ex) < 2 ? sx + 14 : (sx + ex) / 2; ly = Math.abs(sx - ex) < 2 ? my + 3 : my - 4;
          }
          return (
            <g key={i} className={"fedge" + (e.back ? " back" : "")}>
              <path d={d} fill="none" markerEnd="url(#arr)" />
              {e.label && <text x={lx} y={ly} textAnchor="middle" className="elabel">{e.label}</text>}
            </g>
          );
        })}
        {chart.nodes.map((n) => {
          const p = lay.pos.get(n.id)!;
          const active = activeLine != null && n.line === activeLine;
          return (
            <g key={n.id} className={"fnode k-" + n.kind + (active ? " active" : "")} data-testid={active ? "flow-active" : undefined} data-line={n.line ?? ""}>
              <Shape n={n} p={p} />
              <text x={p.x} y={p.y + 4} textAnchor="middle">{n.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
