import { LuPlay, LuPause, LuSquare, LuStepBack, LuStepForward, LuRotateCcw, LuRepeat, LuLoader } from "react-icons/lu";
import { SPEEDS } from "../player";

export type Phase = "idle" | "loading" | "playing" | "paused" | "finished" | "failed" | "stale" | "ready";

type Props = {
  phase: Phase; hasTrace: boolean; idx: number; total: number; speed: number; canResume: boolean;
  onRun: () => void; onPause: () => void; onResume: () => void; onStop: () => void; onFwd: () => void; onBack: () => void;
  onRestart: () => void; onReplay: () => void; onSpeed: (s: number) => void;
};

export function Controls(p: Props) {
  const playing = p.phase === "playing";
  const busy = p.phase === "loading";
  const label = (Object.entries(SPEEDS).find(([, v]) => v === p.speed)?.[0]) ?? "Custom";
  return (
    <div className="controls" role="toolbar" aria-label="Execution controls">
      <button className="btn primary" data-testid="btn-run" onClick={p.onRun} disabled={busy}>{busy ? <LuLoader className="spin" /> : <LuPlay />} Run</button>
      {playing
        ? <button className="btn" data-testid="btn-pause" onClick={p.onPause}><LuPause /> Pause</button>
        : <button className="btn" data-testid="btn-resume" onClick={p.onResume} disabled={!p.canResume}><LuPlay /> Resume</button>}
      <button className="btn" data-testid="btn-stop" onClick={p.onStop} disabled={!p.hasTrace && !busy}><LuSquare /> Stop</button>
      <span className="sep" />
      <button className="btn" data-testid="btn-back" onClick={p.onBack} disabled={!p.hasTrace || p.idx < 0} title="Step backward"><LuStepBack /> Back</button>
      <button className="btn" data-testid="btn-fwd" onClick={p.onFwd} disabled={busy || (p.hasTrace && p.idx >= p.total - 1 && p.phase !== "stale")} title="Step forward (one execution event)"><LuStepForward /> Step</button>
      <span className="sep" />
      <button className="btn" data-testid="btn-restart" onClick={p.onRestart} disabled={!p.hasTrace}><LuRotateCcw /> Restart</button>
      <button className="btn" data-testid="btn-replay" onClick={p.onReplay} disabled={!p.hasTrace}><LuRepeat /> Replay</button>
      <span className="sep" />
      <div className="speed" role="group" aria-label="Execution speed">
        {Object.entries(SPEEDS).map(([k, v]) => (
          <button key={k} className={"seg" + (p.speed === v ? " on" : "")} data-testid={`speed-${k.toLowerCase()}`} onClick={() => p.onSpeed(v)}>{k}</button>
        ))}
        <input type="range" min={0.25} max={4} step={0.25} value={p.speed} onChange={(e) => p.onSpeed(+e.target.value)} aria-label="Animation speed" data-testid="speed-slider" />
        <span className="speed-val" data-testid="speed-label">{label} · {p.speed}×</span>
      </div>
    </div>
  );
}
