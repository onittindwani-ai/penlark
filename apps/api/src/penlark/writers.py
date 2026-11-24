"""Draft writers. The offline stand in fills templates from the evidence and the voice profile. It is NOT a language model.

It cannot invent: wherever a real example, number or story is needed it leaves a bracket such as [YOUR EXAMPLE], and the claims check flags the draft until
a person replaces the bracket with a real fact linked to a source note. The live path (LLM_BACKEND=anthropic, DRAFT_WRITER=model) is `model_tasks.write_variants`: it goes through the shared wrapper and every variant is re scored by code. It has never run against the real service: UNVERIFIED.
"""

from __future__ import annotations

import re

KINDS = ("post", "script", "email", "newsletter")
OFFLINE_LABEL = "Offline stand in: fills a template from your evidence and your voice numbers. It is not a language model. Fill the brackets with your own real facts."


def register(profile: dict) -> str:
    d = {k: v["centre"] for k, v in profile["dims"].items()}
    if d["formality"] > 1.5 or (d["contractions"] < 0.8 and d["sentence_length"] > 17):
        return "formal"
    if d["sentence_length"] < 10:
        return "terse"
    if d["questions"] > 0.1 or d["exclamations"] > 0.08 or d["you_address"] > 4:
        return "warm"
    return "plain"


def _clean_quote(q: str) -> str:
    q = re.sub(r"^(?:hi,?|hello,?|honest question:|great post\.|love this\.)\s*", "", q.strip(), flags=re.I)
    return q.strip()


def contract(text: str, on: bool) -> str:
    pairs = [("do not", "don't"), ("is not", "isn't"), ("it is", "it's"), ("we are", "we're"), ("you are", "you're"), ("I am", "I'm"), ("cannot", "can't"), ("that is", "that's"), ("let us", "let's")]
    for long, short in pairs:
        if on:
            text = re.sub(rf"\b{long}\b", short, text)
            text = re.sub(rf"\b{long.capitalize()}\b", short.capitalize(), text)
        else:
            text = re.sub(rf"\b{short}\b", long, text, flags=re.I) if short.lower() != "can't" else text.replace("can't", "cannot").replace("Can't", "Cannot")
    return text


TEMPLATES = {
    "terse": {
        "post": ["{qp}\n\nGood question. Here is the short answer.\n\n[YOUR ANSWER IN ONE LINE]\n\n[YOUR REAL EXAMPLE]\n\nDo that first. Skip the rest.", "Someone asked: {qp}\n\n[YOUR ANSWER]\n\n[ONE REAL NUMBER FROM YOUR NOTES]\n\nSimple. Try it."],
        "script": ["Question I keep getting: {qp}\n\nShort answer: [YOUR ANSWER].\n\nExample: [YOUR REAL EXAMPLE].\n\nThat is it. Go do it."],
        "email": ["Subject: {topic}\n\nHi [NAME],\n\nYou asked: {qp}\n\n[YOUR ANSWER]\n\nIf that is not clear, tell me. I will fix it.\n\n[YOUR NAME]"],
        "newsletter": ["This week: {topic}.\n\nThe question: {qp}\n\n[YOUR ANSWER]\n\n[YOUR REAL EXAMPLE]\n\nNext week: [YOUR NEXT TOPIC]."],
    },
    "warm": {
        "post": ["Have you ever wondered about this? {qp} I hear it so often, and honestly, it's a good one.\n\nHere's how I think about it: [YOUR ANSWER IN YOUR OWN WORDS].\n\nFor example, [YOUR REAL EXAMPLE]. Does that help? Tell me what you'd try!", "Let's talk about something many of you have asked me: {qp}\n\nIt's okay if this feels confusing! [YOUR GENTLE EXPLANATION].\n\nWhat would you like me to cover next?"],
        "script": ["Hi everyone! Today I want to answer a question that keeps coming up: {qp}\n\nLet's take it step by step. [YOUR FIRST STEP]. Then [YOUR SECOND STEP].\n\nHave you tried this? Let me know!"],
        "email": ["Subject: {topic}\n\nDear [NAME],\n\nThank you for asking: {qp} It's a really good question!\n\n[YOUR ANSWER IN YOUR OWN WORDS]\n\nPlease tell me if you'd like to talk it through.\n\nWarmly,\n[YOUR NAME]"],
        "newsletter": ["Hello, friends!\n\nThis month's question: {qp} I'd love to explore it together.\n\n[YOUR ANSWER IN YOUR OWN WORDS]\n\nWhat's one thing you could try this week?"],
    },
    "formal": {
        "post": ["A question is frequently raised in our engagements: {qp}\n\nIn our experience, the matter is best approached as follows. [YOUR ANSWER, STATED IN FULL SENTENCES].\n\nWe would recommend that the reader consider [YOUR RECOMMENDATION], having regard to [YOUR REAL EXAMPLE]."],
        "script": ["Good morning. It is a question we are frequently asked: {qp}\n\nIt should be noted that there are two considerations. First, [YOUR FIRST POINT]. Second, [YOUR SECOND POINT]."],
        "email": ["Subject: {topic}\n\nDear [NAME],\n\nThank you for your enquiry regarding the following matter: {qp}\n\n[YOUR ANSWER, STATED IN FULL SENTENCES]\n\nShould you wish to discuss the matter further, I should be pleased to arrange a call.\n\nYours sincerely,\n[YOUR NAME]"],
        "newsletter": ["In this edition we consider one question that has been put to us repeatedly: {qp}\n\n[YOUR ANALYSIS, STATED IN FULL SENTENCES]\n\nWe recommend that readers consider [YOUR RECOMMENDATION]."],
    },
    "plain": {
        "post": ["{qp} I get this a lot.\n\nHere is what I do. [YOUR ANSWER].\n\nFor example, [YOUR REAL EXAMPLE].\n\nTry it and see how it goes."],
        "script": ["A question I get a lot: {qp}\n\nHere is my answer. [YOUR ANSWER]. For example, [YOUR REAL EXAMPLE]."],
        "email": ["Subject: {topic}\n\nHi [NAME],\n\nYou asked: {qp}\n\n[YOUR ANSWER]\n\nLet me know if that helps.\n\n[YOUR NAME]"],
        "newsletter": ["This week: {topic}.\n\nThe question: {qp}\n\n[YOUR ANSWER]\n\n[YOUR REAL EXAMPLE]"],
    },
}


def write(profile: dict, idea: dict, kind: str = "post", n_variants: int = 2) -> list[dict]:
    """Return variants. Each is {label, text, label_note}. The first quote of the idea's evidence is the question."""
    reg = register(profile)
    kind = kind if kind in KINDS else "post"
    raw = _clean_quote((idea.get("evidence") or [{"quote": idea["title"]}])[0]["quote"])
    isq = raw.rstrip().endswith("?")
    q = raw.rstrip(".?! ")
    qp = q + ("?" if isq else ".")
    topic = idea["title"].replace(",", "").strip()[:60] or "your question"
    pool = TEMPLATES[reg][kind]
    contr = profile["dims"]["contractions"]["centre"] > 1.5
    out = []
    for i in range(min(n_variants, max(1, len(pool)) + (1 if n_variants > len(pool) else 0))):
        t = pool[i % len(pool)].format(q=q, qp=qp, topic=topic)
        if i >= len(pool):  # a second variant from a one template pool: change how it opens, never the facts
            t = t.replace("\n\n", "\n\nSo, ", 1) if reg == "plain" else t
        out.append({"label": f"Variant {chr(65 + i)}", "text": contract(t, contr), "register": reg, "stand_in": OFFLINE_LABEL})
    return out
