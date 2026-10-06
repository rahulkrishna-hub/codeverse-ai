"""Challenges, predict-before-run exercises and progress tracking.

* Challenge checking and prediction checking both RUN the learner's/real code through the real sandboxed
  engine - expected outputs for predictions are never stored, they are computed by executing the snippet.
* Progress is stored through ``ProgressStore``. ``JsonFileStore`` is the local-development implementation;
  a PostgreSQL store only has to implement the same three methods (load / save) - see README.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
from typing import Optional, Protocol

from app.config import settings
from app.services.execution import execute

# --------------------------------------------------------------------------- content

CHALLENGES: list[dict] = [
    {"id": "sum-two", "title": "Add two numbers", "topic": "Variables", "difficulty": 1, "xp": 10,
     "prompt": "`a` and `b` are already set. Print their sum.",
     "starter": "a = 7\nb = 5\n# print the sum of a and b\n", "expected": "12",
     "hints": ["Use + to add two numbers.", "print(a + b) shows the result in the console."],
     "solution": "a = 7\nb = 5\nprint(a + b)\n"},
    {"id": "even-odd", "title": "Even or odd?", "topic": "Conditions", "difficulty": 1, "xp": 10,
     "prompt": "`n` is 14. Print `even` if it is even, otherwise print `odd`.",
     "starter": "n = 14\n# print even or odd\n", "expected": "even",
     "hints": ["n % 2 gives the remainder after dividing by 2.", "if n % 2 == 0: ... else: ..."],
     "solution": "n = 14\nif n % 2 == 0:\n    print('even')\nelse:\n    print('odd')\n"},
    {"id": "count-five", "title": "Count to 5", "topic": "Loops", "difficulty": 1, "xp": 10,
     "prompt": "Print the numbers 1 to 5, one per line.",
     "starter": "# use a for loop\n", "expected": "1\n2\n3\n4\n5",
     "hints": ["range(1, 6) gives 1,2,3,4,5 (the end is excluded).", "for i in range(1, 6): print(i)"],
     "solution": "for i in range(1, 6):\n    print(i)\n"},
    {"id": "sum-ten", "title": "Sum of 1 to 10", "topic": "Loops", "difficulty": 2, "xp": 20,
     "prompt": "Add up the numbers 1 to 10 with a loop and print the total.",
     "starter": "total = 0\n# loop here\n", "expected": "55",
     "hints": ["Keep a running total variable.", "Inside the loop: total = total + i. Print after the loop."],
     "solution": "total = 0\nfor i in range(1, 11):\n    total = total + i\nprint(total)\n"},
    {"id": "countdown", "title": "Countdown", "topic": "Loops", "difficulty": 2, "xp": 20,
     "prompt": "Print 3, 2, 1 (one per line) with a while loop, then print `Go!`.",
     "starter": "n = 3\n# while loop here\n", "expected": "3\n2\n1\nGo!",
     "hints": ["Loop while n > 0.", "Print n, then n = n - 1. Print Go! after the loop."],
     "solution": "n = 3\nwhile n > 0:\n    print(n)\n    n = n - 1\nprint('Go!')\n"},
    {"id": "square-fn", "title": "Write a function", "topic": "Functions", "difficulty": 2, "xp": 20,
     "prompt": "Define `square(n)` that returns n times n so the last line prints 81.",
     "starter": "# define square here\nprint(square(9))\n", "expected": "81",
     "hints": ["def square(n):", "Use return n * n"],
     "solution": "def square(n):\n    return n * n\nprint(square(9))\n"},
    {"id": "list-max", "title": "Biggest in a list", "topic": "Lists", "difficulty": 2, "xp": 20,
     "prompt": "Find the largest number in `nums` using a loop and print it.",
     "starter": "nums = [3, 9, 2, 7]\nbiggest = nums[0]\n# loop here\n", "expected": "9",
     "hints": ["Compare every item with biggest.", "if x > biggest: biggest = x"],
     "solution": "nums = [3, 9, 2, 7]\nbiggest = nums[0]\nfor x in nums:\n    if x > biggest:\n        biggest = x\nprint(biggest)\n"},
    {"id": "reverse-str", "title": "Reverse a word", "topic": "Strings", "difficulty": 2, "xp": 20,
     "prompt": "Print the word `python` reversed.",
     "starter": "s = 'python'\n# print it reversed\n", "expected": "nohtyp",
     "hints": ["Build a new string letter by letter.", "result = ch + result inside a for ch in s loop. (Or s[::-1].)"],
     "solution": "s = 'python'\nresult = ''\nfor ch in s:\n    result = ch + result\nprint(result)\n"},
    {"id": "word-count", "title": "Count words with a dict", "topic": "Dictionaries", "difficulty": 3, "xp": 30,
     "prompt": "Count how often each word appears in `words` using a dictionary and print the dictionary.",
     "starter": "words = ['a', 'b', 'a', 'c', 'a']\ncounts = {}\n# loop here\n", "expected": "{'a': 3, 'b': 1, 'c': 1}",
     "hints": ["counts.get(w, 0) gives 0 for a new word.", "counts[w] = counts.get(w, 0) + 1"],
     "solution": "words = ['a', 'b', 'a', 'c', 'a']\ncounts = {}\nfor w in words:\n    counts[w] = counts.get(w, 0) + 1\nprint(counts)\n"},
    {"id": "times-table", "title": "Times table", "topic": "Loops", "difficulty": 2, "xp": 20,
     "prompt": "Print the 3 times table for 1..3 exactly like `3 x 1 = 3`.",
     "starter": "# print three lines\n", "expected": "3 x 1 = 3\n3 x 2 = 6\n3 x 3 = 9",
     "hints": ["Loop i from 1 to 3.", "print('3 x', i, '=', 3 * i)"],
     "solution": "for i in range(1, 4):\n    print('3 x', i, '=', 3 * i)\n"},
    {"id": "fizzbuzz", "title": "FizzBuzz (1 to 15)", "topic": "Conditions", "difficulty": 3, "xp": 30,
     "prompt": "For 1..15 print Fizz for multiples of 3, Buzz for multiples of 5, FizzBuzz for both, else the number.",
     "starter": "# your loop\n",
     "expected": "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz",
     "hints": ["Check the 'both' case (divisible by 15) first.", "if i % 15 == 0 ... elif i % 3 == 0 ... elif i % 5 == 0 ... else"],
     "solution": "for i in range(1, 16):\n    if i % 15 == 0:\n        print('FizzBuzz')\n    elif i % 3 == 0:\n        print('Fizz')\n    elif i % 5 == 0:\n        print('Buzz')\n    else:\n        print(i)\n"},
    {"id": "linear-search", "title": "Linear search", "topic": "Searching", "difficulty": 3, "xp": 30,
     "prompt": "Find the index of `target` in `items` with a loop and print it (-1 if missing).",
     "starter": "items = [4, 9, 2, 7]\ntarget = 2\nfound = -1\n# loop here\n", "expected": "2",
     "hints": ["Loop with range(len(items)).", "if items[i] == target: found = i; break"],
     "solution": "items = [4, 9, 2, 7]\ntarget = 2\nfound = -1\nfor i in range(len(items)):\n    if items[i] == target:\n        found = i\n        break\nprint(found)\n"},
]

PREDICTIONS: list[dict] = [
    {"id": "p-arith", "title": "Arithmetic order", "topic": "Variables", "code": "x = 4\ny = x * 2 + 1\nprint(y)\n"},
    {"id": "p-str", "title": "Joining strings", "topic": "Strings", "code": "a = 'py'\nb = 'thon'\nprint(a + b)\nprint(len(a + b))\n"},
    {"id": "p-ifelse", "title": "Which branch?", "topic": "Conditions", "code": "n = 7\nif n > 10:\n    print('big')\nelif n > 5:\n    print('medium')\nelse:\n    print('small')\n"},
    {"id": "p-loop", "title": "Running total", "topic": "Loops", "code": "t = 0\nfor i in range(1, 4):\n    t = t + i\n    print(t)\n"},
    {"id": "p-while", "title": "While countdown", "topic": "Loops", "code": "n = 3\nwhile n > 0:\n    n = n - 1\nprint(n)\n"},
    {"id": "p-divmod", "title": "Division tricks", "topic": "Variables", "code": "print(7 // 2)\nprint(7 % 2)\nprint(7 / 2)\n"},
    {"id": "p-func", "title": "Function call", "topic": "Functions", "code": "def double(n):\n    return n * 2\nprint(double(double(3)))\n"},
    {"id": "p-list", "title": "List changes", "topic": "Lists", "code": "a = [1, 2]\nb = a\nb.append(3)\nprint(a)\n"},
    {"id": "p-dict", "title": "Dictionary lookup", "topic": "Dictionaries", "code": "d = {'x': 1}\nd['y'] = d['x'] + 1\nprint(d)\n"},
    {"id": "p-break", "title": "Break early", "topic": "Loops", "code": "for i in range(5):\n    if i == 3:\n        break\n    print(i)\n"},
]

PREDICTION_XP = 5


def public_challenge(c: dict) -> dict:
    return {k: c[k] for k in ("id", "title", "topic", "difficulty", "xp", "prompt", "starter", "hints")}


def norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in (s or "").strip().splitlines())


# --------------------------------------------------------------------------- progress store

class ProgressStore(Protocol):
    def load(self) -> dict: ...
    def save(self, data: dict) -> None: ...


def _empty() -> dict:
    return {"xp": 0, "challenges": {}, "predictions": {}, "active_days": [], "attempts": 0}


class JsonFileStore:
    """Single-user local store. Atomic writes. Swap for a PostgreSQL implementation of ProgressStore."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(settings.data_dir, "progress.json")
        self._lock = threading.Lock()

    def load(self) -> dict:
        with self._lock:
            try:
                with open(self.path, encoding="utf-8") as f:
                    return {**_empty(), **json.load(f)}
            except (FileNotFoundError, json.JSONDecodeError):
                return _empty()

    def save(self, data: dict) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)


def streak(active_days: list[str], today: dt.date) -> int:
    days = {dt.date.fromisoformat(d) for d in active_days}
    cur = today if today in days else today - dt.timedelta(days=1)
    n = 0
    while cur in days:
        n += 1
        cur -= dt.timedelta(days=1)
    return n


def summary(data: dict, today: Optional[dt.date] = None) -> dict:
    today = today or dt.date.today()
    topics: dict[str, dict] = {}
    for c in CHALLENGES:
        t = topics.setdefault(c["topic"], {"topic": c["topic"], "challenges_done": 0, "challenges_total": 0, "predictions_done": 0, "predictions_total": 0})
        t["challenges_total"] += 1
        t["challenges_done"] += c["id"] in data["challenges"]
    for p in PREDICTIONS:
        t = topics.setdefault(p["topic"], {"topic": p["topic"], "challenges_done": 0, "challenges_total": 0, "predictions_done": 0, "predictions_total": 0})
        t["predictions_total"] += 1
        t["predictions_done"] += bool(data["predictions"].get(p["id"], {}).get("correct"))
    done_topics = [t["topic"] for t in topics.values() if t["challenges_done"] or t["predictions_done"]]
    title = {c["id"]: c["title"] for c in CHALLENGES} | {p["id"]: p["title"] for p in PREDICTIONS}
    recent = sorted(
        [{"kind": "challenge", "id": k, "title": title.get(k, k), "at": v["at"]} for k, v in data["challenges"].items()] +
        [{"kind": "prediction", "id": k, "title": title.get(k, k), "at": v["first_correct_at"]} for k, v in data["predictions"].items() if v.get("correct")],
        key=lambda r: r["at"], reverse=True)[:8]
    return {"xp": data["xp"], "level": data["xp"] // 100 + 1, "xp_into_level": data["xp"] % 100,
            "streak": streak(data["active_days"], today),
            "challenges_completed": len(data["challenges"]), "challenges_total": len(CHALLENGES),
            "predictions_correct": sum(1 for v in data["predictions"].values() if v.get("correct")), "predictions_total": len(PREDICTIONS),
            "topics": list(topics.values()), "topics_learned": done_topics, "completed_ids": sorted(data["challenges"]),
            "predicted_ids": sorted(k for k, v in data["predictions"].items() if v.get("correct")),
            "recent": recent, "storage": "local JSON file (single user, development)"}


# --------------------------------------------------------------------------- checks

def _run(code: str) -> dict:
    return execute(code, "python", {})


def check_challenge(store: ProgressStore, cid: str, source: str, now: Optional[dt.datetime] = None) -> dict:
    ch = next((c for c in CHALLENGES if c["id"] == cid), None)
    if ch is None:
        return {"error": {"kind": "not_found", "message": f"Unknown challenge '{cid}'."}}
    now = now or dt.datetime.now()
    res = _run(source)
    actual = res.get("stdout", "")
    passed = res["execution_status"] == "completed" and norm(actual) == norm(ch["expected"])
    data = store.load()
    data["attempts"] += 1
    first_time = False
    awarded = 0
    if passed:
        if cid not in data["challenges"]:
            first_time = True
            awarded = ch["xp"]
            data["xp"] += awarded
            data["challenges"][cid] = {"at": now.isoformat(timespec="seconds"), "attempts": 1}
        if now.date().isoformat() not in data["active_days"]:
            data["active_days"].append(now.date().isoformat())
    store.save(data)
    out = {"passed": passed, "expected": ch["expected"], "stdout": actual, "execution_status": res["execution_status"],
           "error": res.get("error"), "xp_awarded": awarded, "first_time": first_time, "progress": summary(data, now.date())}
    if not passed:
        out["feedback"] = _feedback(res, ch["expected"])
    return out


def _feedback(res: dict, expected: str) -> str:
    if res["execution_status"] != "completed":
        e = res.get("error") or {}
        return f"Your code stopped with {e.get('type', 'an error')}: {e.get('message', '')}. Fix that first."
    got, want = norm(res.get("stdout", "")).splitlines(), norm(expected).splitlines()
    if not got:
        return "Your program printed nothing. Use print(...) to show the answer."
    if len(got) != len(want):
        return f"Expected {len(want)} line(s) of output but got {len(got)}."
    for i, (g, w) in enumerate(zip(got, want), 1):
        if g != w:
            return f"Output line {i} differs: expected {w!r}, got {g!r}."
    return "Output differs."


def check_prediction(store: ProgressStore, pid: str, prediction: str, now: Optional[dt.datetime] = None) -> dict:
    p = next((x for x in PREDICTIONS if x["id"] == pid), None)
    if p is None:
        return {"error": {"kind": "not_found", "message": f"Unknown exercise '{pid}'."}}
    now = now or dt.datetime.now()
    res = _run(p["code"])                       # the truth comes from really executing the snippet
    actual = res.get("stdout", "")
    correct = res["execution_status"] == "completed" and norm(prediction) == norm(actual)
    data = store.load()
    rec = data["predictions"].setdefault(pid, {"tries": 0, "correct": False})
    rec["tries"] += 1
    awarded = 0
    if correct and not rec["correct"]:
        rec["correct"] = True
        rec["first_correct_at"] = now.isoformat(timespec="seconds")
        awarded = PREDICTION_XP
        data["xp"] += awarded
    if correct and now.date().isoformat() not in data["active_days"]:
        data["active_days"].append(now.date().isoformat())
    store.save(data)
    return {"correct": correct, "actual": actual, "prediction": prediction, "xp_awarded": awarded, "progress": summary(data, now.date())}
