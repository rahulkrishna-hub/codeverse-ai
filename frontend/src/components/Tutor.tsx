import { useEffect, useRef, useState } from "react";
import { LuSparkles, LuBot, LuSend } from "react-icons/lu";
import { explain } from "../api";
import type { ExecResult, Explanation, ExplainLang, TraceEvent } from "../types";

type Props = {
  event: TraceEvent | null; result: ExecResult | null; source: string; lang: ExplainLang; onLang: (l: ExplainLang) => void;
  selectedLine: number | null; lineEvent: TraceEvent | null; lineNote: string; hasTrace: boolean;
  onLoadExample: (code: string) => void; ai: { provider: string; is_llm: boolean } | null;
};
const LANGS: [ExplainLang, string][] = [["en", "English"], ["ta", "தமிழ்"], ["tanglish", "Tanglish"]];

export function Tutor({ event, result, source, lang, onLang, onLoadExample, ai, selectedLine, lineEvent, lineNote, hasTrace }: Props) {
  const [exp, setExp] = useState<Explanation | null>(null);
  const [title, setTitle] = useState("This step");
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const manual = useRef(false);        // a button-triggered answer stays until the step changes
  const ctl = useRef<AbortController | null>(null);

  async function run(mode: string, ttl: string, extra: Record<string, unknown> = {}) {
    ctl.current?.abort(); const c = new AbortController(); ctl.current = c;
    setErr(null);
    try {
      const r = await explain({ mode, language: lang, source_code: source, event, result, ...extra } as any, c.signal);
      setExp(r); setTitle(ttl);
    } catch (e) { if ((e as Error).name !== "AbortError") setErr((e as Error).message); }
  }

  // Auto-explain the *current* execution event whenever the step or language changes.
  useEffect(() => {
    manual.current = false;
    if (!event) { setExp(null); setErr(null); return; }
    const h = setTimeout(() => run("line", "This step"), 120);
    return () => { clearTimeout(h); ctl.current?.abort(); };
  }, [event?.event_index, event === null, lang]);       // eslint-disable-line react-hooks/exhaustive-deps

  const hasErr = !!(result?.error);
  return (
    <div className="tutor" data-testid="tutor">
      <div className="tutor-head">
        <span className="tutor-title"><LuSparkles /> AI Tutor</span>
        <div className="seg-group" role="group" aria-label="Explanation language">
          {LANGS.map(([k, n]) => <button key={k} className={"seg" + (lang === k ? " on" : "")} data-testid={`lang-${k}`} onClick={() => onLang(k)}>{n}</button>)}
        </div>
      </div>
      <div className="tutor-actions">
        <button className="chipbtn" disabled={!event} onClick={() => run("line", "This step")}>Explain this line</button>
        <button className="chipbtn" disabled={selectedLine == null} data-testid="btn-explain-selected" title="Click a line number in the editor first"
          onClick={() => { if (lineEvent) run("line", `Line ${selectedLine}${lineNote}`, { event: lineEvent }); else { setExp(null); setErr(hasTrace ? `Line ${selectedLine} was never executed in this run, so there is nothing to explain yet (it may be in a branch that was skipped).` : "Run the code first — the tutor explains lines using real execution data."); } }}>
          {selectedLine == null ? "Explain selected line" : `Explain line ${selectedLine}`}</button>
        <button className="chipbtn" disabled={!hasErr} data-testid="btn-explain-error" onClick={() => run("error", "About the error")}>Explain this error</button>
        <button className="chipbtn" disabled={!source.trim()} data-testid="btn-explain-program" onClick={() => run("program", "Whole program")}>Explain the whole program</button>
        <button className="chipbtn" onClick={() => run("simpler", "A simpler example")}>Give me a simpler example</button>
      </div>
      <div className="tutor-body" aria-live="polite">
        {err && <div className="banner err">{err}</div>}
        {!exp && !err && <div className="empty-state small">Step through your code — the tutor explains each real execution step using the actual variable values.</div>}
        {exp && (
          <article data-testid="tutor-text">
            <h4>{title}</h4>
            {exp.sections.map((s, i) => <section key={i}><h5>{s.title}</h5><p>{s.body.split(/(`[^`]+`)/g).map((t, j) => t.startsWith("`") ? <code key={j}>{t.slice(1, -1)}</code> : t)}</p></section>)}
            {exp.example_code && <><pre className="ex">{exp.example_code}</pre><button className="btn small" onClick={() => onLoadExample(exp.example_code!)}>Load this in the editor</button></>}
            <footer className={"prov " + (exp.is_llm ? "llm" : "local")} data-testid="provider-label"><LuBot /> {exp.label}</footer>
          </article>
        )}
      </div>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); if (q.trim()) run("ask", "Your question", { question: q }); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask AI about this code…" aria-label="Ask AI about this code" data-testid="ask-input" />
        <button className="btn small" type="submit" aria-label="Send"><LuSend /></button>
      </form>
      <div className="ai-status" data-testid="ai-status">{ai ? (ai.is_llm ? `LLM provider: ${ai.provider}` : "No LLM API key configured → local rule-based tutor (not an AI model)") : "Backend not reachable"}</div>
    </div>
  );
}
