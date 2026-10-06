"""Learning features: every shipped solution must really pass; progress/XP/streak; flowcharts. Real execution."""
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from starlette.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.services import flowchart, learning  # noqa: E402


class Content(unittest.TestCase):
    def setUp(self):
        self.store = learning.JsonFileStore(os.path.join(tempfile.mkdtemp(), "p.json"))

    def test_every_solution_passes_and_every_starter_fails(self):
        for c in learning.CHALLENGES:
            r = learning.check_challenge(self.store, c["id"], c["solution"])
            self.assertTrue(r["passed"], f"{c['id']}: {r.get('feedback')} got {r['stdout']!r}")
            s = learning.check_challenge(self.store, c["id"], c["starter"])
            self.assertFalse(s["passed"], f"starter of {c['id']} must not already pass")

    def test_every_prediction_snippet_runs(self):
        for p in learning.PREDICTIONS:
            r = learning.check_prediction(self.store, p["id"], "definitely wrong")
            self.assertFalse(r["correct"]); self.assertTrue(r["actual"].strip(), p["id"])
            self.assertTrue(learning.check_prediction(self.store, p["id"], r["actual"])["correct"], p["id"])

    def test_xp_only_awarded_once(self):
        c = learning.CHALLENGES[0]
        a = learning.check_challenge(self.store, c["id"], c["solution"]); b = learning.check_challenge(self.store, c["id"], c["solution"])
        self.assertEqual((a["xp_awarded"], b["xp_awarded"]), (c["xp"], 0))
        self.assertEqual(b["progress"]["xp"], c["xp"])
        self.assertEqual(learning.check_prediction(self.store, "p-arith", "9")["xp_awarded"], learning.PREDICTION_XP)
        self.assertEqual(learning.check_prediction(self.store, "p-arith", "9")["xp_awarded"], 0)

    def test_feedback_and_errors(self):
        r = learning.check_challenge(self.store, "sum-two", "print(1)")
        self.assertIn("expected '12'", r["feedback"])
        r = learning.check_challenge(self.store, "sum-two", "print(1/0)")
        self.assertIn("ZeroDivisionError", r["feedback"])
        self.assertIn("error", learning.check_challenge(self.store, "nope", "x"))

    def test_streak(self):
        t = dt.date(2026, 10, 5)
        d = lambda n: (t - dt.timedelta(days=n)).isoformat()
        self.assertEqual(learning.streak([d(0), d(1), d(2)], t), 3)
        self.assertEqual(learning.streak([d(1), d(2)], t), 2)       # today not done yet - streak still alive
        self.assertEqual(learning.streak([d(2), d(3)], t), 0)
        self.assertEqual(learning.streak([], t), 0)

    def test_progress_persists_across_store_instances(self):
        learning.check_challenge(self.store, "sum-two", learning.CHALLENGES[0]["solution"])
        again = learning.JsonFileStore(self.store.path)
        s = learning.summary(again.load())
        self.assertEqual((s["xp"], s["challenges_completed"], s["streak"]), (10, 1, 1))
        self.assertIn("Variables", s["topics_learned"])


class Flow(unittest.TestCase):
    def kinds(self, src, name="main"):
        ch = next(c for c in flowchart.build(src)["charts"] if c["name"] == name)
        return ch, [n["kind"] for n in ch["nodes"]]

    def test_if_loop_function(self):
        ch, k = self.kinds("x=1\nif x>0:\n    print(x)\nelse:\n    x=2\nfor i in range(3):\n    x+=i\ndef f(a):\n    return a\n")
        self.assertEqual(k[0], "start"); self.assertEqual(k[-1], "end")
        self.assertIn("decision", k); self.assertIn("loop", k)
        self.assertTrue(any(e["back"] for e in ch["edges"]))
        self.assertEqual({e["label"] for e in ch["edges"]} >= {"Yes", "No", "next item", "done"}, True)
        names = [c["name"] for c in flowchart.build("def f(a):\n    return a\n")["charts"]]
        self.assertEqual(names, ["main", "f"])

    def test_every_node_reachable_and_edges_valid(self):
        for src in ["while True:\n    break\n", "for i in range(3):\n    if i:\n        continue\n    print(i)\n", "try:\n    x=1/0\nexcept ZeroDivisionError:\n    x=0\n"]:
            for ch in flowchart.build(src)["charts"]:
                ids = {n["id"] for n in ch["nodes"]}
                self.assertTrue(all(e["from"] in ids and e["to"] in ids for e in ch["edges"]))
                seen, todo = set(), ["n0"]
                while todo:
                    n = todo.pop()
                    if n in seen: continue
                    seen.add(n); todo += [e["to"] for e in ch["edges"] if e["from"] == n]
                self.assertEqual(seen, ids, src)


class Http(unittest.TestCase):
    def setUp(self):
        main.store = learning.JsonFileStore(os.path.join(tempfile.mkdtemp(), "p.json"))
        self.c = TestClient(main.app)

    def test_endpoints(self):
        ch = self.c.get("/api/challenges").json()["challenges"]
        self.assertTrue(ch and "solution" not in ch[0] and "expected" not in ch[0])        # answers never leak
        resp = self.c.post(f"/api/challenges/{ch[0]['id']}/check", json={"source_code": learning.CHALLENGES[0]["solution"]})
        self.assertEqual(resp.status_code, 200); r = resp.json()
        bad = self.c.post(f"/api/challenges/{ch[0]['id']}/check", json={"source_code": "print(1/0)"})
        self.assertEqual(bad.status_code, 200); self.assertFalse(bad.json()["passed"])   # failing code is a normal 200 result, not a 404
        self.assertTrue(r["passed"]); self.assertEqual(self.c.get("/api/progress").json()["xp"], 10)
        ex = self.c.get("/api/predictions").json()["exercises"]
        self.assertNotIn("expected", ex[0])
        pr = self.c.post("/api/predictions/p-arith/check", json={"prediction": "9"})
        self.assertEqual((pr.status_code, pr.json()["correct"]), (200, True))
        self.assertEqual(self.c.post("/api/predictions/zzz/check", json={"prediction": "1"}).status_code, 404)
        self.assertEqual(self.c.post("/api/challenges/zzz/check", json={"source_code": "x"}).status_code, 404)
        f = self.c.post("/api/flowchart", json={"source_code": "x=1\nprint(x)"}).json()
        self.assertEqual(len(f["charts"][0]["nodes"]), 4)
        self.assertEqual(self.c.post("/api/flowchart", json={"source_code": "x = ("}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
