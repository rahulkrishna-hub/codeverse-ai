import { useLayoutEffect, useState } from "react";

type Path = { id: string; d: string; kind: "in" | "out" };

/** SVG overlay: curves from operand cards -> calculation panel -> target card, with a travelling dot. */
export function Connections({ container, calc, cards, operandNames, targetNames, idx }: {
  container: React.RefObject<HTMLElement | null>; calc: React.RefObject<HTMLElement | null>;
  cards: React.RefObject<Map<string, HTMLElement>>; operandNames: string[]; targetNames: string[]; idx: number;
}) {
  const [paths, setPaths] = useState<Path[]>([]);
  useLayoutEffect(() => {
    const root = container.current, cEl = calc.current;
    if (!root || !cEl) { setPaths([]); return; }
    const rr = root.getBoundingClientRect(), cr = cEl.getBoundingClientRect();
    const find = (n: string) => root.querySelector<HTMLElement>(`[data-card-name="${CSS.escape(n)}"]`);
    const out: Path[] = []; const st = root.scrollTop;
    const curve = (x1: number, y1: number, x2: number, y2: number) => {
      const my = (y1 + y2) / 2;
      return `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`;
    };
    const ins = [...new Set(operandNames)].map(find).filter(Boolean) as HTMLElement[];
    ins.forEach((el, i) => {
      const r = el.getBoundingClientRect();
      const tx = cr.left - rr.left + cr.width * (0.15 + 0.3 * ((i + 1) / (ins.length + 1)));
      out.push({ id: "in-" + i, kind: "in", d: curve(r.left + r.width / 2 - rr.left, r.top - rr.top + st, tx, cr.bottom - rr.top + st) });
    });
    const outs = [...new Set(targetNames)].map(find).filter(Boolean) as HTMLElement[];
    outs.forEach((el, i) => {
      const r = el.getBoundingClientRect();
      const sx = cr.left - rr.left + cr.width * (0.6 + 0.3 * ((i + 1) / (outs.length + 1)));
      out.push({ id: "out-" + i, kind: "out", d: curve(sx, cr.bottom - rr.top + st, r.left + r.width / 2 - rr.left, r.top - rr.top + st) });
    });
    setPaths(out);
  }, [idx, operandNames.join(","), targetNames.join(",")]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!paths.length) return null;
  return (
    <svg className="connections" data-testid="connections" key={idx} aria-hidden>
      {paths.map((p) => (
        <g key={p.id} className={"conn " + p.kind}>
          <path id={`${p.id}-${idx}`} d={p.d} pathLength={1} />
          <circle r="5"><animateMotion dur="1s" begin={p.kind === "in" ? "0s" : "1.1s"} fill="freeze" path={p.d} /></circle>
        </g>
      ))}
    </svg>
  );
}
