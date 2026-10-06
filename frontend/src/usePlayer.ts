import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BackendDown, executeCode } from "./api";
import { clampIdx, stepDelay } from "./player";
import type { ExecResult } from "./types";
import type { Phase } from "./components/Controls";

/** Freeze / unfreeze every running animation (CSS, WAAPI) and SVG SMIL so Pause really freezes mid-flight. */
const frozen: Animation[] = [];
function freeze() {
  document.getAnimations().forEach((a) => { if (a.playState === "running") { a.pause(); frozen.push(a); } });
  document.querySelectorAll<SVGSVGElement>("svg.connections").forEach((s) => s.pauseAnimations());
}
function unfreeze() {
  frozen.splice(0).forEach((a) => { try { a.play(); } catch { /* element gone */ } });
  document.querySelectorAll<SVGSVGElement>("svg.connections").forEach((s) => s.unpauseAnimations());
}

export function usePlayer(source: string, language: string) {
  const [result, setResult] = useState<ExecResult | null>(null);
  const [tracedSource, setTracedSource] = useState<string | null>(null);
  const [idx, setIdx] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loading, setLoading] = useState(false);
  const [netError, setNetError] = useState<string | null>(null);
  const [fly, setFly] = useState<{ n: number; dir: "fwd" | "jump" }>({ n: 0, dir: "jump" });
  const abort = useRef<AbortController | null>(null);
  const remaining = useRef<{ idx: number; ms: number } | null>(null);
  const events = result?.trace_events ?? [];
  const total = events.length;
  const stale = result != null && tracedSource !== source;

  const move = useCallback((i: number, dir: "fwd" | "jump") => { setIdx(i); setFly((f) => ({ n: f.n + 1, dir })); }, []);

  const run = useCallback(async (autoplay: boolean) => {
    abort.current?.abort();
    const ac = new AbortController(); abort.current = ac;
    setLoading(true); setNetError(null); setPlaying(false); frozen.length = 0; remaining.current = null;
    try {
      const r = await executeCode(source, language, ac.signal);
      setResult(r); setTracedSource(source);
      const n = r.trace_events.length;
      setIdx(n > 0 ? 0 : -1); setFly((f) => ({ n: f.n + 1, dir: "fwd" }));
      setPlaying(autoplay && n > 1);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setNetError(e instanceof BackendDown ? e.message : (e as Error).message);
    } finally { if (abort.current === ac) setLoading(false); }
  }, [source, language]);

  // autoplay timer, with exact pause/resume (remaining time is remembered per step)
  useEffect(() => {
    if (!playing || stale) return;
    if (idx >= total - 1) { setPlaying(false); return; }
    const full = stepDelay(speed);
    const wait = remaining.current?.idx === idx ? remaining.current.ms : full;
    const t0 = performance.now(); let fired = false;
    const h = setTimeout(() => { fired = true; remaining.current = null; move(idx + 1, "fwd"); }, wait);
    return () => { clearTimeout(h); if (!fired) remaining.current = { idx, ms: Math.max(0, wait - (performance.now() - t0)) }; };
  }, [playing, idx, speed, total, stale, move]);

  const api = useMemo(() => ({
    run: () => run(true),
    pause: () => { setPlaying(false); freeze(); },
    resume: () => { if (result && !stale && idx < total - 1) { unfreeze(); setPlaying(true); } },
    stop: () => { abort.current?.abort(); setPlaying(false); setLoading(false); setResult(null); setTracedSource(null); setIdx(-1); setNetError(null); remaining.current = null; frozen.length = 0; },
    fwd: () => { if (!result || stale) { void run(false); return; } setPlaying(false); remaining.current = null; unfreeze(); move(clampIdx(idx + 1, total), "fwd"); },
    back: () => { setPlaying(false); remaining.current = null; unfreeze(); move(clampIdx(idx - 1, total), "jump"); },
    jump: (i: number) => { setPlaying(false); remaining.current = null; unfreeze(); move(clampIdx(i, total), "jump"); },
    restart: () => { setPlaying(false); remaining.current = null; unfreeze(); move(-1, "jump"); },
    replay: () => { remaining.current = null; unfreeze(); move(total > 0 ? 0 : -1, "fwd"); setPlaying(total > 1); },
  }), [run, result, stale, idx, total, move]);

  const phase: Phase = loading ? "loading" : !result ? "idle" : stale ? "stale" : playing ? "playing"
    : events[idx]?.status === "failed" ? "failed" : idx >= total - 1 && total > 0 ? "finished" : idx >= 0 ? "paused" : "ready";

  return { result, events, idx, total, playing, speed, setSpeed, loading, netError, setNetError, stale, phase, fly, ...api };
}
