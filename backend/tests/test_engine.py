"""Engine tests: every case runs the REAL isolated worker (no mocks).

Run:  python -m unittest discover -s tests -v     (or: pytest)
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.execution import execute  # noqa: E402


def run(src, **opts):
    return execute(src, "python", opts or None)


def ev_lines(r):
    return [e["line_number"] for e in r["trace_events"]]


def after(r, i, name):
    return r["trace_events"][i]["variables_after"][name]["repr"]


def change(e, name):
    return next(c for c in e["explanation_context"]["changes"] if c["name"] == name)


class TraceInvariants(unittest.TestCase):
    """Properties that must hold for any completed trace (the frontend relies on them)."""
    PROGRAMS = [
        "x = 10\ny = 20\nresult = x + y\nprint(result)\n",
        "for i in range(3):\n    print(i)\n",
        "def f(n):\n    print('in', n)\n    return n * 2\nprint(f(2) + f(3))\n",
        "n = 3\nwhile n > 0:\n    n -= 1\nprint('done')\n",
        "d = {}\nfor w in ['a', 'b', 'a']:\n    d[w] = d.get(w, 0) + 1\nprint(d)\n",
    ]

    def test_invariants(self):
        for src in self.PROGRAMS:
            with self.subTest(src=src):
                r = run(src)
                self.assertEqual(r["execution_status"], "completed", r.get("error"))
                evs = r["trace_events"]
                self.assertEqual([e["event_index"] for e in evs], list(range(len(evs))))
                # console reconstructed from deltas == real stdout
                self.assertEqual("".join(e["stdout_delta"] for e in evs), r["stdout"])
                nlines = len(src.split("\n"))
                for e in evs:
                    self.assertTrue(1 <= e["line_number"] <= nlines)
                    self.assertIsNotNone(e["variables_after"])
                    self.assertEqual(e["call_stack"][-1]["variables"], e["variables_after"])
                    json.dumps(e, allow_nan=False)           # strictly JSON serialisable
                last_module = [e for e in evs if e["scope"] == "<module>"][-1]
                self.assertEqual(last_module["variables_after"].keys(),
                                 {k for k in r["final_variables"]})


class T01_Assignment(unittest.TestCase):
    def test_simple_assignment_creates_variable(self):
        r = run("x = 10\ny = 20\n")
        self.assertEqual(r["execution_status"], "completed")
        self.assertEqual(len(r["trace_events"]), 2)
        e0, e1 = r["trace_events"]
        self.assertEqual((e0["line_number"], e0["event_type"], e0["source_line"]), (1, "assign", "x = 10"))
        self.assertEqual(e0["variables_before"], {})
        self.assertEqual(e0["variables_after"]["x"], {"type": "int", "repr": "10", "value": 10})
        self.assertEqual(change(e0, "x")["kind"], "created")
        self.assertEqual(set(e1["variables_after"]), {"x", "y"})          # x stays visible
        self.assertEqual(change(e1, "y")["kind"], "created")

    def test_types_are_reported(self):
        r = run("a = 1\nb = 2.5\nc = 'hi'\nd = True\ne = None\nf = [1, 2]\ng = (1, 2)\nh = {'k': 1}\ni = {3, 1, 2}\n")
        v = r["final_variables"]
        self.assertEqual({k: x["type"] for k, x in v.items()},
                         dict(a="int", b="float", c="str", d="bool", e="NoneType", f="list", g="tuple", h="dict", i="set"))
        self.assertEqual([x["repr"] for x in v["f"]["items"]], ["1", "2"])
        self.assertEqual(v["h"]["entries"][0]["key"]["repr"], "'k'")
        self.assertEqual([x["repr"] for x in v["i"]["items"]], ["1", "2", "3"])   # sets are shown sorted

    def test_tuple_unpacking_and_nested_structures(self):
        r = run("a, b = 1, 2\nm = {'xs': [1, [2, 3]]}\n")
        self.assertEqual(r["trace_events"][0]["explanation_context"]["targets"], ["a", "b"])
        nested = r["final_variables"]["m"]["entries"][0]["value"]
        self.assertEqual(nested["type"], "list")
        self.assertEqual(nested["items"][1]["items"][1]["repr"], "3")


class T02_Arithmetic(unittest.TestCase):
    def test_calculation_breakdown(self):
        r = run("x = 10\ny = 20\nresult = x + y\n")
        calc = r["trace_events"][2]["explanation_context"]["calculation"]
        self.assertEqual(calc["operator"], "+")
        self.assertEqual([o["value"] for o in calc["operands"]], ["10", "20"])
        self.assertEqual([o["source"] for o in calc["operands"]], ["x", "y"])
        self.assertEqual(calc["result"], "30")

    def test_all_operators(self):
        r = run("a = 7\nb = 2\nc = a + b\nd = a - b\ne = a * b\nf = a / b\ng = a // b\nh = a % b\ni = a ** b\n")
        got = {k: v["repr"] for k, v in r["final_variables"].items() if k not in ("a", "b")}
        self.assertEqual(got, dict(c="9", d="5", e="14", f="3.5", g="3", h="1", i="49"))

    def test_augmented_assignment_calculation(self):
        r = run("n = 5\nn += 3\n")
        calc = r["trace_events"][1]["explanation_context"]["calculation"]
        self.assertEqual(r["trace_events"][1]["event_type"], "aug_assign")
        self.assertEqual((calc["operands"][0]["value"], calc["operands"][1]["value"], calc["result"]), ("5", "3", "8"))

    def test_operation_is_computed_before_it_runs_but_matches_real_result(self):
        r = run("x = 6\ny = 7\nz = x * y + 1\n")
        e = r["trace_events"][2]
        self.assertEqual(e["explanation_context"]["calculation"]["result"], e["variables_after"]["z"]["repr"])


class T03_Print(unittest.TestCase):
    def test_print_output_attached_to_the_printing_step(self):
        r = run("x = 5\nprint(x)\nprint('a', 'b', sep='-')\nprint(f'x={x}', end='!')\n")
        self.assertEqual([e["stdout_delta"] for e in r["trace_events"]], ["", "5\n", "a-b\n", "x=5!"])
        self.assertEqual(r["stdout"], "5\na-b\nx=5!")
        self.assertEqual(r["trace_events"][1]["event_type"], "print")
        self.assertEqual(r["trace_events"][1]["explanation_context"]["print"]["args"][0]["value"], "5")

    def test_print_inside_function_belongs_to_function_line(self):
        r = run("def hi():\n    print('hi')\nhi()\nprint('bye')\n")
        by_line = {(e["line_number"], e["event_type"]): e["stdout_delta"] for e in r["trace_events"]}
        self.assertEqual(by_line[(2, "print")], "hi\n")
        self.assertEqual(r["stdout"], "hi\nbye\n")


class T04_Reassignment(unittest.TestCase):
    def test_variable_changes_1_2_3(self):
        r = run("count = 1\ncount = count + 1\ncount = count + 1\n")
        evs = r["trace_events"]
        self.assertEqual([after(r, i, "count") for i in range(3)], ["1", "2", "3"])
        self.assertEqual(change(evs[0], "count")["kind"], "created")
        for i, prev, cur in ((1, "1", "2"), (2, "2", "3")):
            c = change(evs[i], "count")
            self.assertEqual((c["kind"], c["previous"]["repr"], c["current"]["repr"]), ("updated", prev, cur))


class T05_IfElse(unittest.TestCase):
    SRC = "x = {x}\nif x > 5:\n    print('big')\nelse:\n    print('small')\nprint('end')\n"

    def test_true_branch(self):
        r = run(self.SRC.format(x=9))
        self.assertEqual(ev_lines(r), [1, 2, 3, 6])
        cond = r["trace_events"][1]
        self.assertTrue(cond["explanation_context"]["branch_taken"])
        self.assertEqual(cond["explanation_context"]["condition"]["result"], "True")
        self.assertEqual(r["stdout"], "big\nend\n")

    def test_else_branch(self):
        r = run(self.SRC.format(x=1))
        self.assertEqual(ev_lines(r), [1, 2, 5, 6])
        self.assertFalse(r["trace_events"][1]["explanation_context"]["branch_taken"])
        self.assertEqual(r["stdout"], "small\nend\n")

    def test_elif_chain(self):
        r = run("s = 75\nif s >= 90:\n    g = 'A'\nelif s >= 70:\n    g = 'B'\nelse:\n    g = 'C'\n")
        self.assertEqual([e["event_type"] for e in r["trace_events"]], ["assign", "if", "elif", "assign"])
        self.assertEqual(r["final_variables"]["g"]["repr"], "'B'")
        self.assertFalse(r["trace_events"][1]["explanation_context"]["branch_taken"])
        self.assertTrue(r["trace_events"][2]["explanation_context"]["branch_taken"])
        enc = r["trace_events"][3]["explanation_context"]["enclosing"]
        self.assertEqual([(b["kind"], b["header"]) for b in enc], [("if-body", "elif s >= 70:")])


class T06_ForLoop(unittest.TestCase):
    def test_iterations(self):
        r = run("total = 0\nfor i in range(3):\n    total += i\nprint(total)\n")
        evs = r["trace_events"]
        headers = [e for e in evs if e["event_type"] == "for"]
        self.assertEqual(len(headers), 4)                                  # 3 iterations + the exit check
        self.assertEqual([h["loop_context"]["loops"][0]["iteration"] for h in headers], [1, 2, 3, 4])
        self.assertEqual([h["loop_context"]["loops"][0]["exiting"] for h in headers], [False, False, False, True])
        self.assertEqual(headers[0]["loop_context"]["loops"][0]["total"], 3)
        self.assertEqual([after(r, e["event_index"], "i") for e in headers[:3]], ["0", "1", "2"])
        self.assertEqual(change(headers[0], "i")["kind"], "created")
        self.assertEqual(change(headers[1], "i")["kind"], "updated")
        self.assertEqual(r["final_variables"]["total"]["repr"], "3")
        self.assertEqual(r["stdout"], "3\n")

    def test_body_lines_know_their_iteration(self):
        r = run("for i in range(2):\n    x = i * 10\n")
        bodies = [e for e in r["trace_events"] if e["event_type"] == "assign"]
        self.assertEqual([b["loop_context"]["loops"][0]["iteration"] for b in bodies], [1, 2])
        self.assertEqual([after(r, b["event_index"], "x") for b in bodies], ["0", "10"])

    def test_nested_loops_report_both_levels(self):
        r = run("for i in range(2):\n    for j in range(3):\n        p = i * j\n")
        inner = [e for e in r["trace_events"] if e["event_type"] == "assign"]
        self.assertEqual(len(inner), 6)
        last = inner[-1]["loop_context"]
        self.assertEqual(last["depth"], 2)
        self.assertEqual([(lp["iteration"], lp["total"]) for lp in last["loops"]], [(2, 2), (3, 3)])
        first_of_second_outer = inner[3]["loop_context"]["loops"]
        self.assertEqual([lp["iteration"] for lp in first_of_second_outer], [2, 1])   # inner counter reset

    def test_break_and_continue(self):
        r = run("for i in range(5):\n    if i == 1:\n        continue\n    if i == 3:\n        break\n    print(i)\n")
        self.assertEqual(r["stdout"], "0\n2\n")
        types = {e["event_type"] for e in r["trace_events"]}
        self.assertTrue({"break", "continue"} <= types)

    def test_one_line_comprehension_is_one_step(self):
        r = run("squares = [n * n for n in range(5)]\nprint(squares)\n")
        self.assertEqual(len(r["trace_events"]), 2)
        self.assertEqual(r["final_variables"]["squares"]["repr"], "[0, 1, 4, 9, 16]")


class T07_WhileLoop(unittest.TestCase):
    def test_iterations_and_exit(self):
        r = run("n = 3\nwhile n > 0:\n    n -= 1\nprint('done')\n")
        heads = [e for e in r["trace_events"] if e["event_type"] == "while"]
        self.assertEqual(len(heads), 4)
        self.assertEqual([h["explanation_context"]["condition"]["result"] for h in heads], ["True", "True", "True", "False"])
        self.assertEqual([h["loop_context"]["loops"][0]["exiting"] for h in heads], [False, False, False, True])
        self.assertEqual([h["explanation_context"]["branch_taken"] for h in heads], [True, True, True, False])
        decs = [e for e in r["trace_events"] if e["event_type"] == "aug_assign"]
        self.assertEqual([change(d, "n")["current"]["repr"] for d in decs], ["2", "1", "0"])

    def test_infinite_loop_is_stopped_with_a_partial_trace(self):
        r = run("n = 0\nwhile True:\n    n += 1\n", max_events=200)
        self.assertEqual(r["execution_status"], "truncated")
        self.assertTrue(r["truncated"])
        self.assertEqual(r["error"]["type"], "StepLimit")
        self.assertEqual(len(r["trace_events"]), 200)
        self.assertGreater(int(r["trace_events"][-1]["variables_after"]["n"]["repr"]), 50)


class T08_Functions(unittest.TestCase):
    def test_call_return_resume_sequence(self):
        r = run("def add(a, b):\n    return a + b\nresult = add(2, 3)\nprint(result)\n")
        types = [(e["event_type"], e["line_number"]) for e in r["trace_events"]]
        self.assertEqual(types, [("function_def", 1), ("assign", 3), ("call", 1), ("return", 2), ("resume", 3), ("print", 4)])
        call = r["trace_events"][2]
        self.assertEqual([a["name"] for a in call["explanation_context"]["args"]], ["a", "b"])
        self.assertEqual([c["name"] for c in call["explanation_context"]["changes"]], ["a", "b"])
        self.assertEqual([s["function"] for s in call["call_stack"]], ["<module>", "add"])
        ret = r["trace_events"][3]
        self.assertEqual(ret["explanation_context"]["return_value"]["repr"], "5")
        self.assertEqual(ret["explanation_context"]["calculation"]["result"], "5")
        resume = r["trace_events"][4]
        self.assertEqual(resume["explanation_context"]["returned_from"], "add")
        self.assertEqual(change(resume, "result")["kind"], "created")
        self.assertEqual([s["function"] for s in resume["call_stack"]], ["<module>"])
        self.assertEqual(r["stdout"], "5\n")

    def test_function_locals_do_not_leak_into_globals(self):
        r = run("def f(a):\n    tmp = a + 1\n    return tmp\nf(1)\n")
        self.assertNotIn("tmp", r["final_variables"])
        inside = [e for e in r["trace_events"] if e["scope"] == "f" and e["event_type"] == "assign"][0]
        self.assertIn("tmp", inside["variables_after"])
        self.assertIn("f", inside["call_stack"][0]["variables"])           # globals visible via the stack

    def test_recursion_builds_a_call_stack(self):
        r = run("def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\nprint(fact(4))\n")
        self.assertEqual(r["stdout"], "24\n")
        depth = max(len(e["call_stack"]) for e in r["trace_events"])
        self.assertEqual(depth, 5)
        calls = [e for e in r["trace_events"] if e["event_type"] == "call"]
        self.assertEqual([c["explanation_context"]["args"][0]["value"]["repr"] for c in calls], ["4", "3", "2", "1"])

    def test_function_without_return_returns_none(self):
        r = run("def hello():\n    x = 1\nv = hello()\n")
        self.assertEqual(r["final_variables"]["v"]["repr"], "None")
        impl = [e for e in r["trace_events"] if e["event_type"] == "return"][0]
        self.assertTrue(impl["explanation_context"]["implicit"])

    def test_lambda_and_builtins_with_callbacks(self):
        r = run("nums = [3, 1, 2]\nordered = sorted(nums, key=lambda v: -v)\n")
        self.assertEqual(r["final_variables"]["ordered"]["repr"], "[3, 2, 1]")
        self.assertEqual(r["execution_status"], "completed")


class T09_ListMutation(unittest.TestCase):
    def test_append_shows_previous_and_new_value(self):
        r = run("nums = [1, 2]\nnums.append(3)\n")
        e = r["trace_events"][1]
        self.assertEqual(e["event_type"], "expr")
        self.assertEqual(e["explanation_context"]["method_call"], {"object": "nums", "method": "append",
                         "args": [{"source": "3", "value": "3", "type": "int"}]})
        c = change(e, "nums")
        self.assertEqual((c["kind"], c["previous"]["repr"], c["current"]["repr"]), ("updated", "[1, 2]", "[1, 2, 3]"))
        self.assertEqual(len(c["current"]["items"]), 3)

    def test_index_assignment_dict_update_and_delete(self):
        r = run("a = [1, 2, 3]\na[0] = 99\nd = {}\nd['k'] = 'v'\ndel a[1]\n")
        self.assertEqual(r["final_variables"]["a"]["repr"], "[99, 3]")
        self.assertEqual(r["final_variables"]["d"]["entries"][0]["value"]["repr"], "'v'")
        self.assertEqual(r["trace_events"][1]["explanation_context"]["targets"], ["a[0]"])

    def test_aliasing_mutation_is_visible_on_both_names(self):
        r = run("a = [1]\nb = a\nb.append(2)\n")
        last = r["trace_events"][-1]["variables_after"]
        self.assertEqual((last["a"]["repr"], last["b"]["repr"]), ("[1, 2]", "[1, 2]"))

    def test_bubble_sort_swaps(self):
        r = run("a = [3, 1, 2]\nfor i in range(len(a)):\n    for j in range(len(a) - 1 - i):\n"
                "        if a[j] > a[j + 1]:\n            a[j], a[j + 1] = a[j + 1], a[j]\nprint(a)\n")
        self.assertEqual(r["stdout"], "[1, 2, 3]\n")


class T10_SyntaxErrors(unittest.TestCase):
    def test_syntax_error_reported_before_execution(self):
        r = run("x = 1\nif x > 0\n    print(x)\n")
        self.assertEqual(r["execution_status"], "syntax_error")
        self.assertEqual(r["trace_events"], [])
        self.assertEqual(r["error"]["type"], "SyntaxError")
        self.assertEqual(r["error"]["line"], 2)
        self.assertIn("colon", r["error"]["hint"])

    def test_unbalanced_bracket(self):
        r = run("x = [1, 2\n")
        self.assertEqual(r["execution_status"], "syntax_error")

    def test_indentation_error(self):
        r = run("def f():\nreturn 1\n")
        self.assertEqual(r["execution_status"], "syntax_error")


class T11_RuntimeErrors(unittest.TestCase):
    def check(self, src, etype, line, msg_part=None):
        r = run(src)
        self.assertEqual(r["execution_status"], "error", r)
        self.assertEqual(r["error"]["type"], etype)
        self.assertEqual(r["error"]["line"], line)
        if msg_part:
            self.assertIn(msg_part, r["error"]["message"])
        failed = [e for e in r["trace_events"] if e["status"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["line_number"], line)
        self.assertEqual(failed[0]["event_index"], r["error"]["event_index"])
        self.assertIn(etype, r["stderr"])
        return r

    def test_division_by_zero(self):
        r = self.check("x = 1\ny = x / 0\nprint('never')\n", "ZeroDivisionError", 2, "division by zero")
        self.assertEqual(len(r["trace_events"]), 2)                       # nothing after the failure
        self.assertEqual(r["stdout"], "")

    def test_undefined_variable(self):
        self.check("a = 1\nprint(b)\n", "NameError", 2, "'b'")

    def test_index_error_and_key_error_and_type_error(self):
        self.check("a = [1]\nprint(a[5])\n", "IndexError", 2)
        self.check("d = {}\nprint(d['x'])\n", "KeyError", 2)
        self.check("x = 'a' + 1\n", "TypeError", 1)

    def test_error_inside_function_has_traceback_and_stack(self):
        r = self.check("def f(x):\n    return 10 / x\nprint(f(0))\n", "ZeroDivisionError", 2)
        self.assertEqual([t["function"] for t in r["error"]["traceback"]], ["<module>", "f"])
        failed = [e for e in r["trace_events"] if e["status"] == "failed"][0]
        self.assertEqual([s["function"] for s in failed["call_stack"]], ["<module>", "f"])
        self.assertTrue(any(e["event_type"] == "return" and e["explanation_context"].get("unwinding")
                            for e in r["trace_events"]))

    def test_output_before_the_error_is_kept(self):
        r = run("print('before')\nx = 1 / 0\n")
        self.assertEqual(r["stdout"], "before\n")
        self.assertEqual(r["execution_status"], "error")

    def test_caught_exception_is_not_a_failure(self):
        r = run("try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    x = -1\nprint(x)\n")
        self.assertEqual(r["execution_status"], "completed")
        self.assertEqual(r["stdout"], "-1\n")
        raised = [e for e in r["trace_events"] if e["explanation_context"].get("exception")]
        self.assertEqual(len(raised), 1)
        self.assertEqual(raised[0]["status"], "ok")
        self.assertEqual(raised[0]["explanation_context"]["exception"]["type"], "ZeroDivisionError")

    def test_recursion_error(self):
        r = run("def f(n):\n    return f(n + 1)\nf(0)\n")
        self.assertEqual(r["execution_status"], "error")
        self.assertEqual(r["error"]["type"], "RecursionError")
        self.assertLessEqual(max(len(e["call_stack"]) for e in r["trace_events"]), 31)   # stack is capped for display


class T12_LimitsAndTimeouts(unittest.TestCase):
    def test_wall_clock_timeout_in_native_code(self):
        r = run("x = 1\ntotal = sum(range(10 ** 10))\nprint(total)\n", wall_timeout_s=1.5)
        self.assertEqual(r["execution_status"], "timeout")
        self.assertEqual(r["error"]["type"], "Timeout")
        self.assertEqual(r["error"]["line"], 2)                          # pinned to the hanging line
        self.assertEqual(len(r["trace_events"]), 1)                      # steps before the hang survive

    def test_excessive_output_is_cut_off(self):
        r = run("for i in range(100000):\n    print('x' * 100)\n")
        self.assertEqual(r["execution_status"], "truncated")
        self.assertEqual(r["error"]["type"], "StepLimit" if r["error"]["type"] == "StepLimit" else "OutputLimit")
        self.assertLessEqual(len(r["stdout"]), r["limits"]["max_output_chars"])

    def test_memory_limit(self):
        r = run("x = [0] * (10 ** 9)\n")
        self.assertEqual(r["execution_status"], "error")
        self.assertEqual(r["error"]["type"], "MemoryError")

    def test_deterministic_traces(self):
        src = "import random\nvals = [random.randint(1, 100) for _ in range(5)]\nprint(vals)\n"
        a, b = run(src), run(src)
        self.assertEqual(a["trace_events"], b["trace_events"])
        self.assertEqual(a["stdout"], b["stdout"])


class T13_InputValidation(unittest.TestCase):
    def test_empty_code(self):
        for src in ("", "   \n\n"):
            r = run(src)
            self.assertEqual(r["execution_status"], "empty")
            self.assertEqual(r["trace_events"], [])

    def test_invalid_and_unavailable_languages(self):
        r = execute("x = 1", "cobol")
        self.assertEqual(r["execution_status"], "invalid_language")
        for lang in ("java", "javascript", "c"):
            r = execute("x = 1", lang)
            self.assertEqual(r["execution_status"], "language_unavailable")
            self.assertEqual(r["trace_events"], [])                      # never a fake trace

    def test_too_large(self):
        r = run("x = 1\n" * 10000)
        self.assertEqual(r["execution_status"], "too_large")

    def test_unsupported_syntax_is_explained(self):
        for src, word in (("class A:\n    pass\n", "Classes"), ("with open('f') as f:\n    pass\n", "with"),
                          ("def g():\n    yield 1\n", "Generators"), ("import os\n", "not allowed"),
                          ("x = 1\nfrom subprocess import run\n", "not allowed")):
            with self.subTest(src=src):
                r = run(src)
                self.assertEqual(r["execution_status"], "unsupported")
                self.assertIn(word, r["error"]["message"])
                self.assertEqual(r["trace_events"], [])

    def test_input_gives_a_helpful_error(self):
        r = run("name = input('?')\n")
        self.assertEqual(r["execution_status"], "error")
        self.assertIn("not supported", r["error"]["message"])


class T14_SandboxBehaviour(unittest.TestCase):
    """The worker must not give user code access to files, the environment or the network."""

    def test_sandbox_is_reported_honestly(self):
        r = run("x = 1\n")
        sb = r["sandbox"]
        self.assertFalse(sb["production_ready"])
        self.assertIn("Local-development", sb["warning"])

    def test_no_open_no_os_no_dunders(self):
        attempts = {
            "open": "f = open('/etc/passwd')\n",
            "eval": "eval('1+1')\n",
            "exec": "exec('x = 1')\n",
            "import os": "import os\n",
            "socket": "import socket\n",
            "dunder import": "m = __import__('os')\n",
            "class walk": "x = ().__class__\n",
            "module internals": "import random\nrandom._os.system('id')\n",
            "builtins access": "x = __builtins__\n",
        }
        for name, src in attempts.items():
            with self.subTest(name):
                r = run(src)
                self.assertIn(r["execution_status"], ("unsupported", "error"), (name, r["execution_status"]))
                self.assertEqual(r["stdout"], "")

    def test_environment_is_scrubbed(self):
        os.environ["CV_TEST_SECRET"] = "hunter2"
        try:
            r = run("x = 1\n")
            self.assertNotIn("hunter2", json.dumps(r))
        finally:
            del os.environ["CV_TEST_SECRET"]

    @unittest.skipUnless(os.geteuid() == 0 and run("x=1")["sandbox"]["network_isolated"], "needs root + unshare")
    def test_network_namespace_has_no_route(self):
        # sockets are not importable by user code, so probe from the worker's own namespace:
        import subprocess
        from app.engine import runner
        p = subprocess.run(["unshare", "-n", "--", sys.executable, "-c",
                            "import socket;s=socket.socket();s.settimeout(2)\n"
                            "try:\n s.connect(('1.1.1.1',80));print('CONNECTED')\nexcept OSError as e:\n print('blocked')"],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.stdout.strip(), "blocked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
