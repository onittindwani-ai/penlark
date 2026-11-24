"""The offline stand in for the model behind `build_llm`. It is plain rules and templates, NOT a language model.

It answers the three jobs Penlark gives a model. Each request starts with a line `[task:<name>]` and the data sits in marked blocks (`source=profile`,
`source=idea`). The answer is JSON in the shape a real model must also return:

    write_draft   {"variants": [{"label", "text"}]}               the fixed templates in `writers.py`, with brackets where a real fact is needed
    write_guide   {"guide": "<plain language voice guide>"}        the fixed rules in `guide.py` over the measured numbers
    find_ideas    {"ideas": [{"title", "quotes": [{"note_id", "quote"}]}]}   the plain idea finder in `ideas.py` over the notes block

A real model (`LLM_BACKEND=anthropic`) uses the same shapes, so the checks around it (voice match, house rules, the claims check, the second person approval)
do not change. Nothing here calls a network.
"""

from __future__ import annotations

import json
import re

from penlark import guide, ideas, writers
from sendora_core.llm import LLMResponse
from sendora_core.safety import UNTRUSTED_CLOSE, UNTRUSTED_OPEN


def blocks(prompt: str) -> dict[str, str]:
    """The data blocks of a prompt, by source name."""
    pat = re.escape(UNTRUSTED_OPEN) + r" source=([^\n]*)\n(.*?)\n" + re.escape(UNTRUSTED_CLOSE)
    return {m.group(1): m.group(2) for m in re.finditer(pat, prompt, re.S)}


def task_of(prompt: str) -> str:
    m = re.match(r"\[task:(\w+)\]", prompt)
    return m.group(1) if m else ""


def _json(text: str, default):
    try:
        return json.loads(text)
    except ValueError:
        return default


class OfflineBackend:
    """Same call shape as the real backends, so the whole product runs with no key and no network."""

    is_live = False
    supports_json_schema = False

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        task, data = task_of(prompt), blocks(prompt)
        out: dict = {}
        if task == "write_draft":
            profile, idea = _json(data.get("profile", "{}"), {}), _json(data.get("idea", "{}"), {})
            kind, n = str(idea.get("kind", "post")), int(idea.get("variants", 2) or 2)
            if profile.get("dims") and idea.get("title"):
                out = {"variants": [{"label": v["label"], "text": v["text"]} for v in writers.write(profile, {"title": idea["title"], "evidence": idea.get("evidence", [])}, kind, n)]}
            else:
                out = {"variants": []}
        elif task == "write_guide":
            profile = _json(data.get("profile", "{}"), {})
            out = {"guide": guide.offline_guide(profile, str(profile.get("name", "this author")))} if profile.get("dims") else {"guide": ""}
        elif task == "find_ideas":
            rows = _json(data.get("notes", "[]"), [])
            found = ideas.find_ideas([{"id": r[0], "kind": r[1], "text": r[2]} for r in rows if isinstance(r, list) and len(r) == 3])
            out = {"ideas": [{"title": i.title, "quotes": [{"note_id": e["note_id"], "quote": e["quote"]} for e in i.evidence]} for i in found[:8]]}
        text = json.dumps(out)
        return LLMResponse(text=text, input_tokens=len(prompt) // 4, output_tokens=len(text) // 4, model="offline-rules")
