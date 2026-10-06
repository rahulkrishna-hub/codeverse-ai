// Pure functions deriving the visual state from a trace + step index. No hidden state: stepping backward is
// just choosing a smaller index, so variables/console are *recomputed from the recorded events*, never undone.
import type { Change, Frame, TraceEvent, Vars } from "./types";

/** idx = -1 means "before the first event". */
export function stdoutUpTo(events: TraceEvent[], idx: number): string {
  let s = "";
  for (let i = 0; i <= idx && i < events.length; i++) s += events[i].stdout_delta;
  return s;
}

export type FrameView = { id: string; name: string; isCurrent: boolean; vars: Vars };

/** Frames shown in the memory panel for the event at idx (outermost first). */
export function framesAt(events: TraceEvent[], idx: number): FrameView[] {
  if (idx < 0 || idx >= events.length) return [];
  const e = events[idx];
  const stack: Frame[] = e.call_stack.length ? e.call_stack : [{ function: e.scope, line: e.line_number, is_current: true, variables: e.variables_after }];
  return stack.map((f, depth) => ({
    id: `${depth}:${f.function}`, name: f.function, isCurrent: f.is_current,
    vars: f.is_current ? e.variables_after : f.variables,
  }));
}

export function changesAt(events: TraceEvent[], idx: number): Map<string, Change> {
  const m = new Map<string, Change>();
  if (idx >= 0 && idx < events.length) for (const c of events[idx].explanation_context.changes ?? []) m.set(c.name, c);
  return m;
}

export type StepStatus = "pending" | "current" | "completed" | "failed";
export function stepStatus(events: TraceEvent[], i: number, idx: number): StepStatus {
  if (i > idx) return "pending";
  if (events[i].status === "failed") return "failed";
  return i === idx ? "current" : "completed";
}

export const STEP_BASE_MS = 1700;
export const SPEEDS = { Slow: 0.5, Normal: 1, Fast: 2.5 } as const;
export const stepDelay = (speed: number) => Math.max(120, STEP_BASE_MS / speed);

export function clampIdx(i: number, n: number) { return Math.max(-1, Math.min(n - 1, i)); }
