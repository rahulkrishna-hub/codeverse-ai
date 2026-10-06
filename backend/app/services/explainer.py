"""Local, rule-based explainer (the AI Tutor fallback).

Every sentence is derived from the ACTUAL trace event (statement kind, operand values,
variable changes, loop iteration, branch taken ...). It is NOT an LLM, and every response
says so (``provider = "local-fallback"``, ``is_llm = False``).

Languages: "en" (English), "ta" (Tamil), "tanglish" (Tamil written in English letters).
"""
from __future__ import annotations

import ast
from typing import Any, Optional

LANGS = ("en", "ta", "tanglish")
PROVIDER_ID = "local-fallback"

SECTION_TITLES = {
    "what": {"en": "What this line does", "ta": "இந்த வரி என்ன செய்கிறது", "tanglish": "Indha line enna pannudhu"},
    "why": {"en": "Why it runs now", "ta": "ஏன் இப்போது இயங்குகிறது", "tanglish": "Yen ippo run aagudhu"},
    "vars": {"en": "Variables involved", "ta": "தொடர்புடைய variables", "tanglish": "Related variables"},
    "takeaway": {"en": "What to remember", "ta": "நினைவில் வைக்க", "tanglish": "Ninaivula vachukka"},
}

OPS = {
    "+": {"en": "adds", "ta": "கூட்டி", "tanglish": "add panni"},
    "-": {"en": "subtracts", "ta": "கழித்து", "tanglish": "subtract panni"},
    "*": {"en": "multiplies", "ta": "பெருக்கி", "tanglish": "multiply panni"},
    "/": {"en": "divides", "ta": "வகுத்து", "tanglish": "divide panni"},
    "//": {"en": "floor-divides", "ta": "முழுமையாக வகுத்து", "tanglish": "floor-divide panni"},
    "%": {"en": "takes the remainder of", "ta": "மீதியை எடுத்து", "tanglish": "remainder eduthu"},
    "**": {"en": "raises to the power", "ta": "அடுக்கு கணக்கிட்டு", "tanglish": "power calculate panni"},
}


def _L(lang: str) -> str:
    return lang if lang in LANGS else "en"


def _t(lang: str, en: str, ta: str, tg: str) -> str:
    return {"en": en, "ta": ta, "tanglish": tg}[_L(lang)]


def _r(d: Optional[dict]) -> str:
    return d["repr"] if d else "?"


def _code(s: str) -> str:
    return f"`{s}`"


# --------------------------------------------------------------------------- per-event facts

def _loop_info(event: dict) -> Optional[dict]:
    lc = event.get("loop_context")
    if not lc or not lc.get("loops"):
        return None
    return lc["loops"][-1]


def _values_line(event: dict, lang: str) -> list[str]:
    ctx = event["explanation_context"]
    out = []
    for c in ctx.get("changes", []):
        name, cur, prev = c["name"], c.get("current"), c.get("previous")
        if c["kind"] == "created":
            out.append(_t(lang, f"{_code(name)} is new: it now holds {_code(_r(cur))} (type {cur['type']}).",
                          f"{_code(name)} புதியது: இப்போது {_code(_r(cur))} (வகை {cur['type']}) உள்ளது.",
                          f"{_code(name)} pudhusu: ippo {_code(_r(cur))} (type {cur['type']}) irukku."))
        elif c["kind"] == "updated":
            out.append(_t(lang, f"{_code(name)} changed from {_code(_r(prev))} to {_code(_r(cur))}.",
                          f"{_code(name)} {_code(_r(prev))} இலிருந்து {_code(_r(cur))} ஆக மாறியது.",
                          f"{_code(name)} {_code(_r(prev))}-la irundhu {_code(_r(cur))}-ku maarichu."))
        else:
            out.append(_t(lang, f"{_code(name)} was deleted.", f"{_code(name)} நீக்கப்பட்டது.",
                          f"{_code(name)} delete aayiduchu."))
    return out


def _involved(event: dict, lang: str) -> list[str]:
    """Variables read by this statement, with their values BEFORE it ran."""
    ctx = event["explanation_context"]
    before = event.get("variables_before", {})
    names: list[str] = []
    calc = ctx.get("calculation") or {}
    for o in calc.get("operands", []):
        if o["source"].isidentifier() and o["source"] in before:
            names.append(o["source"])
    for a in (ctx.get("print") or {}).get("args", []):
        if a["source"].isidentifier() and a["source"] in before:
            names.append(a["source"])
    cond = ctx.get("condition") or {}
    for o in cond.get("operands", []):
        if o["source"].isidentifier() and o["source"] in before:
            names.append(o["source"])
    mc = ctx.get("method_call")
    if mc and mc["object"].isidentifier() and mc["object"] in before:
        names.append(mc["object"])
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(_t(lang, f"{_code(n)} is {_code(_r(before[n]))} right now.",
                          f"{_code(n)} இப்போது {_code(_r(before[n]))}.",
                          f"{_code(n)} ippo {_code(_r(before[n]))}."))
    return out


def _what(event: dict, lang: str) -> str:
    ctx = event["explanation_context"]
    et = event["event_type"]
    src = event["source_line"].strip()
    changes = ctx.get("changes", [])
    targets = ctx.get("targets") or []
    calc = ctx.get("calculation") or {}
    first_target = targets[0] if targets else "?"

    if et == "assign":
        created = [c for c in changes if c["kind"] == "created"]
        verb_new = bool(created) and any(c["name"] == first_target for c in created)
        if calc.get("operator") and all(o.get("value") is not None for o in calc.get("operands", [])) and calc.get("result"):
            a, b = calc["operands"][0], calc["operands"][-1]
            opw = OPS.get(calc["operator"], {})
            if len(calc["operands"]) == 2:
                if a["source"].isidentifier() and b["source"].isidentifier() and calc["operator"] in OPS:
                    return _t(lang,
                              f"{_code(a['source'])} is {a['value']} and {_code(b['source'])} is {b['value']}. Python {opw['en']} them: "
                              f"{a['value']} {calc['operator']} {b['value']} = {calc['result']}, and stores {calc['result']} in {_code(first_target)}.",
                              f"{_code(a['source'])} மதிப்பு {a['value']}, {_code(b['source'])} மதிப்பு {b['value']}. Python இரண்டையும் {opw['ta']} "
                              f"{a['value']} {calc['operator']} {b['value']} = {calc['result']} என்று {_code(first_target)} இல் சேமிக்கிறது.",
                              f"{_code(a['source'])} oda value {a['value']}, {_code(b['source'])} oda value {b['value']}. Python rendu values-ah "
                              f"{opw['tanglish']} {calc['result']} nu {_code(first_target)} variable-la store pannuthu.")
                return _t(lang,
                          f"Python first works out {_code(calc['expression'])}: {a['value']} {calc['operator']} {b['value']} = {calc['result']}. "
                          f"Then it stores {calc['result']} in {_code(first_target)}.",
                          f"Python முதலில் {_code(calc['expression'])} கணக்கிடுகிறது: {a['value']} {calc['operator']} {b['value']} = {calc['result']}. "
                          f"பிறகு {calc['result']} ஐ {_code(first_target)} இல் சேமிக்கிறது.",
                          f"Python first {_code(calc['expression'])} calculate pannum: {a['value']} {calc['operator']} {b['value']} = {calc['result']}. "
                          f"Apparam {calc['result']}-ah {_code(first_target)}-la store pannum.")
        val = ctx.get("value_source", "?")
        cur = next((c["current"] for c in changes if c["name"] == first_target), None)
        shown = _r(cur) if cur else val
        if len(targets) > 1:
            return _t(lang, f"Python unpacks the values and assigns them to {', '.join(_code(t) for t in targets)}.",
                      f"Python மதிப்புகளைப் பிரித்து {', '.join(_code(t) for t in targets)} க்கு ஒதுக்குகிறது.",
                      f"Python values-ah pirichu {', '.join(_code(t) for t in targets)}-ku assign pannudhu.")
        if verb_new:
            return _t(lang, f"This creates a new variable {_code(first_target)} and stores {_code(shown)} in it.",
                      f"இது {_code(first_target)} என்ற புதிய variable உருவாக்கி அதில் {_code(shown)} சேமிக்கிறது.",
                      f"Idhu {_code(first_target)} nu oru pudhu variable create panni, adhula {_code(shown)} store pannudhu.")
        prev = next((c["previous"] for c in changes if c["name"] == first_target and c.get("previous")), None)
        if prev:
            return _t(lang, f"{_code(first_target)} already existed. Its value changes from {_code(_r(prev))} to {_code(shown)}.",
                      f"{_code(first_target)} ஏற்கனவே இருந்தது. அதன் மதிப்பு {_code(_r(prev))} இலிருந்து {_code(shown)} ஆக மாறுகிறது.",
                      f"{_code(first_target)} munnadiye irundhuchu. Adhoda value {_code(_r(prev))}-la irundhu {_code(shown)}-ku maarudhu.")
        return _t(lang, f"Stores the result of {_code(val)} in {_code(first_target)}.",
                  f"{_code(val)} இன் முடிவை {_code(first_target)} இல் சேமிக்கிறது.",
                  f"{_code(val)} oda result-ah {_code(first_target)}-la store pannudhu.")

    if et == "aug_assign":
        op = ctx.get("operator", "+=")
        ch = changes[0] if changes else None
        if ch and ch.get("previous") and ch.get("current"):
            return _t(lang, f"{_code(src)} updates {_code(first_target)} in place: {_r(ch['previous'])} becomes {_r(ch['current'])}.",
                      f"{_code(src)} {_code(first_target)} ஐ மாற்றுகிறது: {_r(ch['previous'])} இப்போது {_r(ch['current'])}.",
                      f"{_code(src)} {_code(first_target)}-ah update pannudhu: {_r(ch['previous'])} ippo {_r(ch['current'])} aagudhu.")
        return _t(lang, f"{_code(src)} updates {_code(first_target)} using {op}.",
                  f"{_code(src)} {_code(first_target)} ஐ {op} பயன்படுத்தி மாற்றுகிறது.",
                  f"{_code(src)} {_code(first_target)}-ah {op} vachu update pannudhu.")

    if et == "print":
        text = event.get("stdout_delta", "")
        shown = text.rstrip("\n")
        return _t(lang, f"print shows a value on the console. Output: {_code(shown)}.",
                  f"print console இல் மதிப்பைக் காட்டுகிறது. வெளியீடு: {_code(shown)}.",
                  f"print console-la value-ah kaattudhu. Output: {_code(shown)}.")

    if et in ("expr",):
        mc = ctx.get("method_call")
        ch = changes[0] if changes else None
        if mc:
            if ch and ch.get("previous") and ch.get("current"):
                return _t(lang, f"{_code(mc['object'] + '.' + mc['method'] + '(...)')} changes the data inside {_code(mc['object'])}: "
                          f"{_r(ch['previous'])} becomes {_r(ch['current'])}.",
                          f"{_code(mc['object'] + '.' + mc['method'] + '(...)')} {_code(mc['object'])} உள்ளிருக்கும் தரவை மாற்றுகிறது: "
                          f"{_r(ch['previous'])} இப்போது {_r(ch['current'])}.",
                          f"{_code(mc['object'] + '.' + mc['method'] + '(...)')} {_code(mc['object'])}-kulla irukkura data-vai maathudhu: "
                          f"{_r(ch['previous'])} ippo {_r(ch['current'])}.")
            return _t(lang, f"Calls the method {_code(mc['method'])} on {_code(mc['object'])}.",
                      f"{_code(mc['object'])} மீது {_code(mc['method'])} method ஐ அழைக்கிறது.",
                      f"{_code(mc['object'])} mela {_code(mc['method'])} method-ah call pannudhu.")
        return _t(lang, f"Evaluates {_code(src)}.", f"{_code(src)} ஐ மதிப்பிடுகிறது.", f"{_code(src)}-ah evaluate pannudhu.")

    if et in ("if", "elif"):
        cond = ctx.get("condition") or {}
        expr = cond.get("expression", src)
        res = cond.get("result") or cond.get("truth")
        taken = ctx.get("branch_taken")
        ops = cond.get("operands") or []
        shown = ""
        if len(ops) == 2 and all(o.get("value") is not None for o in ops):
            shown = f" ({ops[0]['value']} {cond.get('operator')} {ops[1]['value']})"
        if taken is True:
            return _t(lang, f"Python checks {_code(expr)}{shown}. It is True, so the indented block below runs.",
                      f"Python {_code(expr)}{shown} ஐ சரிபார்க்கிறது. அது True, எனவே கீழே உள்ள block இயங்கும்.",
                      f"Python {_code(expr)}{shown} check pannudhu. Adhu True, so keezha irukkura block run aagum.")
        if taken is False:
            return _t(lang, f"Python checks {_code(expr)}{shown}. It is False, so this block is skipped.",
                      f"Python {_code(expr)}{shown} ஐ சரிபார்க்கிறது. அது False, எனவே இந்த block தவிர்க்கப்படும்.",
                      f"Python {_code(expr)}{shown} check pannudhu. Adhu False, so indha block skip aagum.")
        return _t(lang, f"Python checks the condition {_code(expr)}.", f"Python {_code(expr)} நிபந்தனையை சரிபார்க்கிறது.",
                  f"Python {_code(expr)} condition-ah check pannudhu.")

    if et == "for":
        li = _loop_info(event) or {}
        var = li.get("variable") or "the loop variable"
        it = li.get("iteration", 1)
        tot = li.get("total")
        if li.get("exiting"):
            return _t(lang, "There are no items left, so the loop ends and Python moves on after it.",
                      "மீதம் எந்த உருப்படியும் இல்லை, எனவே loop முடிந்து Python அடுத்த வரிக்குச் செல்கிறது.",
                      "Innum items illa, so loop mudinjidhu; Python adutha line-ku pogudhu.")
        cur = next((c["current"] for c in changes if c["name"] == li.get("variable")), None)
        of = f" of {tot}" if tot else ""
        of_ta = f" / {tot}" if tot else ""
        return _t(lang, f"Loop round {it}{of}: {_code(var)} takes the next item{(' = ' + _r(cur)) if cur else ''}, then the loop body runs.",
                  f"Loop சுற்று {it}{of_ta}: {_code(var)} அடுத்த உருப்படியை{(' = ' + _r(cur)) if cur else ''} பெறுகிறது, பிறகு loop body இயங்கும்.",
                  f"Loop round {it}{of_ta}: {_code(var)} adutha item-ah{(' = ' + _r(cur)) if cur else ''} edukkudhu, apparam loop body run aagum.")

    if et == "while":
        cond = ctx.get("condition") or {}
        expr = cond.get("expression", src)
        taken = ctx.get("branch_taken")
        li = _loop_info(event) or {}
        it = li.get("iteration", 1)
        if taken is False:
            return _t(lang, f"Python checks {_code(expr)} again. It is False, so the while loop stops.",
                      f"Python {_code(expr)} ஐ மீண்டும் சரிபார்க்கிறது. அது False, எனவே while loop நிற்கிறது.",
                      f"Python {_code(expr)}-ah thirumba check pannudhu. Adhu False, so while loop nikkudhu.")
        return _t(lang, f"Check number {it}: is {_code(expr)} True? Yes, so the loop body runs once more.",
                  f"சரிபார்ப்பு {it}: {_code(expr)} True ஆ? ஆம், எனவே loop body மீண்டும் இயங்கும்.",
                  f"Check {it}: {_code(expr)} True-aa? Aama, so loop body innoru thadava run aagum.")

    if et == "function_def":
        fn = ctx.get("function", {})
        params = ", ".join(fn.get("params", []))
        return _t(lang, f"Defines a function named {_code(fn.get('name', '?'))}({params}). Nothing inside it runs yet - it only runs when the function is called.",
                  f"{_code(fn.get('name', '?'))}({params}) என்ற function ஐ வரையறுக்கிறது. உள்ளே உள்ள code இன்னும் இயங்காது - function அழைக்கப்படும்போதுதான் இயங்கும்.",
                  f"{_code(fn.get('name', '?'))}({params}) nu oru function define pannudhu. Ulla irukkura code ippo run aagadhu - function call pannumbodhu dhaan run aagum.")

    if et == "call":
        fn = ctx.get("function", {})
        args = ", ".join(f"{a['name']}={_r(a['value'])}" for a in ctx.get("args", []))
        return _t(lang, f"The function {_code(fn.get('name', '?'))} starts. Its parameters receive the values: {args or 'none'}.",
                  f"{_code(fn.get('name', '?'))} function தொடங்குகிறது. அதன் parameters மதிப்புகளைப் பெறுகின்றன: {args or 'எதுவுமில்லை'}.",
                  f"{_code(fn.get('name', '?'))} function start aagudhu. Adhoda parameters-ku values kedaikkudhu: {args or 'onnum illa'}.")

    if et == "return":
        rv = ctx.get("return_value")
        name = (ctx.get("function") or {}).get("name") or (event.get("scope") or "function")
        if ctx.get("unwinding"):
            return _t(lang, f"The function {_code(name)} stops early because an error happened inside it.",
                      f"உள்ளே பிழை ஏற்பட்டதால் {_code(name)} function இடையிலேயே நிற்கிறது.",
                      f"Ulla error vandhadhaala {_code(name)} function naduvulaye nikkudhu.")
        calc = ctx.get("calculation") or {}
        extra = ""
        if calc.get("result") and calc.get("operands"):
            extra = f" ({calc['expression']} = {calc['result']})"
        if ctx.get("implicit"):
            return _t(lang, f"The function reached its end without a return statement, so it gives back {_code(_r(rv))} (None).",
                      f"return இல்லாமல் function முடிந்தது, எனவே {_code(_r(rv))} (None) திருப்பித் தருகிறது.",
                      f"return illama function mudinjidhu, so {_code(_r(rv))} (None) thirumba tharudhu.")
        return _t(lang, f"{_code('return')} sends the value {_code(_r(rv))}{extra} back to the line that called the function.",
                  f"{_code('return')} மதிப்பு {_code(_r(rv))}{extra} ஐ function ஐ அழைத்த வரிக்குத் திருப்பி அனுப்புகிறது.",
                  f"{_code('return')} value {_code(_r(rv))}{extra}-ah function-ah call panna line-ku thirumba anuppudhu.")

    if et == "resume":
        rv = ctx.get("returned_from")
        val = _r(ctx.get("return_value"))
        ch = changes[0] if changes else None
        tail = ""
        if ch and ch["kind"] in ("created", "updated"):
            tail = _t(lang, f" The line finishes by storing {_code(_r(ch['current']))} in {_code(ch['name'])}.",
                      f" வரி {_code(_r(ch['current']))} ஐ {_code(ch['name'])} இல் சேமித்து முடிகிறது.",
                      f" Line mudiyum bodhu {_code(_r(ch['current']))}-ah {_code(ch['name'])}-la store pannudhu.")
        elif event.get("stdout_delta"):
            tail = _t(lang, f" The line then prints {_code(event['stdout_delta'].rstrip(chr(10)))}.",
                      f" பிறகு {_code(event['stdout_delta'].rstrip(chr(10)))} ஐ அச்சிடுகிறது.",
                      f" Apparam {_code(event['stdout_delta'].rstrip(chr(10)))}-ah print pannudhu.")
        return _t(lang, f"Back in the calling line: {_code(str(rv) + '(...)')} gave back {_code(val)}.{tail}",
                  f"அழைத்த வரிக்குத் திரும்பியது: {_code(str(rv) + '(...)')} {_code(val)} ஐ திருப்பித் தந்தது.{tail}",
                  f"Call panna line-ku thirumbi vandhaachu: {_code(str(rv) + '(...)')} {_code(val)} thirumba kuduthuchu.{tail}")

    simple = {
        "break": ("Leaves the loop immediately.", "Loop ஐ உடனே விட்டு வெளியேறுகிறது.", "Loop-ah ukkaarndhu udane veliya varudhu."),
        "continue": ("Skips the rest of this round and starts the next one.", "இந்த சுற்றின் மீதியைத் தவிர்த்து அடுத்த சுற்றைத் தொடங்குகிறது.", "Indha round-oda meedhi-ah skip panni adutha round start pannudhu."),
        "pass": ("Does nothing; it is a placeholder.", "எதுவும் செய்யாது; இது ஒரு placeholder.", "Onnum pannaadhu; idhu oru placeholder."),
        "import": ("Loads a module so its tools can be used.", "ஒரு module ஐ ஏற்றுகிறது.", "Oru module-ah load pannudhu, adhoda tools use pannalaam."),
    }
    if et in simple:
        return _t(lang, *simple[et])
    if et == "assert":
        return _t(lang, f"Checks that {_code((ctx.get('condition') or {}).get('expression', src))} is True; if not, the program stops.",
                  "நிபந்தனை True என சரிபார்க்கிறது; இல்லையெனில் program நிற்கும்.",
                  "Condition True-nu check pannudhu; illana program nikkum.")
    if et == "delete":
        return _t(lang, f"Deletes {', '.join(_code(t) for t in targets)}.", f"{', '.join(_code(t) for t in targets)} ஐ நீக்குகிறது.",
                  f"{', '.join(_code(t) for t in targets)}-ah delete pannudhu.")
    return _t(lang, f"Runs {_code(src)}.", f"{_code(src)} ஐ இயக்குகிறது.", f"{_code(src)}-ah run pannudhu.")


def _why(event: dict, lang: str) -> str:
    ctx = event["explanation_context"]
    et = event["event_type"]
    parts: list[str] = []
    enc = ctx.get("enclosing") or []
    li = _loop_info(event)
    idx = event["event_index"]
    if et == "call":
        cl = ctx.get("caller_line")
        parts.append(_t(lang, f"Line {cl} called this function, so Python jumped here.",
                        f"{cl}-ஆம் வரி இந்த function ஐ அழைத்ததால் Python இங்கு வந்தது.",
                        f"Line {cl} indha function-ah call pannadhaala Python inga vandhuchu."))
    elif et == "resume":
        parts.append(_t(lang, "The function finished, so Python returns to the line that called it.",
                        "Function முடிந்தது, எனவே அதை அழைத்த வரிக்கு Python திரும்புகிறது.",
                        "Function mudinjidhu, so adhai call panna line-ku Python thirumbudhu."))
    elif idx == 0:
        parts.append(_t(lang, "Python starts at the first line and runs one line at a time, top to bottom.",
                        "Python முதல் வரியிலிருந்து தொடங்கி மேலிருந்து கீழாக ஒவ்வொரு வரியாக இயக்குகிறது.",
                        "Python first line-la irundhu start panni, mela irundhu keezha oru line oru line-ah run pannum."))
    else:
        parts.append(_t(lang, "Python runs lines in order, so this line comes right after the previous step.",
                        "Python வரிகளை வரிசையாக இயக்குகிறது, எனவே இது முந்தைய படிக்குப் பிறகு வருகிறது.",
                        "Python lines-ah order-la run pannum, so idhu munnadi step-kku appuram varudhu."))
    for b in enc:
        k = b["kind"]
        if k == "if-body":
            parts.append(_t(lang, f"It is inside {_code(b['header'])} (line {b['line']}), and that condition was True.",
                            f"இது {_code(b['header'])} ({b['line']}-ஆம் வரி) உள்ளே உள்ளது, அந்த நிபந்தனை True ஆக இருந்தது.",
                            f"Idhu {_code(b['header'])} (line {b['line']}) kulla irukku, andha condition True-aa irundhuchu."))
        elif k == "else-body":
            parts.append(_t(lang, f"It is in the else part of {_code(b['header'])} (line {b['line']}), which runs when that condition is False.",
                            f"இது {_code(b['header'])} ({b['line']}-ஆம் வரி) இன் else பகுதியில் உள்ளது; நிபந்தனை False ஆனபோது இயங்கும்.",
                            f"Idhu {_code(b['header'])} (line {b['line']}) oda else part-la irukku; condition False-na run aagum."))
        elif k in ("for-body", "while-body") and li and not li.get("is_header"):
            n = li.get("iteration")
            tot = f" of {li['total']}" if li.get("total") else ""
            parts.append(_t(lang, f"It is inside the loop {_code(b['header'])}; this is round {n}{tot}.",
                            f"இது {_code(b['header'])} loop உள்ளே உள்ளது; இது சுற்று {n}{(' / ' + str(li['total'])) if li.get('total') else ''}.",
                            f"Idhu {_code(b['header'])} loop-kulla irukku; idhu round {n}{(' / ' + str(li['total'])) if li.get('total') else ''}."))
        elif k == "function" and et not in ("call",):
            parts.append(_t(lang, f"It is part of the function {_code(b.get('name', ''))}.",
                            f"இது {_code(b.get('name', ''))} function இன் பகுதி.",
                            f"Idhu {_code(b.get('name', ''))} function-oda part."))
    if ctx.get("calls_function"):
        parts.append(_t(lang, f"This line calls {_code(ctx['calls_function'])}, so the next steps happen inside that function.",
                        f"இந்த வரி {_code(ctx['calls_function'])} ஐ அழைக்கிறது, எனவே அடுத்த படிகள் அந்த function உள்ளே நடக்கும்.",
                        f"Indha line {_code(ctx['calls_function'])}-ah call pannudhu, so adutha steps andha function-kulla nadakkum."))
    return " ".join(parts)


def _takeaway(event: dict, lang: str) -> str:
    et = event["event_type"]
    ctx = event["explanation_context"]
    ch = ctx.get("changes", [])
    updated = any(c["kind"] == "updated" for c in ch)
    created = any(c["kind"] == "created" for c in ch)
    table = {
        "assign": (("A variable is a named box. Assigning again to an existing name replaces what is inside.",
                    "Variable என்பது பெயரிடப்பட்ட பெட்டி. இருக்கும் பெயருக்கு மீண்டும் ஒதுக்கினால் உள்ளே இருப்பது மாறும்.",
                    "Variable-nu sonna per vachcha pettti maadhiri. Irukkura per-ku thirumba assign panna ulla irukkura value maarum.")
                   if updated and not created else
                   ("Use = to create a variable. Python works out the right side first, then stores it on the left.",
                    "= பயன்படுத்தி variable உருவாக்கலாம். Python வலப்பக்கத்தை முதலில் கணக்கிட்டு இடப்பக்கத்தில் சேமிக்கும்.",
                    "= use panni variable create pannalaam. Python right side-ah first calculate panni left-la store pannum.")),
        "aug_assign": ("x += 1 is a short way to write x = x + 1.", "x += 1 என்பது x = x + 1 இன் சுருக்கம்.", "x += 1 nu na x = x + 1 oda short form."),
        "print": ("print is how a program shows results to a person.", "program முடிவுகளை காட்ட print பயன்படும்.", "program result-ah kaattuvadharku print use pannuvom."),
        "expr": ("Some operations change a value in place, like list.append().", "list.append() போன்றவை மதிப்பை அதே இடத்தில் மாற்றும்.", "list.append() maadhiri sila operations value-ah adhe idathula maathum."),
        "if": ("if lets a program choose: the block runs only when the condition is True.", "if நிபந்தனை True ஆனால் மட்டுமே block இயங்கும்.", "if-la condition True-na mattum dhaan block run aagum."),
        "elif": ("elif is checked only when the earlier conditions were False.", "முந்தைய நிபந்தனைகள் False ஆனால் மட்டுமே elif சரிபார்க்கப்படும்.", "Munnadi irukkura conditions False-na mattum dhaan elif check aagum."),
        "for": ("A for loop repeats its body once for each item.", "for loop ஒவ்வொரு உருப்படிக்கும் body ஐ ஒருமுறை இயக்கும்.", "for loop ovvoru item-kum body-ah oru thadava run pannum."),
        "while": ("A while loop repeats as long as its condition stays True - make sure something changes it!", "நிபந்தனை True ஆக இருக்கும் வரை while loop திரும்பத் திரும்ப இயங்கும் - அதை மாற்ற ஏதாவது இருக்க வேண்டும்!", "Condition True-aa irukkura varaikkum while loop thirumba thirumba run aagum - adhai maathura onnu irukkanum!"),
        "function_def": ("def only saves the recipe. The code inside runs when you call the function.", "def செய்முறையை மட்டும் சேமிக்கிறது. function ஐ அழைக்கும்போது உள்ளே உள்ள code இயங்கும்.", "def recipe-ah mattum save pannum. Function-ah call pannumbodhu ulla irukkura code run aagum."),
        "call": ("Each call gets its own fresh set of variables, separate from the caller.", "ஒவ்வொரு அழைப்புக்கும் தனி variables உண்டு.", "Ovvoru call-kum thani variables irukkum."),
        "return": ("return ends the function and hands a value back to the caller.", "return function ஐ முடித்து மதிப்பை அழைத்தவருக்குத் தரும்.", "return function-ah mudichu value-ah call panninavarukku tharum."),
        "resume": ("The returned value replaces the function call in the line, then the line finishes.", "திரும்பிய மதிப்பு function அழைப்பின் இடத்தில் வந்து வரி முடியும்.", "Thirumbi vandha value function call irundha idathula vandhu line mudiyum."),
        "break": ("break jumps out of the whole loop.", "break முழு loop ஐயும் விட்டு வெளியேறும்.", "break motha loop-ayum vittu veliya poidum."),
        "continue": ("continue skips to the next round of the loop.", "continue அடுத்த சுற்றுக்குச் செல்லும்.", "continue adutha round-ku poidum."),
    }
    if et in table:
        return _t(lang, *table[et])
    return ""


def explain_event(event: dict, language: str = "en") -> dict:
    lang = _L(language)
    secs = [("what", _what(event, lang)), ("why", _why(event, lang))]
    vars_lines = _involved(event, lang) + _values_line(event, lang)
    if vars_lines:
        secs.append(("vars", "\n".join(vars_lines)))
    tk = _takeaway(event, lang)
    if tk:
        secs.append(("takeaway", tk))
    if event.get("error") and event.get("status") == "failed":
        secs.append(("what", explain_error({"type": event["error"]["type"], "message": event["error"]["message"],
                                            "line": event["line_number"]}, event, lang)["text"]))
    return _pack(lang, [(SECTION_TITLES[k][lang], body) for k, body in secs if body])


def _pack(lang: str, sections: list[tuple[str, str]], extra: Optional[dict] = None) -> dict:
    out = {"provider": PROVIDER_ID, "is_llm": False, "language": lang,
           "label": _t(lang, "Local rule-based explanation (not an AI model)",
                       "உள்ளூர் விதி அடிப்படையிலான விளக்கம் (AI model அல்ல)",
                       "Local rule-based explanation (AI model illa)"),
           "sections": [{"title": t, "body": b} for t, b in sections],
           "text": "\n\n".join(f"{t}\n{b}" for t, b in sections)}
    if extra:
        out.update(extra)
    return out


# --------------------------------------------------------------------------- errors

def _name_from_msg(msg: str) -> str:
    import re
    m = re.search(r"'([^']+)'", msg or "")
    return m.group(1) if m else "?"


def explain_error(error: dict, event: Optional[dict], language: str = "en") -> dict:
    lang = _L(language)
    et = error.get("type", "Error")
    msg = error.get("message", "")
    line = error.get("line")
    at = _t(lang, f" (line {line})" if line else "", f" ({line}-ஆம் வரி)" if line else "", f" (line {line})" if line else "")
    name = _name_from_msg(msg)
    T = {
        "ZeroDivisionError": (
            ("You tried to divide a number by zero, which is impossible in maths and in Python.",
             "ஒரு எண்ணை பூஜ்யத்தால் வகுக்க முயன்றீர்கள்; இது கணிதத்திலும் Python இலும் சாத்தியமில்லை.",
             "Oru number-ah zero-vaala divide panna try pannirukkeenga; idhu maths-layum Python-layum mudiyaadhu."),
            ("Check the value on the right of / (or // or %). Make sure it can never be 0, or test it with an if first.",
             "/ (அல்லது // , %) க்கு வலப்பக்கம் உள்ள மதிப்பைப் பாருங்கள். அது 0 ஆகாதபடி பார்த்துக் கொள்ளுங்கள் அல்லது முதலில் if மூலம் சோதியுங்கள்.",
             "/ (illa // , %) right side irukkura value-ah paarunga. Adhu 0 aagama paathukonga, illana mudhalla if vachu check pannunga.")),
        "NameError": (
            (f"Python does not know the name {_code(name)}. It was never created before this line.",
             f"Python க்கு {_code(name)} என்ற பெயர் தெரியவில்லை. இந்த வரிக்கு முன் அது உருவாக்கப்படவில்லை.",
             f"Python-kku {_code(name)} nu per theriyala. Indha line-ku munnadi adhu create aagala."),
            ("Check the spelling (capital letters matter) and make sure the variable is assigned on an earlier line, in the same place where you use it.",
             "எழுத்துப்பிழை (பெரிய/சிறிய எழுத்து) உள்ளதா எனப் பாருங்கள்; மேலும் அந்த variable முன்பே ஒதுக்கப்பட்டுள்ளதா எனப் பாருங்கள்.",
             "Spelling (capital/small letters) check pannunga; adhu munnadiye assign aagi irukkaanu paarunga.")),
        "TypeError": (
            ("Python cannot combine or use these values this way (for example adding text to a number).",
             "இந்த மதிப்புகளை இப்படிப் பயன்படுத்த Python ஆல் முடியாது (எ.கா. உரையுடன் எண்ணைக் கூட்டுவது).",
             "Indha values-ah ippadi use panna Python-ala mudiyaadhu (example: text-oda number-ah add panradhu)."),
            ("Check the types of the values. Use int(), float() or str() to convert, or an f-string to mix text and numbers.",
             "மதிப்புகளின் வகையைப் பாருங்கள். int(), float(), str() மூலம் மாற்றுங்கள் அல்லது f-string பயன்படுத்துங்கள்.",
             "Values-oda type-ah paarunga. int(), float(), str() vachu convert pannunga, illana f-string use pannunga.")),
        "IndexError": (
            ("You asked for a position that does not exist in the list. Positions start at 0 and the last valid one is len(list) - 1.",
             "பட்டியலில் இல்லாத இடத்தைக் கேட்டுள்ளீர்கள். இடங்கள் 0 இல் தொடங்கி கடைசி சரியான இடம் len(list) - 1.",
             "List-la illaadha position-ah kettirukkeenga. Positions 0-la start aagum, last valid position len(list) - 1."),
            ("Print len(your_list) and check your index. A loop like for i in range(len(x)) stays inside the limits.",
             "len(உங்கள்_பட்டியல்) ஐ அச்சிட்டு index ஐ சரிபாருங்கள். for i in range(len(x)) போன்ற loop எல்லைக்குள் இருக்கும்.",
             "len(list) print panni index-ah check pannunga. for i in range(len(x)) maadhiri loop limit-kulla irukkum.")),
        "KeyError": (
            (f"The dictionary has no key {_code(name)}.",
             f"Dictionary இல் {_code(name)} என்ற key இல்லை.",
             f"Dictionary-la {_code(name)} nu key illa."),
            ("Check the spelling of the key, or use d.get(key, default) which does not crash when the key is missing.",
             "key எழுத்துப்பிழையைப் பாருங்கள் அல்லது d.get(key, default) பயன்படுத்துங்கள்.",
             "Key spelling check pannunga, illana d.get(key, default) use pannunga - key illanalum crash aagaadhu.")),
        "ValueError": (
            ("The value has the right type but an unacceptable content (for example int('abc')).",
             "மதிப்பின் வகை சரி, ஆனால் உள்ளடக்கம் ஏற்றதல்ல (எ.கா. int('abc')).",
             "Value-oda type sari, aana content seri illa (example: int('abc'))."),
            ("Check what is being converted or passed in.", "எது மாற்றப்படுகிறது / அனுப்பப்படுகிறது என்று பாருங்கள்.", "Edhu convert aagudhu / anuppapaduthu-nu paarunga.")),
        "AttributeError": (
            ("This value does not have the method or attribute you asked for.",
             "இந்த மதிப்பில் நீங்கள் கேட்ட method அல்லது attribute இல்லை.",
             "Indha value-kku nee kaetta method / attribute illa."),
            ("Check the type of the value and the spelling of the method name.", "மதிப்பின் வகையையும் method பெயர் எழுத்துப்பிழையையும் பாருங்கள்.", "Value type-ayum method per spelling-ayum paarunga.")),
        "RecursionError": (
            ("A function kept calling itself without ever stopping.",
             "ஒரு function நிற்காமல் தன்னையே அழைத்துக் கொண்டே இருந்தது.",
             "Oru function nikkaama thannaiye call pannitte irundhuchu."),
            ("Add a base case - an if that returns without calling the function again - and make each call move closer to it.",
             "base case ஐச் சேருங்கள் - மீண்டும் அழைக்காமல் return செய்யும் if - ஒவ்வொரு அழைப்பும் அதை நெருங்க வேண்டும்.",
             "Base case add pannunga - function-ah thirumba call pannaama return panra if - ovvoru call-um adhai nerungi pogunum.")),
        "StepLimit": (
            ("The program ran so many steps that the visualizer stopped it. This usually means an infinite loop.",
             "program பல படிகள் இயங்கியதால் visualizer நிறுத்தியது. இது பொதுவாக முடிவில்லா loop ஆகும்.",
             "Program romba steps run aanadhaala visualizer nirutthiduchu. Idhu pothuva infinite loop."),
            ("Look at the loop condition: does something inside the loop change it so it eventually becomes False?",
             "loop நிபந்தனையைப் பாருங்கள்: loop உள்ளே அதை False ஆக்கும் மாற்றம் உள்ளதா?",
             "Loop condition-ah paarunga: loop-kulla adhai False aakkura maatram irukka?")),
        "Timeout": (
            ("The program took too long and was stopped.", "program அதிக நேரம் எடுத்ததால் நிறுத்தப்பட்டது.", "Program romba neram eduthadhaala nirutthapattadhu."),
            ("Look for an infinite loop or a calculation with a huge number.", "முடிவில்லா loop அல்லது மிகப்பெரிய கணக்கீட்டைத் தேடுங்கள்.", "Infinite loop illa romba perusu calculation irukkaanu paarunga.")),
        "OutputLimit": (
            ("The program printed more text than the visualizer allows.", "program அனுமதிக்கப்பட்டதை விட அதிக உரையை அச்சிட்டது.", "Program allow pannadhai vida adhigama text print pannuchu."),
            ("Print less, or check that a loop is not printing forever.", "குறைவாக அச்சிடுங்கள் அல்லது loop முடிவில்லாமல் அச்சிடவில்லை என்று பாருங்கள்.", "Kammiyaa print pannunga, illa loop mudiva illama print pannudhaanu paarunga.")),
        "MemoryError": (
            ("The program tried to use more memory than allowed.", "அனுமதிக்கப்பட்டதை விட அதிக memory பயன்படுத்த முயன்றது.", "Allow pannadhai vida adhiga memory use panna try pannuchu."),
            ("Use smaller numbers/sizes.", "சிறிய எண்கள்/அளவுகளைப் பயன்படுத்துங்கள்.", "Chinna numbers/sizes use pannunga.")),
        "SyntaxError": (
            ("Python could not read this line; the code is not written in a valid way.",
             "Python இந்த வரியைப் படிக்க முடியவில்லை; code சரியான வடிவத்தில் இல்லை.",
             "Python indha line-ah padikka mudiyala; code sariyaana format-la illa."),
            (error.get("hint") or "Check for a missing colon, bracket or quote on or just above this line.",
             error.get("hint") or "இந்த வரியிலோ அதற்கு மேலோ colon, bracket அல்லது quote விடுபட்டுள்ளதா எனப் பாருங்கள்.",
             error.get("hint") or "Indha line-layo adhukku mela-layo colon, bracket, quote miss aagi irukkaanu paarunga.")),
        "UnsupportedSyntax": (
            (msg, msg, msg),
            ("This first release of CodeVerse supports a defined subset of Python; see the supported list in the app.",
             "CodeVerse இன் இந்த முதல் வெளியீடு Python இன் ஒரு குறிப்பிட்ட பகுதியை ஆதரிக்கிறது; ஆதரிக்கப்படுவதைப் பாருங்கள்.",
             "CodeVerse-oda indha first release Python-oda oru subset-ah mattum support pannudhu; supported list-ah paarunga.")),
    }
    what, fix = T.get(et, ((f"Python raised {et}: {msg}", f"Python {et} பிழையை எழுப்பியது: {msg}", f"Python {et} error kudutthuchu: {msg}"),
                           ("Read the message carefully and check the values used on this line.",
                            "செய்தியை கவனமாகப் படித்து இந்த வரியில் பயன்படுத்தப்பட்ட மதிப்புகளைப் பாருங்கள்.",
                            "Message-ah nalla padichu indha line-la use pannina values-ah paarunga.")))
    head = _t(lang, f"{et}{at}: ", f"{et}{at}: ", f"{et}{at}: ")
    sections = [(_t(lang, "What went wrong", "என்ன தவறு நடந்தது", "Enna thappu nadandhuchu"), head + _t(lang, *what)),
                (_t(lang, "How to fix it", "எப்படி சரி செய்வது", "Eppadi sari pannradhu"), _t(lang, *fix))]
    if event and event.get("variables_before"):
        vs = ", ".join(f"{k}={v['repr']}" for k, v in list(event["variables_before"].items())[:8] if v["type"] != "function")
        if vs:
            sections.append((_t(lang, "Variables just before the error", "பிழைக்கு முன் variables", "Error-ku munnadi variables"), vs))
    r = _pack(lang, sections)
    r["text"] = "\n\n".join(f"{t}\n{b}" for t, b in sections)
    return r


# --------------------------------------------------------------------------- whole program

def explain_program(source: str, result: dict, language: str = "en") -> dict:
    lang = _L(language)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return explain_error({"type": "SyntaxError", "message": "invalid syntax"}, None, lang)
    counts = {"assign": 0, "loops": 0, "ifs": 0, "funcs": 0, "prints": 0, "calls": 0}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            counts["assign"] += 1
        elif isinstance(n, (ast.For, ast.While)):
            counts["loops"] += 1
        elif isinstance(n, ast.If):
            counts["ifs"] += 1
        elif isinstance(n, ast.FunctionDef):
            counts["funcs"] += 1
        elif isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name) and n.func.id == "print":
                counts["prints"] += 1
            else:
                counts["calls"] += 1
    status = result.get("execution_status")
    steps = len(result.get("trace_events", []))
    fv = {k: v["repr"] for k, v in (result.get("final_variables") or {}).items() if v.get("type") != "function"}
    parts = []
    bits_en, bits_ta, bits_tg = [], [], []
    if counts["assign"]:
        bits_en.append(f"{counts['assign']} assignment(s)"); bits_ta.append(f"{counts['assign']} ஒதுக்கீடு(கள்)"); bits_tg.append(f"{counts['assign']} assignment")
    if counts["funcs"]:
        bits_en.append(f"{counts['funcs']} function(s)"); bits_ta.append(f"{counts['funcs']} function(கள்)"); bits_tg.append(f"{counts['funcs']} function")
    if counts["ifs"]:
        bits_en.append(f"{counts['ifs']} decision(s) (if)"); bits_ta.append(f"{counts['ifs']} முடிவு(கள்) (if)"); bits_tg.append(f"{counts['ifs']} decision (if)")
    if counts["loops"]:
        bits_en.append(f"{counts['loops']} loop(s)"); bits_ta.append(f"{counts['loops']} loop(கள்)"); bits_tg.append(f"{counts['loops']} loop")
    if counts["prints"]:
        bits_en.append(f"{counts['prints']} print(s)"); bits_ta.append(f"{counts['prints']} print(கள்)"); bits_tg.append(f"{counts['prints']} print")
    overview = _t(lang, "This program contains " + (", ".join(bits_en) or "a few statements") + ".",
                  "இந்த program இல் " + (", ".join(bits_ta) or "சில கூற்றுகள்") + " உள்ளன.",
                  "Indha program-la " + (", ".join(bits_tg) or "konjam statements") + " irukku.")
    parts.append((_t(lang, "Overview", "சுருக்கம்", "Overview"), overview))
    run_txt = _t(lang, f"When it ran, Python executed {steps} step(s) and finished with status '{status}'.",
                 f"இயங்கியபோது Python {steps} படி(கள்) இயக்கி '{status}' நிலையில் முடிந்தது.",
                 f"Run aana pothu Python {steps} step run panni '{status}' status-la mudinjidhu.")
    parts.append((_t(lang, "What happened", "என்ன நடந்தது", "Enna nadandhuchu"), run_txt))
    out = (result.get("stdout") or "").rstrip("\n")
    if out:
        parts.append((_t(lang, "Output", "வெளியீடு", "Output"), out))
    if fv:
        parts.append((_t(lang, "Final variables", "இறுதி variables", "Final variables"), ", ".join(f"{k} = {v}" for k, v in fv.items())))
    if result.get("error") and status in ("error", "timeout", "truncated"):
        parts.append((_t(lang, "Problem", "பிரச்சனை", "Problem"), explain_error(result["error"], None, lang)["text"]))
    return _pack(lang, parts)


# --------------------------------------------------------------------------- simpler example

SIMPLER = {
    "assign": ("name = 'Asha'\nage = 12\nprint(name, age)", "Two variables, then print them."),
    "aug_assign": ("score = 0\nscore += 5\nscore += 5\nprint(score)", "A counter that grows by 5 each time."),
    "print": ("print('Hello')\nprint(2 + 3)", "print shows text and results."),
    "expr": ("fruits = []\nfruits.append('apple')\nfruits.append('mango')\nprint(fruits)", "A list that grows with append."),
    "if": ("temp = 35\nif temp > 30:\n    print('hot')\nelse:\n    print('not hot')", "One decision with two outcomes."),
    "elif": ("n = 0\nif n > 0:\n    print('positive')\nelif n < 0:\n    print('negative')\nelse:\n    print('zero')", "Three outcomes."),
    "for": ("for i in range(3):\n    print('round', i)", "A loop that repeats three times."),
    "while": ("n = 3\nwhile n > 0:\n    print(n)\n    n -= 1", "A countdown that stops at 0."),
    "function_def": ("def greet(name):\n    return 'Hi ' + name\nprint(greet('Ravi'))", "A tiny function that is called once."),
    "call": ("def double(x):\n    return x * 2\nprint(double(4))", "Call a function with one value."),
    "return": ("def double(x):\n    return x * 2\nprint(double(4))", "return hands a value back."),
    "resume": ("def double(x):\n    return x * 2\nanswer = double(4)\nprint(answer)", "The returned value is stored."),
    "default": ("x = 1\ny = 2\nprint(x + y)", "The simplest program: two variables and print."),
}


def simpler_example(event: Optional[dict], language: str = "en") -> dict:
    lang = _L(language)
    kind = (event or {}).get("event_type", "default")
    code, desc = SIMPLER.get(kind, SIMPLER["default"])
    intro = _t(lang, "Here is a smaller program that uses the same idea. Load it and press Run:",
               "அதே யோசனையைப் பயன்படுத்தும் சிறிய program இதோ. அதை ஏற்றி Run அழுத்துங்கள்:",
               "Adhey idea use panra chinna program idhu. Load panni Run press pannunga:")
    r = _pack(lang, [(_t(lang, "A simpler example", "எளிய எடுத்துக்காட்டு", "Simple example"), f"{intro}\n\n{desc}")],
              {"example_code": code})
    return r
