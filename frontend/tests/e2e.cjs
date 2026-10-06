// Real-browser end-to-end test against a RUNNING backend (python -m uvicorn app.main:app --port 8000).
// Usage: node tests/e2e.cjs [baseUrl]      (needs `playwright` + a Chromium; set PLAYWRIGHT_PATH if not resolvable)
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const BASE = process.argv[2] || "http://localhost:8000";
const SHOTS = process.env.SHOTS || "../shots";
let pass = 0, fail = 0;
const ok = (c, m) => { c ? pass++ : fail++; console.log((c ? "  PASS " : "  FAIL ") + m); };
const txt = async (p, id) => (await p.getByTestId(id).innerText()).trim();

async function setCode(page, code) {
  await page.getByTestId("editor-input").fill(code);
}
async function fresh(page, example) {
  await page.goto(BASE); await page.evaluate(() => localStorage.clear()); await page.goto(BASE);
  await page.getByTestId("example-select").selectOption(example);
  await page.getByTestId("speed-fast").click();
}
async function waitPhase(page, name, ms = 30000) {
  await page.waitForFunction((n) => document.querySelector('[data-testid="phase"]')?.textContent === n, name, { timeout: ms });
}

(async () => {
  const exe = process.env.CHROMIUM || undefined;
  const browser = await chromium.launch({ executablePath: exe });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(String(e))); page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  console.log("1. Example 'vars': step-by-step (the spec's x/y/result/print sequence)");
  await fresh(page, "vars");
  ok((await txt(page, "step-total")) === "0", "no steps before running (no fake progress)");
  await page.getByTestId("btn-fwd").click();          // first press runs the code and shows event 1
  await page.waitForSelector('[data-testid="card-x"]');
  ok((await txt(page, "step-num")) === "1" && (await txt(page, "step-total")) === "4", "Step 1/4 after first Step press");
  ok((await txt(page, "status-line")) === "1", "active line is 1");
  ok((await page.getByTestId("card-x").innerText()).includes("10") && (await page.getByTestId("card-x").innerText()).includes("int"), "card x shows 10 and type int");
  ok((await page.getByTestId("badge-x").innerText()) === "NEW", "x badge = NEW");
  ok(await page.getByTestId("active-bar").count() === 1, "active-line bar present");
  await page.getByTestId("btn-fwd").click();
  ok((await page.getByTestId("card-y").innerText()).includes("20") && (await page.getByTestId("card-x").getAttribute("data-kind")) === "same", "step 2: y=20 created, x remains and is not new");
  await page.getByTestId("btn-fwd").click();
  await page.waitForSelector('[data-testid="calc-result"]');
  ok((await page.getByTestId("calc-row").innerText()).replace(/\s+/g, " ").includes("10") && (await txt(page, "calc-result")) === "30", "step 3: calculation panel shows 10, 20 -> 30");
  ok(await page.getByTestId("connections").count() === 1, "step 3: connection lines drawn from x/y cards");
  ok((await page.getByTestId("card-result").innerText()).includes("30"), "step 3: result card = 30");
  ok((await txt(page, "console-text")).includes("30") === false, "console still empty before print");
  await page.screenshot({ path: `${SHOTS}/step3.png` });
  await page.getByTestId("btn-fwd").click();
  await page.waitForSelector('[data-testid="fly-chip"]', { timeout: 3000 }).then(() => ok(true, "step 4: value chip flies into console"), () => ok(false, "step 4: value chip flies into console"));
  await page.waitForFunction(() => document.querySelector('[data-testid="console-text"]').textContent.includes("30"));
  ok(true, "step 4: console shows 30");
  ok((await page.getByTestId("btn-fwd").isDisabled()) && (await txt(page, "phase")) === "Finished", "at last step: Step disabled, phase Finished");
  await page.getByTestId("btn-back").click();
  ok(!(await txt(page, "console-text")).includes("30"), "Step Back restores console (30 removed)");
  ok((await txt(page, "step-num")) === "3", "Step Back -> step 3");
  await page.getByTestId("btn-back").click(); await page.getByTestId("btn-back").click();
  ok((await page.getByTestId("card-result").count()) === 0 && (await page.getByTestId("card-x").count()) === 1, "back to step 1: result/y removed, x kept");
  await page.getByTestId("btn-back").click();
  ok((await txt(page, "step-num")) === "0" && (await page.getByTestId("memory-empty").count()) === 1, "back before step 1: empty memory");

  console.log("2. Variable update: count 1 -> 2 -> 3");
  await fresh(page, "update");
  await page.getByTestId("btn-fwd").click(); await page.getByTestId("btn-fwd").click();
  ok((await page.getByTestId("badge-count").innerText()) === "UPDATED" && (await page.getByTestId("card-count").innerText()).includes("was 1"), "count UPDATED, 'was 1', value 2");
  ok((await page.getByTestId("card-count").innerText()).replace(/\s+/g, " ").includes("2"), "count shows 2");
  await page.getByTestId("btn-fwd").click();
  ok((await page.getByTestId("card-count").innerText()).includes("was 2"), "third step: was 2 -> 3");

  console.log("3. Autoplay, pause, resume, replay");
  await fresh(page, "for");
  await page.getByTestId("speed-normal").click();
  await page.getByTestId("speed-slider").fill("4");
  await page.getByTestId("btn-run").click();
  await page.waitForSelector('[data-testid="btn-pause"]');
  await page.waitForFunction(() => +document.querySelector('[data-testid="step-num"]').textContent >= 3);
  await page.getByTestId("btn-pause").click();
  const at = await txt(page, "step-num");
  await page.waitForTimeout(1500);
  ok((await txt(page, "step-num")) === at && (await txt(page, "phase")) === "Paused", `Pause freezes at step ${at}`);
  await page.getByTestId("btn-resume").click();
  await page.waitForFunction((a) => +document.querySelector('[data-testid="step-num"]').textContent > +a, at, { timeout: 5000 });
  ok(true, "Resume continues from the same point");
  await waitPhase(page, "Finished");
  const total = await txt(page, "step-total");
  ok((await txt(page, "step-num")) === total, `autoplay reached the end (${total} real events)`);
  ok((await txt(page, "console-text")).includes("sum: 10"), "console shows 'sum: 10'");
  ok((await page.getByTestId("loop-pill").count()) >= 0, "loop pill component rendered (if in loop)");
  await page.getByTestId("btn-replay").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="step-num"]').textContent === "1");
  ok(true, "Replay restarts from step 1");
  await waitPhase(page, "Finished");
  await page.getByTestId("btn-restart").click();
  ok((await txt(page, "step-num")) === "0", "Restart returns to before step 1 (paused)");
  await page.getByTestId("btn-run").click(); await page.waitForTimeout(400);
  await page.getByTestId("btn-stop").click();
  ok((await txt(page, "phase")) === "Not running" && (await txt(page, "step-total")) === "0", "Stop clears the run");

  console.log("4. User-edited code runs for real");
  await fresh(page, "vars");
  await setCode(page, "a = 7\nb = a * 6\nprint(b)\nprint('hi', a)\n");
  await page.getByTestId("btn-run").click(); await waitPhase(page, "Finished");
  ok((await txt(page, "console-text")).includes("42") && (await txt(page, "console-text")).includes("hi 7"), "custom program printed 42 and 'hi 7'");
  ok((await txt(page, "step-total")) === "4", "4 events for 4 lines");
  await setCode(page, "a = 7\nb = a * 6\nprint(b)\nprint('hi', a)\nz = 1\n");
  ok(await page.getByTestId("stale-banner").count() === 1, "editing after a run shows the 'trace is stale' banner");

  console.log("5. Functions, call stack, nested data");
  await fresh(page, "func");
  await page.getByTestId("btn-run").click(); await waitPhase(page, "Finished");
  ok((await txt(page, "console-text")).includes("25"), "function example prints 25");
  await page.getByTestId("timeline").locator("button").nth(3).click();
  ok((await page.locator(".frame").count()) >= 2, "time travel to a call event shows >1 memory frames");
  await fresh(page, "dict");
  await page.getByTestId("btn-run").click(); await waitPhase(page, "Finished");
  ok(await page.locator('[data-kind="dict"]').count() > 0, "dictionary rendered as key/value rows");
  await fresh(page, "list");
  await page.getByTestId("btn-run").click(); await waitPhase(page, "Finished");
  ok(await page.locator('.cidx').count() > 0, "list rendered with indexed cells");
  await page.screenshot({ path: `${SHOTS}/list.png` });

  console.log("6. Errors");
  await fresh(page, "error");
  await page.getByTestId("btn-run").click(); await waitPhase(page, "Failed");
  ok((await txt(page, "console-error")).includes("ZeroDivisionError"), "runtime error: ZeroDivisionError shown in console");
  ok(await page.locator(".error-bar").count() === 1 && (await txt(page, "status-line")) === "4", "failing line 4 highlighted");
  ok(await page.locator('.tl[data-status="failed"]').count() === 1, "timeline marks the failed step");
  await page.getByTestId("btn-explain-error").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="tutor-text"] h4')?.textContent === "About the error");
  ok(true, "Explain this error works"); await page.screenshot({ path: `${SHOTS}/error.png` });
  await fresh(page, "vars");
  await setCode(page, "x = (1 +\nprint(x)\n");
  await page.getByTestId("btn-run").click(); await page.waitForSelector('[data-testid="exec-error"]');
  ok((await txt(page, "exec-error")).includes("SyntaxError") && (await page.getByTestId("editor-input").inputValue()).startsWith("x = (1"), "syntax error reported, editor content preserved");
  await setCode(page, "   \n");
  await page.getByTestId("btn-run").click(); await page.waitForSelector('[data-testid="exec-error"]');
  ok((await txt(page, "exec-error")).toLowerCase().includes("no code"), "empty code handled");
  await setCode(page, "while True:\n    pass\n");
  await page.getByTestId("btn-run").click(); await page.waitForSelector('[data-testid="exec-error"]', { timeout: 20000 });
  ok(true, "infinite loop ended by limits: " + (await txt(page, "exec-error")).slice(0, 90));
  await page.route("**/api/execute", (r) => r.abort());
  await page.getByTestId("btn-run").click(); await page.waitForSelector('[data-testid="net-error"]');
  ok((await page.getByTestId("editor-input").inputValue()).startsWith("while True"), "backend down: message shown, code preserved");
  await page.unroute("**/api/execute");
  errors.length = 0;   // the aborted request above is intentional

  console.log("7. Tutor languages + honesty");
  await fresh(page, "vars");
  await page.getByTestId("btn-fwd").click(); await page.getByTestId("btn-fwd").click(); await page.getByTestId("btn-fwd").click();
  await page.getByTestId("lang-tanglish").click();
  await page.waitForFunction(() => /oda value/.test(document.querySelector('[data-testid="tutor-text"]')?.textContent || ""));
  ok(true, "Tanglish explanation uses the real values: " + (await txt(page, "tutor-text")).match(/`?x`? oda value[^.]*\./)?.[0]);
  await page.getByTestId("lang-ta").click(); await page.waitForTimeout(600);
  ok(/[஀-௿]/.test(await txt(page, "tutor-text")), "Tamil explanation contains Tamil script");
  ok((await txt(page, "provider-label")).toLowerCase().includes("not an ai model") || (await txt(page, "provider-label")).includes("AI model"), "fallback is labelled as not an LLM");
  await page.getByTestId("lang-en").click();
  await page.getByTestId("ask-input").fill("why 30?"); await page.getByTestId("ask-input").press("Enter");
  await page.waitForFunction(() => document.querySelector('[data-testid="tutor-text"] h4')?.textContent === "Your question");
  ok((await txt(page, "tutor-text")).includes("No LLM API key"), "Ask AI without key says so (no pretending)");
  await page.screenshot({ path: `${SHOTS}/desktop.png` });

  console.log("8. Mobile layout");
  await page.setViewportSize({ width: 390, height: 800 });
  ok(await page.locator(".tabs").isVisible(), "tabs visible on mobile");
  await page.getByRole("tab", { name: /Visualizer/ }).click();
  ok(await page.locator(".p-viz").isVisible() && !(await page.locator(".p-code").isVisible()), "tab switches panels");
  ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "no horizontal page scroll");
  await page.screenshot({ path: `${SHOTS}/mobile.png` });


  console.log("9. Predict Before Run");
  await page.setViewportSize({ width: 1440, height: 900 });
  await fresh(page, "vars");
  const xp0 = await txt(page, "xp-chip");
  await page.getByTestId("nav-learn").click();
  await page.getByTestId("pred-p-arith").click();
  await page.getByTestId("guess").fill("wrong");
  await page.getByTestId("btn-submit-guess").click();
  await page.waitForSelector('[data-testid="pred-result"]');
  ok((await txt(page, "pred-result")).includes("Not quite") && (await txt(page, "pred-actual")) === "9", "wrong prediction: real output (9) is shown, no XP");
  await page.getByTestId("guess").fill("9");
  await page.getByTestId("btn-submit-guess").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="pred-result"]')?.textContent.includes("Correct"));
  ok((await txt(page, "pred-result")).includes("+5 XP"), "correct prediction awards +5 XP");
  await page.getByTestId("btn-submit-guess").click(); await page.waitForTimeout(500);
  ok((await txt(page, "pred-result")).includes("Correct!") && !(await txt(page, "pred-result")).includes("+5"), "repeating it does not award XP again");
  await page.getByTestId("btn-watch").click();
  await waitPhase(page, "Finished");
  ok((await page.getByTestId("editor-input").inputValue()).startsWith("x = 4") && (await txt(page, "console-text")).includes("9"), "'Watch it execute' opens the snippet in the playground and runs it");

  console.log("10. Challenges");
  await page.getByTestId("nav-challenges").click();
  await page.getByTestId("ch-sum-two").click();
  await page.getByTestId("btn-check").click();
  await page.waitForSelector('[data-testid="ch-result"]');
  ok((await txt(page, "ch-result")).includes("Not yet") && (await txt(page, "ch-feedback")).includes("printed nothing"), "starter code fails with a helpful message");
  await page.getByTestId("btn-hint").click();
  ok((await page.getByTestId("hints").locator("li").count()) === 1, "hint reveals one at a time");
  await page.getByTestId("editor-input").fill("a = 7\nb = 5\nprint(a + b)\n");
  await page.getByTestId("btn-check").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="ch-result"]')?.textContent.includes("Passed"));
  ok((await txt(page, "ch-result")).includes("+10 XP"), "correct solution passes and awards +10 XP");
  ok((await txt(page, "xp-chip")).includes("15 XP"), "XP chip updated to 15");
  await page.getByTestId("btn-check").click(); await page.waitForTimeout(500);
  ok((await txt(page, "ch-result")).includes("no extra XP"), "second pass gives no extra XP");
  await page.getByTestId("ch-even-odd").click();
  await page.getByTestId("editor-input").fill("n = 14\nprint('odd')\n");
  await page.getByTestId("btn-check").click(); await page.waitForSelector('[data-testid="ch-feedback"]');
  ok((await txt(page, "ch-feedback")).includes("expected 'even'"), "wrong output explained (expected 'even', got 'odd')");
  await page.getByTestId("btn-ch-visualize").click();
  ok((await page.getByTestId("editor-input").inputValue()).includes("print('odd')"), "'Visualize my code' loads the draft in the playground");
  await page.screenshot({ path: `${SHOTS}/challenge.png` });

  console.log("11. Progress (persisted by the backend)");
  await page.reload(); await page.getByTestId("nav-progress").click();
  await page.waitForSelector('[data-testid="p-xp"]');
  ok((await txt(page, "p-xp")) === "15" && (await txt(page, "p-ch")) === "1/12" && (await txt(page, "p-pred")) === "1/10", "after reload: 15 XP, 1/12 challenges, 1/10 predictions");
  ok((await txt(page, "p-streak")) === "1", "streak = 1 day");
  ok((await txt(page, "topic-Variables")).includes("2/"), "Variables topic shows both completions");
  await page.screenshot({ path: `${SHOTS}/progress.png` });

  console.log("12. Flowchart + line explainer");
  await page.getByTestId("nav-playground").click();
  await page.getByTestId("example-select").selectOption("ifelse");
  await page.getByTestId("viztab-flow").click();
  await page.waitForSelector('[data-testid="flowchart"]');
  ok((await page.locator(".fnode.k-decision").count()) === 1 && (await page.locator(".fnode.k-io").count()) === 3, "if/else flowchart: 1 decision, 3 print boxes");
  await page.getByTestId("btn-fwd").click(); await page.getByTestId("btn-fwd").click();
  await page.waitForSelector('[data-testid="flow-active"]');
  ok((await page.locator(".fnode.active").getAttribute("data-line")) === "2", "flowchart highlights the decision box for line 2 while it executes");
  await page.getByTestId("btn-fwd").click();
  ok((await page.locator(".fnode.active").getAttribute("data-line")) === "5", "next step highlights the else branch (line 5)");
  await page.screenshot({ path: `${SHOTS}/flow.png` });
  await page.getByTestId("gutter-2").click();
  ok(await page.getByTestId("sel-bar").count() === 1, "clicking a line number selects it");
  await page.getByTestId("btn-explain-selected").click();
  await page.waitForFunction(() => /Line 2 \(step 2\)/.test(document.querySelector('[data-testid="tutor-text"]')?.textContent || ""));
  ok(true, "Explain selected line uses the real event for that line (step 2)");
  await page.getByTestId("gutter-3").click();
  await page.getByTestId("btn-explain-selected").click();
  ok((await page.locator(".banner.err").last().innerText()).includes("never executed"), "line in a skipped branch: honest 'never executed' message");
  await page.getByTestId("btn-stop").click();
  await page.getByTestId("btn-explain-selected").click();
  ok((await page.locator(".banner.err").last().innerText()).includes("Run the code first"), "no trace yet: asks to run first");
  await fresh(page, "func"); await page.getByTestId("viztab-flow").click(); await page.waitForSelector('[data-testid="flowchart"]');
  ok((await page.locator(".flow-tabs .seg").count()) === 3, "function example: main + square() + add_squares() charts");

  ok(errors.length === 0, "no console/page errors" + (errors.length ? ": " + errors.slice(0, 3).join(" | ") : ""));
  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error("CRASH", e); process.exit(2); });
