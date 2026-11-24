"""The plain language voice guide. The offline stand in turns the measured numbers into sentences with fixed rules. It is NOT a language model.

The live path (LLM_BACKEND=anthropic, GUIDE_WRITER=model) is `model_tasks.write_guide`, through the shared wrapper. It has never run against the real service, so it is UNVERIFIED. A person edits the guide and locks it.
"""

from __future__ import annotations

OFFLINE_LABEL = "Written by the offline stand in (fixed rules over the measured numbers). It is not a language model. Edit it freely."


def _band(x: float, cuts: list[tuple[float, str]], top: str) -> str:
    for c, t in cuts:
        if x < c:
            return t
    return top


def offline_guide(profile: dict, name: str) -> str:
    d = {k: v["centre"] for k, v in profile["dims"].items()}
    out = [f"Voice guide for {name}", "", OFFLINE_LABEL, ""]
    sl = d["sentence_length"]
    out.append("Sentences: " + _band(sl, [(9, f"short and blunt, about {sl:.0f} words, with fragments allowed."), (16, f"plain and medium, about {sl:.0f} words."), (22, f"fairly long, about {sl:.0f} words, with a clause or two.")], f"long and structured, about {sl:.0f} words.") + " " + _band(d["sentence_variety"], [(3, "The length stays even."), (7, "The length varies a little.")], "The rhythm jumps between very short and long lines."))
    out.append("Paragraphs: " + _band(d["paragraph_length"], [(1.6, "mostly one line each. Let a punchy line stand alone."), (3.2, "two or three sentences.")], "long blocks of four or more sentences."))
    out.append("Tone: " + (_band(d["formality"], [(-0.5, "casual and spoken."), (1.0, "relaxed but tidy.")], "formal and measured. Avoid slang.")) + " " + ("Uses contractions freely." if d["contractions"] > 2.5 else "Rarely uses contractions. Write the full words." if d["contractions"] < 0.6 else "Uses some contractions."))
    out.append("Talking to the reader: " + ("often says you and we." if d["you_address"] > 4 else "mostly describes things without addressing the reader.") + (" Speaks from personal experience with I." if d["i_voice"] > 2.5 else " Rarely says I."))
    q, e = d["questions"], d["exclamations"]
    out.append("Questions and energy: " + ("asks the reader questions often." if q > 0.12 else "seldom asks questions." if q < 0.03 else "asks a question now and then.") + (" Uses exclamation marks." if e > 0.08 else " Avoids exclamation marks."))
    out.append("Detail: " + ("uses concrete numbers often." if d["numbers"] > 3 else "uses few numbers.") + (" Uses colons, brackets or ellipses as habits." if d["heavy_punctuation"] > 0.4 else ""))
    kinds = profile["openers_centre"]
    top = max(kinds, key=kinds.get)
    label = {"question": "a question", "number": "a number", "i": "I", "you_we": "you or we", "conjunction": "a joining word such as and, but or so", "the_it": "the, it or this", "other": "a plain subject"}[top]
    out.append(f"Sentences most often start with {label}.")
    if profile.get("favourite_words"):
        out.append("Favourite words: " + ", ".join(profile["favourite_words"]) + ".")
    if profile.get("signature_phrases"):
        out.append("Phrases that keep coming back: " + "; ".join(profile["signature_phrases"]) + ".")
    out += ["", "Never invent facts, numbers or stories. If a line needs a real example, leave a bracket for the author."]
    return "\n".join(out)


def diff_profiles(old: dict | None, new: dict) -> list[dict]:
    """What changed between two profile versions, per dimension, in plain words."""
    from penlark import dimensions as D

    if not old:
        return []
    out = []
    for k, (lab, *_r) in D.SCALAR.items():
        a, b = old["dims"][k]["centre"], new["dims"][k]["centre"]
        tol = max(old["dims"][k]["tolerance"], 1e-9)
        if abs(b - a) / tol >= 0.25:
            out.append({"key": k, "label": lab, "before": round(a, 3), "after": round(b, 3), "change": "up" if b > a else "down"})
    return out
