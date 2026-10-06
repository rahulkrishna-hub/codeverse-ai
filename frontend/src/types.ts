export type Desc = {
  type: string; repr: string; value?: unknown; len?: number; truncated?: boolean;
  items?: Desc[]; entries?: { key: Desc; value: Desc }[]; name?: string; params?: string[];
};
export type Vars = Record<string, Desc>;
export type Change = { name: string; kind: "created" | "updated" | "deleted"; previous: Desc | null; current: Desc | null };
export type Operand = { source: string; value: string; type: string };
export type Calc = { expression: string; operands: Operand[]; operator: string | null; result: string; result_type: string; truth?: boolean };
export type LoopInfo = { line: number; kind: string; iteration: number; total: number | null; variable: string | null; is_header: boolean; exiting: boolean | null; header: string };
export type Frame = { function: string; line: number; is_current: boolean; variables: Vars };
export type Ctx = {
  changes?: Change[]; calculation?: Calc; condition?: Calc & { truth: boolean }; branch_taken?: boolean;
  targets?: string[]; value_source?: string; return_value?: Desc; print?: { args: Operand[] };
  function?: { name: string; params: string[] }; args?: { name: string; value: Desc }[]; caller_line?: number;
  enclosing?: { kind: string; line: number; header: string; name?: string }[];
  [k: string]: unknown;
};
export type TraceEvent = {
  event_index: number; line_number: number; event_type: string; source_line: string; scope: string;
  variables_before: Vars; variables_after: Vars; stdout_delta: string; explanation_context: Ctx;
  call_stack: Frame[]; loop_context: { loops: LoopInfo[]; depth: number } | null;
  status: "ok" | "failed"; error: { type: string; message: string } | null;
};
export type ExecError = { type: string; kind: string; message: string; line: number | null; column?: number | null; hint?: string | null; traceback?: { function: string; line: number; source: string }[] };
export type Sandbox = { mode: string; network_isolated: boolean; privilege_dropped: boolean; production_ready: boolean; warning: string };
export type ExecResult = {
  execution_id: string; execution_status: string; language: string; trace_events: TraceEvent[];
  final_variables: Vars; stdout: string; stderr: string; error: ExecError | null; supported_features: string[];
  truncated: boolean; sandbox: Sandbox | null; stats: { event_count: number; elapsed_ms: number };
};
export type Explanation = {
  provider: string; is_llm: boolean; language: string; label: string; sections: { title: string; body: string }[];
  text: string; example_code?: string;
};
export type LangInfo = { id: string; name: string; status: "available" | "coming_soon"; monaco_language: string };
export type ExplainLang = "en" | "ta" | "tanglish";

export type Challenge = { id: string; title: string; topic: string; difficulty: number; xp: number; prompt: string; starter: string; hints: string[] };
export type TopicStat = { topic: string; challenges_done: number; challenges_total: number; predictions_done: number; predictions_total: number };
export type Progress = {
  xp: number; level: number; xp_into_level: number; streak: number; challenges_completed: number; challenges_total: number;
  predictions_correct: number; predictions_total: number; topics: TopicStat[]; topics_learned: string[];
  completed_ids: string[]; predicted_ids: string[]; recent: { kind: string; id: string; title: string; at: string }[]; storage: string;
};
export type ChallengeResult = { passed: boolean; expected: string; stdout: string; execution_status: string; error: ExecError | null; xp_awarded: number; first_time: boolean; feedback?: string; progress: Progress };
export type PredictionExercise = { id: string; title: string; topic: string; code: string };
export type PredictionResult = { correct: boolean; actual: string; prediction: string; xp_awarded: number; progress: Progress };
export type FlowNode = { id: string; kind: string; label: string; line: number | null };
export type FlowEdge = { from: string; to: string; label: string; back: boolean };
export type FlowChart = { name: string; nodes: FlowNode[]; edges: FlowEdge[] };
