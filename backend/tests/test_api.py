"""HTTP-layer tests (Starlette TestClient). Execution is the REAL isolated worker - nothing mocked."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)


class Api(unittest.TestCase):
    def test_health_and_languages(self):
        self.assertEqual(c.get("/api/health").json()["status"], "ok")
        langs = {l["id"]: l["status"] for l in c.get("/api/languages").json()["languages"]}
        self.assertEqual(langs["python"], "available")
        self.assertEqual(langs["java"], "coming_soon")

    def test_execute_real_trace(self):
        r = c.post("/api/execute", json={"source_code": "x = 10\ny = 20\nresult = x + y\nprint(result)\n"}).json()
        self.assertEqual(r["execution_status"], "completed")
        self.assertEqual([e["line_number"] for e in r["trace_events"]], [1, 2, 3, 4])
        self.assertEqual(r["stdout"], "30\n")
        self.assertEqual(r["trace_events"][2]["explanation_context"]["calculation"]["result"], "30")
        self.assertFalse(r["sandbox"]["production_ready"])       # honest labelling

    def test_unknown_and_unavailable_language(self):
        self.assertEqual(c.post("/api/execute", json={"source_code": "x=1", "language": "cobol"}).json()["execution_status"], "invalid_language")
        self.assertEqual(c.post("/api/execute", json={"source_code": "x=1", "language": "java"}).json()["execution_status"], "language_unavailable")

    def test_validation_errors(self):
        self.assertEqual(c.post("/api/execute", content=b"not json").status_code, 400)
        self.assertEqual(c.post("/api/execute", json={"source_code": 5}).status_code, 422)

    def test_empty_syntax_runtime(self):
        self.assertEqual(c.post("/api/execute", json={"source_code": "  \n"}).json()["execution_status"], "empty")
        s = c.post("/api/execute", json={"source_code": "x = (1 +\n"}).json()
        self.assertEqual(s["error"]["type"], "SyntaxError")
        r = c.post("/api/execute", json={"source_code": "a = 1\nb = a / 0\n"}).json()
        self.assertEqual(r["error"]["type"], "ZeroDivisionError")
        self.assertEqual(r["trace_events"][-1]["status"], "failed")

    def test_explain_modes_and_honesty(self):
        r = c.post("/api/execute", json={"source_code": "x = 10\ny = 20\nr = x + y\n"}).json()
        e = c.post("/api/explain", json={"mode": "line", "language": "tanglish", "event": r["trace_events"][2]}).json()
        self.assertFalse(e["is_llm"]); self.assertIn("30", e["text"]); self.assertIn("oda value", e["text"])
        self.assertTrue(any("஀" <= ch <= "௿" for ch in c.post("/api/explain", json={"mode": "line", "language": "ta", "event": r["trace_events"][2]}).json()["text"]))
        self.assertEqual(c.post("/api/explain", json={"mode": "line"}).status_code, 422)
        ask = c.post("/api/explain", json={"mode": "ask", "question": "why?", "language": "en", "event": r["trace_events"][0]}).json()
        self.assertFalse(ask["is_llm"]); self.assertIn("No LLM API key", ask["text"])
        self.assertEqual(c.get("/api/ai/status").json()["is_llm"], False)


if __name__ == "__main__":
    unittest.main()
