import type { Challenge, ChallengeResult, FlowChart, PredictionExercise, PredictionResult, Progress, ExecResult, Explanation, ExplainLang, LangInfo, TraceEvent } from "./types";

const BASE = (globalThis as any).CODEVERSE_API ?? "";

export class BackendDown extends Error {}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new BackendDown("Cannot reach the CodeVerse backend. Is it running? (uvicorn app.main:app --port 8000)");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message ?? `Request failed (${res.status})`);
  return data as T;
}

export const executeCode = (source_code: string, language: string, signal?: AbortSignal) =>
  post<ExecResult>("/api/execute", { source_code, language, execution_options: {} }, signal);

export const explain = (p: { mode: string; language: ExplainLang; source_code: string; event?: TraceEvent | null; result?: ExecResult | null; question?: string }, signal?: AbortSignal) =>
  post<Explanation>("/api/explain", { ...p, event: p.event ?? null, result: p.result ? { error: p.result.error } : null }, signal);

export async function getLanguages(): Promise<LangInfo[]> {
  try { return (await (await fetch(BASE + "/api/languages")).json()).languages; } catch { return [{ id: "python", name: "Python", status: "available", monaco_language: "python" }]; }
}
export async function getAiStatus(): Promise<{ provider: string; is_llm: boolean } | null> {
  try { return await (await fetch(BASE + "/api/ai/status")).json(); } catch { return null; }
}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try { res = await fetch(BASE + path); } catch { throw new BackendDown("Cannot reach the CodeVerse backend. Is it running? (uvicorn app.main:app --port 8000)"); }
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}
export const getChallenges = () => get<{ challenges: Challenge[] }>("/api/challenges").then((r) => r.challenges);
export const checkChallenge = (id: string, source_code: string) => post<ChallengeResult>(`/api/challenges/${id}/check`, { source_code });
export const getPredictions = () => get<{ exercises: PredictionExercise[]; xp_each: number }>("/api/predictions");
export const checkPrediction = (id: string, prediction: string) => post<PredictionResult>(`/api/predictions/${id}/check`, { prediction });
export const getProgress = () => get<Progress>("/api/progress");
export const getFlowchart = (source_code: string, signal?: AbortSignal) => post<{ charts: FlowChart[] }>("/api/flowchart", { source_code }, signal);
