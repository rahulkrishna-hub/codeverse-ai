"""HTTP layer (Starlette + pydantic). FastAPI was not installable in the dev sandbox (PyPI blocked);
the handlers below are plain functions over ``app.services`` so porting to FastAPI is mechanical."""
from __future__ import annotations

import os
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app.adapters import REGISTRY
from app.config import settings
from app.services import ai_provider, explainer, flowchart, learning
from app.services.execution import execute


class ExecuteRequest(BaseModel):
    source_code: str = ""
    language: str = "python"
    execution_options: dict[str, Any] = Field(default_factory=dict)


class ExplainRequest(BaseModel):
    mode: str = "line"                       # line | error | program | simpler | ask
    language: str = "tanglish"               # explanation language: en | ta | tanglish
    source_code: str = ""
    event: Optional[dict] = None
    result: Optional[dict] = None
    question: str = ""


store = learning.JsonFileStore()


class ChallengeCheck(BaseModel):
    source_code: str = ""


class PredictionCheck(BaseModel):
    prediction: str = ""


class FlowRequest(BaseModel):
    source_code: str = ""


async def _body(request: Request, model):
    try:
        return model.model_validate(await request.json()), None
    except ValidationError as e:
        return None, JSONResponse({"error": {"kind": "validation", "message": str(e.errors()[0]["msg"])}}, 422)
    except Exception:
        return None, JSONResponse({"error": {"kind": "bad_json", "message": "Request body must be valid JSON."}}, 400)


async def health(request):
    return JSONResponse({"status": "ok", "sandbox": "subprocess-rlimit (local development only)"})


async def languages(request):
    return JSONResponse({"languages": [a.describe() for a in REGISTRY.values()]})


async def ai_status(request):
    return JSONResponse(ai_provider.status())


async def execute_ep(request):
    req, err = await _body(request, ExecuteRequest)
    if err:
        return err
    from starlette.concurrency import run_in_threadpool
    result = await run_in_threadpool(execute, req.source_code, req.language, req.execution_options)
    return JSONResponse(result)


async def explain_ep(request):
    req, err = await _body(request, ExplainRequest)
    if err:
        return err
    lang = req.language
    try:
        if req.mode == "line":
            if not req.event:
                return JSONResponse({"error": {"kind": "validation", "message": "event is required"}}, 422)
            return JSONResponse(explainer.explain_event(req.event, lang))
        if req.mode == "error":
            e = (req.result or {}).get("error") or (req.event or {}).get("error")
            if not e:
                return JSONResponse({"error": {"kind": "validation", "message": "No error to explain."}}, 422)
            return JSONResponse(explainer.explain_error(e, req.event, lang))
        if req.mode == "program":
            return JSONResponse(explainer.explain_program(req.source_code, req.result or {}, lang))
        if req.mode == "simpler":
            return JSONResponse(explainer.simpler_example(req.event, lang))
        if req.mode == "ask":
            if not req.question.strip():
                return JSONResponse({"error": {"kind": "validation", "message": "Type a question first."}}, 422)
            from starlette.concurrency import run_in_threadpool
            prov = ai_provider.get_provider()
            try:
                return JSONResponse(await run_in_threadpool(prov.ask, req.question, req.source_code, req.event, lang))
            except Exception as ex:   # LLM call failed -> say so, do not pretend
                fb = ai_provider.LocalFallbackProvider().ask(req.question, req.source_code, req.event, lang)
                fb["label"] += f" - the LLM call failed ({type(ex).__name__}), showing the local fallback"
                return JSONResponse(fb)
        return JSONResponse({"error": {"kind": "validation", "message": f"Unknown mode '{req.mode}'."}}, 422)
    except Exception as ex:
        return JSONResponse({"error": {"kind": "explain_failed", "message": f"{type(ex).__name__}: {ex}"}}, 500)


async def challenges_ep(request):
    return JSONResponse({"challenges": [learning.public_challenge(c) for c in learning.CHALLENGES]})


async def challenge_check_ep(request):
    req, err = await _body(request, ChallengeCheck)
    if err:
        return err
    from starlette.concurrency import run_in_threadpool
    out = await run_in_threadpool(learning.check_challenge, store, request.path_params["cid"], req.source_code)
    return JSONResponse(out, 200 if "passed" in out else 404)


async def predictions_ep(request):
    return JSONResponse({"exercises": [{k: p[k] for k in ("id", "title", "topic", "code")} for p in learning.PREDICTIONS], "xp_each": learning.PREDICTION_XP})


async def prediction_check_ep(request):
    req, err = await _body(request, PredictionCheck)
    if err:
        return err
    from starlette.concurrency import run_in_threadpool
    out = await run_in_threadpool(learning.check_prediction, store, request.path_params["pid"], req.prediction)
    return JSONResponse(out, 200 if "correct" in out else 404)


async def progress_ep(request):
    return JSONResponse(learning.summary(store.load()))


async def flowchart_ep(request):
    req, err = await _body(request, FlowRequest)
    if err:
        return err
    try:
        return JSONResponse(flowchart.build(req.source_code))
    except SyntaxError as e:
        return JSONResponse({"error": {"kind": "syntax_error", "message": f"SyntaxError: {e.msg}", "line": e.lineno}}, 422)


routes = [
    Route("/api/challenges", challenges_ep),
    Route("/api/challenges/{cid}/check", challenge_check_ep, methods=["POST"]),
    Route("/api/predictions", predictions_ep),
    Route("/api/predictions/{pid}/check", prediction_check_ep, methods=["POST"]),
    Route("/api/progress", progress_ep),
    Route("/api/flowchart", flowchart_ep, methods=["POST"]),
    Route("/api/health", health),
    Route("/api/languages", languages),
    Route("/api/ai/status", ai_status),
    Route("/api/execute", execute_ep, methods=["POST"]),
    Route("/api/explain", explain_ep, methods=["POST"]),
]
_dist = os.environ.get("CV_FRONTEND_DIST") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
if os.path.isdir(_dist):
    routes.append(Mount("/", app=StaticFiles(directory=_dist, html=True), name="web"))

app = Starlette(routes=routes, middleware=[Middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])])
