"""Pluggable AI provider layer.

``get_provider()`` returns an object with ``.id``, ``.is_llm`` and ``ask(question, source, event, language)``.
Without ANTHROPIC_API_KEY the *local fallback* is used and every response says so
(``is_llm: false``). A response only claims ``is_llm: true`` if the HTTP call to the LLM API
actually succeeded. The Anthropic provider is implemented with stdlib ``urllib`` and has NOT been
exercised in the development sandbox (no API key / egress) - see README.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

from app.config import settings
from app.services import explainer


class LocalFallbackProvider:
    id = explainer.PROVIDER_ID
    is_llm = False

    def ask(self, question: str, source: str, event: Optional[dict], language: str) -> dict:
        lang = explainer._L(language)
        note = explainer._t(
            lang,
            "No LLM API key is configured, so free-form questions cannot be answered by an AI model. "
            "Here is the rule-based explanation of the current step instead.",
            "LLM API key அமைக்கப்படவில்லை, அதனால் கேள்விக்கு AI model பதில் சொல்ல முடியாது. அதற்குப் பதிலாக தற்போதைய படியின் விதி அடிப்படையிலான விளக்கம் இதோ.",
            "LLM API key set pannala, so un question-ku AI model pathil sollamudiyadhu. Adhukku badhila current step-oda rule-based vilakkam idhu.")
        base = explainer.explain_event(event, lang) if event else explainer.explain_program(source, {}, lang)
        base["sections"].insert(0, {"title": explainer._t(lang, "Note", "குறிப்பு", "Note"), "body": note})
        base["text"] = "\n\n".join(f"{s['title']}\n{s['body']}" for s in base["sections"])
        base["question"] = question
        return base


class AnthropicProvider:
    id = "anthropic"
    is_llm = True

    def ask(self, question: str, source: str, event: Optional[dict], language: str) -> dict:
        lang = explainer._L(language)
        ctx = {"line": event and event.get("line_number"), "source_line": event and event.get("source_line"),
               "variables_after": event and {k: v.get("repr") for k, v in event["variables_after"].items()},
               "stdout_delta": event and event.get("stdout_delta")}
        lang_name = {"en": "English", "ta": "Tamil", "tanglish": "Tanglish (Tamil written in English letters)"}[lang]
        body = {"model": settings.llm_model, "max_tokens": 700,
                "system": f"You are a patient programming tutor for complete beginners. Answer in {lang_name}. "
                          "Use ONLY the program and execution state given; do not invent values.",
                "messages": [{"role": "user", "content":
                              f"Program:\n{source}\n\nCurrent step state: {json.dumps(ctx)}\n\nQuestion: {question}"}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                                              "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:   # raises on failure -> caller reports it
            data = json.load(resp)
        text = "".join(p.get("text", "") for p in data.get("content", []))
        return {"provider": self.id, "is_llm": True, "language": lang, "label": f"LLM answer ({settings.llm_model})",
                "sections": [{"title": "Answer", "body": text}], "text": text, "question": question}


def get_provider():
    return AnthropicProvider() if settings.anthropic_api_key else LocalFallbackProvider()


def status() -> dict:
    p = get_provider()
    return {"provider": p.id, "is_llm": p.is_llm, "api_key_configured": bool(settings.anthropic_api_key)}
