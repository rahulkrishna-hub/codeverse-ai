import { useEffect, useState } from "react";
import { LuCircleCheck, LuCircle, LuLightbulb, LuPlay, LuFlame, LuTrophy, LuTarget, LuCheck, LuX, LuEye } from "react-icons/lu";
import { checkChallenge, checkPrediction, getChallenges, getPredictions } from "../api";
import type { Challenge, ChallengeResult, PredictionExercise, PredictionResult, Progress } from "../types";
import { tokenize } from "../highlight";
import { CodeEditor } from "./CodeEditor";

function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="codeblock" data-testid="code-block">
      {code.replace(/\n$/, "").split("\n").map((l, i) => (
        <div key={i}><span className="ln">{i + 1}</span>{tokenize(l).map((t, j) => <span key={j} className={"t-" + t.t}>{t.s}</span>)}</div>
      ))}
    </pre>
  );
}

function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { fn().then(setData, (e) => setErr(e.message)); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err };
}

/* ------------------------------------------------------------------ Learn: Predict Before Run */
export function LearnPage({ progress, onProgress, onWatch }: { progress: Progress | null; onProgress: (p: Progress) => void; onWatch: (code: string) => void }) {
  const { data, err } = useLoad(getPredictions);
  const [sel, setSel] = useState(0);
  const [guess, setGuess] = useState("");
  const [res, setRes] = useState<PredictionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const done = new Set(progress?.predicted_ids ?? []);
  const ex: PredictionExercise | undefined = data?.exercises[sel];
  useEffect(() => { setGuess(""); setRes(null); setError(null); }, [sel]);
  if (err) return <div className="page"><div className="banner err">{err}</div></div>;
  if (!data || !ex) return <div className="page"><div className="empty-state">Loading exercises…</div></div>;

  async function submit() {
    setBusy(true); setError(null);
    try { const r = await checkPrediction(ex!.id, guess); setRes(r); onProgress(r.progress); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="page two" data-testid="learn-page">
      <aside className="list panel">
        <h3>Predict before you run</h3>
        <p className="muted small">Read the code, type exactly what you think it prints, then the real engine runs it and compares. +{data.xp_each} XP for each first correct answer.</p>
        {data.exercises.map((e, i) => (
          <button key={e.id} className={"li" + (i === sel ? " on" : "")} onClick={() => setSel(i)} data-testid={`pred-${e.id}`}>
            {done.has(e.id) ? <LuCircleCheck className="ok" /> : <LuCircle />}<span>{e.title}</span><i>{e.topic}</i>
          </button>
        ))}
      </aside>
      <section className="detail panel">
        <h2>{ex.title} <span className="pill">{ex.topic}</span></h2>
        <CodeBlock code={ex.code} />
        <label className="lbl" htmlFor="guess">What will this print? (one line per print, exactly)</label>
        <textarea id="guess" data-testid="guess" className="guess" rows={4} value={guess} onChange={(e) => setGuess(e.target.value)} placeholder="Type your prediction…" />
        <div className="row">
          <button className="btn primary" data-testid="btn-submit-guess" onClick={submit} disabled={busy || !guess.trim()}><LuTarget /> Check my prediction</button>
          <button className="btn" data-testid="btn-watch" onClick={() => onWatch(ex.code)}><LuEye /> Watch it execute step by step</button>
          <button className="btn" onClick={() => setSel((sel + 1) % data.exercises.length)}>Next exercise</button>
        </div>
        {error && <div className="banner err">{error}</div>}
        {res && (
          <div className={"result " + (res.correct ? "good" : "bad")} data-testid="pred-result">
            <h4>{res.correct ? <><LuCheck /> Correct!{res.xp_awarded ? ` +${res.xp_awarded} XP` : ""}</> : <><LuX /> Not quite</>}</h4>
            <div className="cmp">
              <div><span className="muted">You predicted</span><pre>{res.prediction}</pre></div>
              <div><span className="muted">Python printed</span><pre data-testid="pred-actual">{res.actual}</pre></div>
            </div>
            {!res.correct && <p className="small">Use “Watch it execute” to see which step produced each value.</p>}
          </div>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ Challenges */
export function ChallengesPage({ progress, onProgress, onOpen }: { progress: Progress | null; onProgress: (p: Progress) => void; onOpen: (code: string) => void }) {
  const { data, err } = useLoad(getChallenges);
  const [sel, setSel] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [hints, setHints] = useState<Record<string, number>>({});
  const [res, setRes] = useState<Record<string, ChallengeResult>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const done = new Set(progress?.completed_ids ?? []);
  const ch: Challenge | undefined = data?.[sel];
  if (err) return <div className="page"><div className="banner err">{err}</div></div>;
  if (!data || !ch) return <div className="page"><div className="empty-state">Loading challenges…</div></div>;
  const code = drafts[ch.id] ?? ch.starter;
  const r = res[ch.id];
  const shown = hints[ch.id] ?? 0;

  async function check() {
    setBusy(true); setError(null);
    try { const out = await checkChallenge(ch!.id, code); setRes({ ...res, [ch!.id]: out }); onProgress(out.progress); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="page two" data-testid="challenges-page">
      <aside className="list panel">
        <h3>Challenges</h3>
        {data.map((c, i) => (
          <button key={c.id} className={"li" + (i === sel ? " on" : "")} onClick={() => { setSel(i); setError(null); }} data-testid={`ch-${c.id}`}>
            {done.has(c.id) ? <LuCircleCheck className="ok" /> : <LuCircle />}<span>{c.title}</span>
            <i>{"●".repeat(c.difficulty)} {c.xp} XP</i>
          </button>
        ))}
      </aside>
      <section className="detail panel">
        <h2>{ch.title} <span className="pill">{ch.topic}</span> {done.has(ch.id) && <span className="pill finished">completed</span>}</h2>
        <p data-testid="ch-prompt">{ch.prompt.split(/(`[^`]+`)/g).map((t, j) => t.startsWith("`") ? <code key={j}>{t.slice(1, -1)}</code> : t)}</p>
        <div className="ch-editor"><CodeEditor value={code} onChange={(v) => setDrafts({ ...drafts, [ch.id]: v })} activeLine={null} errorLine={null} stale={false} selectedLine={null} onSelectLine={() => {}} /></div>
        <div className="row">
          <button className="btn primary" data-testid="btn-check" onClick={check} disabled={busy}><LuPlay /> Check my answer</button>
          <button className="btn" onClick={() => onOpen(code)} data-testid="btn-ch-visualize"><LuEye /> Visualize my code</button>
          <button className="btn" onClick={() => { setDrafts({ ...drafts, [ch.id]: ch.starter }); setRes({ ...res, [ch.id]: undefined as any }); }}>Reset</button>
          <button className="btn" data-testid="btn-hint" disabled={shown >= ch.hints.length} onClick={() => setHints({ ...hints, [ch.id]: shown + 1 })}><LuLightbulb /> Hint ({shown}/{ch.hints.length})</button>
        </div>
        {shown > 0 && <ol className="hints" data-testid="hints">{ch.hints.slice(0, shown).map((h, i) => <li key={i}>{h}</li>)}</ol>}
        {error && <div className="banner err">{error}</div>}
        {r && (
          <div className={"result " + (r.passed ? "good" : "bad")} data-testid="ch-result">
            <h4>{r.passed ? <><LuCheck /> Passed!{r.xp_awarded ? ` +${r.xp_awarded} XP` : " (already completed — no extra XP)"}</> : <><LuX /> Not yet</>}</h4>
            {!r.passed && r.feedback && <p data-testid="ch-feedback">{r.feedback}</p>}
            <div className="cmp">
              <div><span className="muted">Expected output</span><pre>{r.expected}</pre></div>
              <div><span className="muted">Your output</span><pre>{r.stdout || "(nothing)"}</pre></div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ Progress */
export function ProgressPage({ progress, err }: { progress: Progress | null; err: string | null }) {
  if (err) return <div className="page"><div className="banner err">{err}</div></div>;
  if (!progress) return <div className="page"><div className="empty-state">Loading progress…</div></div>;
  const p = progress;
  return (
    <div className="page" data-testid="progress-page">
      <div className="tiles">
        <div className="tile"><LuTrophy /><b data-testid="p-xp">{p.xp}</b><span>XP · level {p.level}</span><div className="bar"><i style={{ width: `${p.xp_into_level}%` }} /></div></div>
        <div className="tile"><LuFlame /><b data-testid="p-streak">{p.streak}</b><span>day streak</span></div>
        <div className="tile"><LuCircleCheck /><b data-testid="p-ch">{p.challenges_completed}/{p.challenges_total}</b><span>challenges</span></div>
        <div className="tile"><LuTarget /><b data-testid="p-pred">{p.predictions_correct}/{p.predictions_total}</b><span>predictions right</span></div>
      </div>
      <div className="two-col">
        <section className="panel pad"><h3>Topics</h3>
          {p.topics.map((t) => {
            const total = t.challenges_total + t.predictions_total, d = t.challenges_done + t.predictions_done;
            return <div key={t.topic} className="topic" data-testid={`topic-${t.topic}`}><span>{t.topic}</span><div className="bar"><i style={{ width: `${total ? (100 * d) / total : 0}%` }} /></div><em>{d}/{total}</em></div>;
          })}
          <p className="muted small">Topics learned: {p.topics_learned.length ? p.topics_learned.join(", ") : "none yet — solve a challenge or predict an output."}</p>
        </section>
        <section className="panel pad"><h3>Recent</h3>
          {p.recent.length === 0 && <p className="muted">Nothing yet.</p>}
          {p.recent.map((r, i) => <div key={i} className="recent"><LuCircleCheck className="ok" /> {r.kind === "challenge" ? "Challenge" : "Prediction"} <b>{r.title}</b><span className="muted">{r.at.replace("T", " ")}</span></div>)}
        </section>
      </div>
      <p className="muted small">Stored in: {p.storage}. Streak counts days with at least one correct answer.</p>
    </div>
  );
}
