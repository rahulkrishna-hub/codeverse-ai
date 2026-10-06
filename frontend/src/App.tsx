import { useEffect, useMemo, useRef, useState } from "react";
import { LuCopy, LuRotateCcw, LuEraser, LuCode, LuWorkflow, LuSparkles, LuTerminal, LuTriangleAlert } from "react-icons/lu";
import { getAiStatus, getLanguages, getProgress } from "./api";
import { EXAMPLES } from "./examples";
import { changesAt, framesAt, stdoutUpTo } from "./player";
import { usePlayer } from "./usePlayer";
import type { ExplainLang, LangInfo, Progress } from "./types";
import { CodeEditor } from "./components/CodeEditor";
import { MemoryPanel } from "./components/MemoryPanel";
import { CalcPanel, calcOf } from "./components/CalcPanel";
import { Connections } from "./components/Connections";
import { Console } from "./components/Console";
import { Timeline } from "./components/Timeline";
import { Controls } from "./components/Controls";
import { Tutor } from "./components/Tutor";
import { TopNav, type Page } from "./components/TopNav";
import { Flowchart } from "./components/Flowchart";
import { ChallengesPage, LearnPage, ProgressPage } from "./components/Pages";

const safe = {
  get(k: string) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k: string, v: string) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};

export function App() {
  const [source, setSource] = useState(() => safe.get("cv.source") ?? EXAMPLES[0].code);
  const [exampleId, setExampleId] = useState(EXAMPLES[0].id);
  const [language, setLanguage] = useState("python");
  const [langs, setLangs] = useState<LangInfo[]>([{ id: "python", name: "Python", status: "available", monaco_language: "python" }]);
  const [theme, setTheme] = useState(() => safe.get("cv.theme") ?? "dark");
  const [explainLang, setExplainLang] = useState<ExplainLang>(() => (safe.get("cv.lang") as ExplainLang) ?? "tanglish");
  const [ai, setAi] = useState<{ provider: string; is_llm: boolean } | null>(null);
  const [tab, setTab] = useState<"code" | "viz" | "tutor" | "console">("code");   // small screens
  const [clearedAt, setClearedAt] = useState(-1);
  const [copied, setCopied] = useState(false);
  const [page, setPage] = useState<Page>("playground");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [progressErr, setProgressErr] = useState<string | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [vizTab, setVizTab] = useState<"memory" | "flow">("memory");
  const [autoRun, setAutoRun] = useState(false);

  const p = usePlayer(source, language);
  const ev = p.idx >= 0 ? p.events[p.idx] ?? null : null;

  useEffect(() => { getLanguages().then(setLangs); getAiStatus().then(setAi); getProgress().then(setProgress, (e) => setProgressErr(e.message)); }, []);
  useEffect(() => { if (autoRun && page === "playground") { setAutoRun(false); void p.run(); } }, [autoRun, page]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { document.documentElement.dataset.theme = theme; safe.set("cv.theme", theme); }, [theme]);
  useEffect(() => { safe.set("cv.source", source); }, [source]);
  useEffect(() => { safe.set("cv.lang", explainLang); }, [explainLang]);
  useEffect(() => { document.documentElement.style.setProperty("--spd", String(1 / p.speed)); }, [p.speed]);
  useEffect(() => { if (p.idx < clearedAt) setClearedAt(-1); }, [p.idx, clearedAt]);

  const frames = useMemo(() => framesAt(p.events, p.idx), [p.events, p.idx]);
  const changes = useMemo(() => changesAt(p.events, p.idx), [p.events, p.idx]);
  const text = useMemo(() => stdoutUpTo(p.events, p.idx).slice(clearedAt >= 0 ? stdoutUpTo(p.events, clearedAt).length : 0), [p.events, p.idx, clearedAt]);

  const vizRef = useRef<HTMLDivElement>(null);
  const calcRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef(new Map<string, HTMLElement>());
  const registerCard = (k: string, el: HTMLElement | null) => { el ? cardsRef.current.set(k, el) : cardsRef.current.delete(k); };
  const calc = calcOf(ev);
  const varNames = new Set(frames.flatMap((f) => Object.keys(f.vars)));
  const operandNames = (calc?.operands ?? []).map((o) => o.source).filter((s) => varNames.has(s));
  const targetNames = ev?.explanation_context.calculation && ev.explanation_context.targets ? ev.explanation_context.targets : [];

  const err = p.result?.error ?? null;
  const preRunError = err && p.result!.trace_events.length === 0;
  const errorLine = ev?.status === "failed" ? ev.line_number : err?.line ?? null;
  const showErrLine = !p.stale && errorLine != null && (preRunError || ev?.status === "failed");

  // Code Explainer: the real event for the selected line (latest run at/before the current step, else its first run)
  const lineEvent = useMemo(() => {
    if (selectedLine == null || p.stale) return null;
    let best: number | null = null;
    for (let i = 0; i < p.events.length; i++) if (p.events[i].line_number === selectedLine) { if (i <= p.idx) best = i; else if (best === null) best = i; if (i > p.idx) break; }
    return best === null ? null : p.events[best];
  }, [selectedLine, p.events, p.idx, p.stale]);
  const lineNote = lineEvent ? ` (step ${lineEvent.event_index + 1})` : "";

  function openInPlayground(code: string, run: boolean) {
    p.stop(); setSource(code); setExampleId(""); setSelectedLine(null); setPage("playground"); setAutoRun(run);
  }

  function loadExample(id: string) {
    const ex = EXAMPLES.find((e) => e.id === id); if (!ex) return;
    setExampleId(id); setSource(ex.code); p.stop(); setSelectedLine(null);
  }

  return (
    <div className="app" data-testid="app">
      <TopNav langs={langs} lang={language} onLang={setLanguage} theme={theme} onTheme={() => setTheme(theme === "dark" ? "light" : "dark")} page={page} onPage={setPage} progress={progress} />
      {page === "learn" && <LearnPage progress={progress} onProgress={setProgress} onWatch={(c) => openInPlayground(c, true)} />}
      {page === "challenges" && <ChallengesPage progress={progress} onProgress={setProgress} onOpen={(c) => openInPlayground(c, false)} />}
      {page === "progress" && <ProgressPage progress={progress} err={progressErr} />}
      {page === "playground" && <>
      <div className="tabs" role="tablist">
        {([["code", "Code", LuCode], ["viz", "Visualizer", LuWorkflow], ["tutor", "Tutor", LuSparkles], ["console", "Console", LuTerminal]] as const).map(([k, n, I]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}><I /> {n}</button>
        ))}
      </div>
      <main className={"workspace show-" + tab}>
        <section className="panel p-code" aria-label="Code editor">
          <div className="panel-bar">
            <select value={exampleId} onChange={(e) => loadExample(e.target.value)} aria-label="Example library" data-testid="example-select">
              {EXAMPLES.map((e) => <option key={e.id} value={e.id}>{e.topic} · {e.title}</option>)}
              {exampleId === "" && <option value="">Your code</option>}
            </select>
            <span className="grow" />
            <button className="icon-btn" title="Reset to the example's starter code" data-testid="btn-reset" onClick={() => { loadExample(exampleId); }}><LuRotateCcw /></button>
            <button className="icon-btn" title="Copy code" data-testid="btn-copy" onClick={async () => { try { await navigator.clipboard.writeText(source); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* clipboard blocked */ } }}><LuCopy /></button>
            <button className="icon-btn" title="Clear output" onClick={() => setClearedAt(p.idx)}><LuEraser /></button>
          </div>
          <CodeEditor value={source} onChange={setSource} activeLine={ev?.line_number ?? null} errorLine={showErrLine ? errorLine : null} stale={p.stale} selectedLine={selectedLine} onSelectLine={setSelectedLine} />
          {copied && <div className="toast">Copied</div>}
          {p.stale && <div className="banner warn" data-testid="stale-banner"><LuTriangleAlert /> You edited the code after the trace was recorded. Press Run to trace the new code.</div>}
          {p.netError && <div className="banner err" data-testid="net-error"><LuTriangleAlert /> {p.netError}</div>}
          {err && !p.stale && <div className="banner err" data-testid="exec-error"><LuTriangleAlert /> <b>{err.type}</b>{err.line ? ` (line ${err.line})` : ""}: {err.message}{err.hint ? ` — ${err.hint}` : ""}</div>}
        </section>

        <section className="panel p-viz" aria-label="Execution visualizer">
          <div className="status" data-testid="status">
            <span>Step <b data-testid="step-num">{Math.max(p.idx + 1, 0)}</b> / <b data-testid="step-total">{p.total}</b></span>
            <span>Line <b data-testid="status-line">{ev ? ev.line_number : "—"}</b></span>
            <span className={"pill " + p.phase} data-testid="phase">{({ idle: "Not running", loading: "Tracing…", playing: "Running", paused: "Paused", finished: "Finished", failed: "Failed", stale: "Code changed", ready: "Ready" } as const)[p.phase]}</span>
            {ev?.loop_context?.loops.map((l, i) => <span key={i} className="pill loop" data-testid="loop-pill">{l.kind} · iteration {l.iteration}{l.total ? `/${l.total}` : ""}{l.variable ? ` · ${l.variable}` : ""}</span>)}
            {ev && ev.scope !== "<module>" && <span className="pill fn">in {ev.scope}()</span>}
          </div>
          <div className="viztabs" role="tablist">
            <button role="tab" aria-selected={vizTab === "memory"} data-testid="viztab-memory" className={vizTab === "memory" ? "on" : ""} onClick={() => setVizTab("memory")}>Memory</button>
            <button role="tab" aria-selected={vizTab === "flow"} data-testid="viztab-flow" className={vizTab === "flow" ? "on" : ""} onClick={() => setVizTab("flow")}>Flowchart</button>
          </div>
          {vizTab === "memory" ? (
          <div className="viz" ref={vizRef}>
            <CalcPanel ref={calcRef} event={ev} idx={p.idx} />
            <MemoryPanel frames={frames} changes={changes} idx={p.idx} event={ev} registerCard={registerCard} />
            <Connections container={vizRef} calc={calcRef} cards={cardsRef} operandNames={operandNames} targetNames={targetNames} idx={p.idx} />
          </div>) : (
          <div className="viz"><Flowchart source={source} activeLine={p.stale ? null : ev?.line_number ?? null} activeScope={p.stale ? null : ev?.scope ?? null} /></div>)}
        </section>

        <section className="panel p-tutor" aria-label="AI tutor">
          <Tutor event={ev} result={p.result} source={source} lang={explainLang} onLang={setExplainLang} ai={ai} selectedLine={selectedLine} lineEvent={lineEvent} lineNote={lineNote} hasTrace={!!p.result && !p.stale}
            onLoadExample={(c) => { setSource(c); p.stop(); setTab("code"); }} />
        </section>

        <section className="panel p-bottom" aria-label="Console and history">
          <Controls phase={p.phase} hasTrace={!!p.result} idx={p.idx} total={p.total} speed={p.speed} canResume={!!p.result && !p.stale && p.idx < p.total - 1 && !p.playing}
            onRun={p.run} onPause={p.pause} onResume={p.resume} onStop={p.stop} onFwd={p.fwd} onBack={p.back} onRestart={p.restart} onReplay={p.replay} onSpeed={p.setSpeed} />
          <div className="bottom-grid">
            <Console text={text} lastDelta={ev?.stdout_delta ?? ""} idx={p.idx} event={ev} error={err} atEnd={p.idx >= p.total - 1} fly={p.fly} speed={p.speed}
              onClear={() => setClearedAt(p.idx)} stale={p.stale} sandboxWarning={p.result?.sandbox && !p.result.sandbox.production_ready ? p.result.sandbox.warning : undefined} />
            <div className="history"><div className="console-bar"><span>Execution history</span><span className="muted">click a step to time-travel</span></div>
              <Timeline events={p.events} idx={p.idx} onJump={p.jump} /></div>
          </div>
        </section>
      </main>
      </>}
    </div>
  );
}
