// Run: npm test   (Node >= 22). Fixtures are REAL backend traces (see ../README: regenerate with tests/gen_fixtures.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { changesAt, clampIdx, framesAt, stdoutUpTo, stepDelay, stepStatus } from "../src/player.ts";

const fx = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));

test("stdout is rebuilt from events, so stepping back removes later output", () => {
  const ev = fx.vars.trace_events;
  assert.equal(stdoutUpTo(ev, 2), "");
  assert.equal(stdoutUpTo(ev, 3), "30\n");
  assert.equal(stdoutUpTo(ev, 2), "", "going back again gives the earlier state (no mutation)");
  assert.equal(stdoutUpTo(ev, -1), "");
});

test("memory frames follow the recorded variables", () => {
  const ev = fx.vars.trace_events;
  assert.deepEqual(Object.keys(framesAt(ev, 0)[0].vars), ["x"]);
  assert.deepEqual(Object.keys(framesAt(ev, 2)[0].vars), ["x", "y", "result"]);
  assert.equal(framesAt(ev, 2)[0].vars.result.repr, "30");
  assert.equal(framesAt(ev, -1).length, 0);
});

test("created vs updated is derived from the event's changes", () => {
  const ev = fx.loop.trace_events;
  assert.equal(changesAt(ev, 0).get("t")?.kind, "created");
  const upd = ev.findIndex((e: any) => e.explanation_context.changes?.some((c: any) => c.name === "t" && c.kind === "updated"));
  assert.ok(upd > 0);
  const c = changesAt(ev, upd).get("t")!;
  assert.notEqual(c.previous?.repr, c.current?.repr);
});

test("call frames: callee frame is current, caller frame kept", () => {
  const ev = fx.func.trace_events;
  const i = ev.findIndex((e: any) => e.event_type === "call");
  const fr = framesAt(ev, i);
  assert.equal(fr.length, 2);
  assert.equal(fr[1].isCurrent, true);
  assert.ok("n" in fr[1].vars);
});

test("step status: pending / current / completed / failed", () => {
  const ev = fx.err.trace_events; const last = ev.length - 1;
  assert.equal(stepStatus(ev, 0, 0), "current");
  assert.equal(stepStatus(ev, 0, 1), "completed");
  assert.equal(stepStatus(ev, last, 0), "pending");
  assert.equal(stepStatus(ev, last, last), "failed");
});

test("clamp and speed", () => {
  assert.equal(clampIdx(-5, 4), -1); assert.equal(clampIdx(9, 4), 3);
  assert.ok(stepDelay(4) < stepDelay(1) && stepDelay(0.5) > stepDelay(1));
});
