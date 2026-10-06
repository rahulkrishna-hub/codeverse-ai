# CodeVerse AI — Python core + learning features

Edit Python → **real execution trace** (isolated worker) → animated line-by-line execution, live variable memory cards,
calculation panel, console, step forward/backward, pause/resume, replay, speed control, time-travel timeline,
Tamil / Tanglish / English tutor. Nothing is pre-recorded: every animation is driven by events the backend recorded from *your* code.

## Run it

```bash
# 1) backend  (Python 3.11+)
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# 2) frontend  (Node 20+) — in another terminal
cd frontend
npm install
npm run build            # -> frontend/dist, served by the backend
# open http://localhost:8000
```
`npm run dev` rebuilds on change (reload the page). Set `window.CODEVERSE_API="http://localhost:8000"` if you serve `dist/` elsewhere.

## Tests

```bash
cd backend  && python -m unittest discover -s tests     # engine + HTTP API (real sandboxed worker, no mocks)
cd frontend && npm test                                  # step/memory/console derivation vs REAL backend traces
cd frontend && npm run typecheck:core                    # strict tsc on the non-React modules
# browser E2E (start the backend with a throw-away data dir so progress assertions are deterministic:
#  CV_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 8000 ; needs Playwright + Chromium):
cd frontend && PLAYWRIGHT_PATH=<path to playwright> CHROMIUM=<chromium binary> node tests/e2e.cjs
```

## Layout
```
backend/app/engine/     analysis.py (AST pre-checks) · tracer.py (sys.settrace) · serialize.py · worker.py (sandboxed child) · runner.py (limits)
backend/app/adapters/   LanguageAdapter interface + PythonAdapter; Java/JavaScript/C are "coming soon" stubs
backend/app/services/   execution.py · explainer.py (local rule-based tutor, en/ta/tanglish) · ai_provider.py (provider abstraction)
backend/app/main.py     HTTP API            backend/tests/   engine + API tests
frontend/src/           App · usePlayer (playback) · player.ts (pure state derivation) · components/*
frontend/tests/         player.test.ts · e2e.cjs (real browser) · fixtures.json (real traces)
```

## API
* `POST /api/execute` `{source_code, language, execution_options}` → `{execution_id, execution_status, trace_events[], final_variables, stdout, stderr, error, supported_features, sandbox, stats, truncated}`.
  Event: `event_index, line_number, event_type, source_line, scope, variables_before, variables_after, stdout_delta, explanation_context, call_stack, loop_context, status, error`.
  Empty/syntax/unsupported/runtime/timeout/limit/unknown-language cases return a structured `error` + `execution_status`.
* `POST /api/explain` `{mode: line|error|program|simpler|ask, language: en|ta|tanglish, event, source_code, result, question}`
* `GET /api/challenges` · `POST /api/challenges/{id}/check {source_code}` · `GET /api/predictions` · `POST /api/predictions/{id}/check {prediction}` · `GET /api/progress` · `POST /api/flowchart {source_code}`
* `GET /api/languages` · `GET /api/ai/status` · `GET /api/health`

## What is real / simulated / needs config
| | |
|---|---|
| **Real** | AST pre-check + `sys.settrace` tracing in a separate subprocess (CPU / memory / wall-clock / output / step limits; network + privilege drop best-effort). All animations, stepping, console, memory and errors come from the trace. |
| **Local fallback (labelled in UI)** | Tutor text is rule-based from the actual event (`is_llm:false`, "not an AI model"). |
| **Needs config, UNTESTED** | `ANTHROPIC_API_KEY` enables `AnthropicProvider` (stdlib HTTP). Not exercised (no key here); on failure the UI says so and shows the fallback. |
| **Learning features (real)** | Predict Before Run (10 exercises; the expected output is computed by actually running the snippet), 12 challenges (every shipped solution is verified by a test to pass and every starter to fail), hints, XP/levels/streak/topic progress persisted server-side, AST flowcharts that light up the executing box, click-a-line explainer. |
| **Not built yet** | PostgreSQL (progress uses a local JSON file behind a `ProgressStore` interface), accounts/multi-user, Java/JS/C engines (shown as "coming soon"), Monaco autocomplete. |
| **Sandbox** | **Local-development only** (`production_ready:false`, shown in the console footer). Use containers/gVisor/Firecracker before public exposure. |

## Supported Python subset (v1)
Assignments (tuple-unpack, augmented, subscript), arithmetic/comparison/boolean ops, f-strings, `print`, if/elif/else, for/while (break/continue/else),
functions (params, return, recursion, lambda), list/tuple/dict/set (comprehensions run as ONE step), try/except/finally/raise/assert/del/pass,
imports of `math random string itertools collections heapq bisect`.
**Rejected with a clear message:** classes, `with`, async, generators, `match`, other imports, private/dunder attribute access.

## Stack deviations
PyPI and the npm registry were blocked by the build environment's network policy (403), so the spec stack could not be installed:

| Spec | Used here | To port |
|---|---|---|
| FastAPI | Starlette + pydantic | handlers in `app/main.py` are plain async functions |
| Vite | esbuild (`build.mjs`) | add Vite + HTML entry |
| Tailwind | hand-written CSS (variables, dark + light) | — |
| Monaco | custom textarea + token-overlay editor (no autocomplete) | swap `CodeEditor.tsx` for `@monaco-editor/react` |
| Framer Motion | CSS keyframes + Web Animations API + SVG SMIL | — |
| Lucide | `react-icons/lu` (same icons) | — |

`.tsx` files were bundled by esbuild and exercised in a real browser, but **not type-checked** (no `@types/react` offline) — run `npm run typecheck` after `npm install`.
