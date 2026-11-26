"""House rules: banned phrases and patterns, no dashes, reading level, and the claims check.

The claims check is the guard against invented facts. A sentence that holds a number, a result, a client or a personal experience must be tied to a
source note whose own text contains the same numbers. Otherwise the draft is flagged "needs a source or a founder fact". Penlark never fills the gap itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from penlark import safe_regex
from penlark.textstats import reading_grade, split_sentences, words

MIN_WORDS_FOR_GRADE = 8  # the grade formula swings wildly on a few words, so a very short text is not judged on reading level

DEFAULT_BANNED = [
    "in today's fast-paced world", "in today's fast paced world", "in today's digital landscape", "in the ever-evolving", "ever-evolving landscape", "in the realm of", "it is important to note", "it's important to note",
    "it's worth noting", "it is worth noting", "it's crucial to", "it is crucial to", "let's dive in", "let's delve", "dive deep", "deep dive", "delve into", "unlock the power", "unlock your potential", "unlock new opportunities",
    "take your", "to the next level", "game changer", "game-changer", "game changing", "revolutionize", "revolutionise", "harness the power", "leverage the power", "leveraging", "cutting-edge", "cutting edge", "state-of-the-art",
    "seamless experience", "seamlessly integrate", "navigate the complexities", "navigating the", "rich tapestry", "tapestry of", "testament to", "at the end of the day", "in conclusion", "in summary", "to sum up",
    "moving forward", "going forward", "circle back", "low-hanging fruit", "move the needle", "synergy", "paradigm shift", "thought leader", "best practices", "robust solution", "holistic approach", "streamline workflows",
    "drive meaningful engagement", "foster a culture", "empower your team", "empowers teams", "empower you", "transformative potential", "elevate your", "stand out from the crowd", "whether you're a seasoned",
    "whether you are a seasoned", "success is a journey", "key takeaways", "here's everything you need to know", "here is everything you need to know", "buckle up", "without further ado", "the power of",
    "in this article, we", "in this post, we", "i'm excited to announce", "i am excited to announce", "i'm thrilled to", "i am thrilled to", "humbled to", "game on", "hot take", "unpack", "pivotal", "plethora", "myriad of",
    "crucial role", "vital role", "ever-changing", "fast-paced", "work-life balance", "think outside the box", "hit the ground running", "tip of the iceberg", "needle in a haystack", "it goes without saying",
    # added in round 4 from general knowledge of machine sounding marketing (multi word phrases, or words that real writers rarely use); each can still be turned off in the app
    "ever-evolving world", "rapidly evolving", "constantly evolving", "now more than ever", "look no further", "unleash the", "unleash your", "supercharge", "best-in-class", "one-stop shop", "stay ahead of the curve", "ahead of the curve",
    "at your fingertips", "embark on a journey", "embark on this journey", "unlock the secrets", "unlock the full potential", "unlock the potential", "in a world where", "it's no secret that", "it is no secret that", "plays a pivotal role",
    "plays a crucial role", "seamlessly", "utilize", "utilise", "endless possibilities", "world of possibilities", "mission-critical", "turnkey solution", "end-to-end solution", "tailored to your needs", "a game-changing", "ultimate solution",
]
DEFAULT_PATTERNS = [
    (r"\bin today'?s [\w\- ]{0,30}(?:world|landscape|era|age|market)\b", "A stock opener that sounds like a template."),
    (r"\bit'?s not (?:just|only|about) [^.;,]{1,60}[,;] it'?s\b", "The \"it's not X, it's Y\" turn is a very common machine habit."),
    (r"\bnot (?:just|only) [^.;]{1,60}, but (?:also )?\b", "\"Not only X but also Y\" is a stock turn."),
    (r"\b(?:imagine|picture) a world where\b", "A stock opener."),
    (r"\b(?:are you ready to|ready to take)\b", "A stock sales opener."),
]
DASHES = ("\u2014", "\u2013", "\u2012", "\u2015", " - ")


@dataclass
class Rules:
    banned: list[str]
    patterns: list[tuple[str, str]]
    no_dashes: bool = True
    max_grade: float | None = None
    min_grade: float | None = None
    require_sources: bool = True


def default_rules() -> Rules:
    return Rules(list(DEFAULT_BANNED), list(DEFAULT_PATTERNS))


def _norm(t: str) -> str:
    return t.lower().replace("’", "'")


@lru_cache(maxsize=1024)
def phrase_regex(phrase: str) -> re.Pattern[str] | None:
    """A banned phrase matches in any case, with a space or a hyphen between its words, with a straight or curly apostrophe, and with the regular endings of a word
    inside it (leverage, leverages, leveraged, leveraging). Hyphens inside the phrase and spaces are the same thing: "game-changer" also catches "game changer"."""
    words = [w for w in re.split(r"[\s\-]+", _norm(phrase).strip()) if w]
    if not words:
        return None
    parts = []
    for w in words:
        body = re.escape(w).replace("\\'", "['\u2019]").replace("'", "['\u2019]")
        if w.isalpha() and len(w) >= 7 and w.endswith("ing"):
            body = re.escape(w[:-3]) + r"(?:e|es|ed|ing)"
        elif w.isalpha() and len(w) >= 5 and not w.endswith(("ed", "ing", "s")):
            body = re.escape(w[:-1]) + r"(?:e|es|ed|ing)" if w.endswith("e") else body + r"(?:s|es|ed|ing)?"
        parts.append(body)
    return re.compile(r"(?<![A-Za-z])" + r"[\s\-]+".join(parts) + r"(?![A-Za-z])", re.I)


def check_style(text: str, rules: Rules) -> list[dict]:
    flags: list[dict] = []
    low = _norm(text)
    for ph in rules.banned:
        rx = phrase_regex(ph)
        if rx is None:
            continue
        for m in rx.finditer(text):
            flags.append({"kind": "banned_phrase", "start": m.start(), "end": m.end(), "text": text[m.start():m.end()], "message": f"\"{ph}\" is on the banned list."})
    for pat, why in rules.patterns:
        unsafe = safe_regex.problem(pat)
        if unsafe:  # a pattern that could freeze the process is never run: it is shown instead, so a person fixes it on the Rules page
            flags.append({"kind": "unsafe_rule", "start": 0, "end": 0, "text": "", "message": f"The banned pattern \"{pat[:60]}\" was not run. {unsafe} Edit or delete it on the Rules page."})
            continue
        try:
            for n, m in enumerate(re.finditer(pat, low)):
                if n >= safe_regex.MAX_MATCHES:
                    break
                flags.append({"kind": "banned_pattern", "start": m.start(), "end": m.end(), "text": text[m.start():m.end()], "message": why})
        except re.error:
            continue
    if rules.no_dashes:
        for d in DASHES:
            for m in re.finditer(re.escape(d), text):
                flags.append({"kind": "dash", "start": m.start(), "end": m.end(), "text": text[m.start():m.end()], "message": "No dashes. Use a comma, a colon, a full stop or brackets."})
    if (rules.max_grade is not None or rules.min_grade is not None) and len(words(text)) >= MIN_WORDS_FOR_GRADE:
        g = reading_grade(text)
        if rules.max_grade is not None and g > rules.max_grade:
            flags.append({"kind": "reading_level", "start": 0, "end": 0, "text": "", "message": f"Reading level is grade {g}, above your limit of {rules.max_grade}. Shorten sentences and swap long words."})
        if rules.min_grade is not None and g < rules.min_grade:
            flags.append({"kind": "reading_level", "start": 0, "end": 0, "text": "", "message": f"Reading level is grade {g}, below your floor of {rules.min_grade}."})
    seen: set[tuple] = set()
    unique = []
    for f in flags:  # two list entries for the same words (game changer, game-changer) give one flag
        k = (f["kind"], f["start"], f["end"])
        if k not in seen:
            seen.add(k)
            unique.append(f)
    unique.sort(key=lambda f: (f["start"], f["kind"]))
    return unique


EXPERIENCE = re.compile(r"\b(?:i|we)(?:['\u2019]ve|\s+have|\s+had)?\s+(?:built|launched|lost|closed|grew|raised|hired|fired|sold|shipped|made|saved|doubled|tripled|cut|paid|quit|started|ran|wrote|tested|tried|signed|won|helped|trained|coached|taught|treated|handled|managed|delivered|onboarded|boosted|generated|booked|landed|scaled|mentored|recruited|fixed|repaired|installed|rebuilt|cleared)\b", re.I)
_PEOPLE = r"(?:client|customer|student|patient|boss|investor|cofounder|co-founder|member|employee|apprentice|driver|account)s?"
# a client claim names a client of the writer or says what a client did. A generic "a patient" or "the student" in advice is not a claim.
CLIENT = re.compile(rf"\b(?:my|our)\s+(?:\w+\s+)?{_PEOPLE}\b|\bone\s+of\s+(?:my|our)\s+\w+|\b(?:a|one|another)\s+{_PEOPLE}\s+(?:of\s+(?:mine|ours)|told|asked|said|wrote|emailed|called|came|hired|paid|signed|cancell?ed|left|stayed|renewed|saw|got|gained|lost|saved|doubled|texted|messaged|messaged)\b", re.I)
_NUMWORD = r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|millions?|dozens?)"
# a number written as a word counts as a figure when it counts people, firms, money or a share, or says how long someone has done something
NUMWORD_CLAIM = re.compile(rf"\b{_NUMWORD}\s+(?:of\s+(?:my|our|the)\s+)?(?:percent|per\s+cent|times|dollars|pounds|euros|clients|customers|patients|students|people|users|leads|sales|calls|employees|hires|orders|members|teams|companies|businesses|nurses|drivers|shipments|loads|cases|kids|children|families|farmers|teachers|electricians|dentists)\b|\b(?:for|over|after|than|nearly|almost|about)\s+{_NUMWORD}\s+(?:years|months)\b", re.I)
RESULT = re.compile(r"\b(?:increased|decreased|grew|dropped|rose|fell|doubled|tripled|halved|improved|reduced|saved)\b[^.]{0,40}\bby\b", re.I)


_WORDNUM = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|billion"
# A figure is a whole number as written: 1500 and 1,500 are the same figure, 15 is not 150 or 5, and "15%" and "15 percent" are the same figure.
_FIGURE = re.compile(rf"(?<![\d.,])(\d[\d,]*(?:\.\d+)?)(\s*(?:%|percent\b|per\s+cent\b))?|\b({_WORDNUM})\b(\s+(?:percent|per\s+cent)\b)?", re.I)


def _numtokens(s: str) -> set[str]:
    out: set[str] = set()
    for m in _FIGURE.finditer(s):
        base = m.group(1).replace(",", "") if m.group(1) else m.group(3).lower()
        out.add(base + ("%" if m.group(2) or m.group(4) else ""))
    return out


def find_claims(text: str) -> list[dict]:
    out = []
    for s, start in split_sentences(text):
        kinds = []
        if re.search(r"\d", s) or re.search(r"\b(?:percent|million|billion|thousand|hundred)\b", s, re.I) or NUMWORD_CLAIM.search(s):
            kinds.append("number")
        if EXPERIENCE.search(s):
            kinds.append("experience")
        if CLIENT.search(s):
            kinds.append("client")
        if RESULT.search(s):
            kinds.append("result")
        if kinds:
            out.append({"text": s, "start": start, "end": start + len(s), "kinds": kinds})
    return out


def check_claims(text: str, notes: dict[int, str], links: dict[str, int] | None = None) -> list[dict]:
    """`notes` maps note id to text, and holds the notes attached to the draft. `links` maps a claim sentence to a note id chosen by a person.

    A claim with numbers is supported only when the linked (or any attached) note contains every number in it. A claim with no numbers (an experience or a client)
    is supported only when a person linked a note to it. Nothing is ever inferred as supported by a language model.
    """
    links = links or {}
    out = []
    for c in find_claims(text):
        nums = _numtokens(c["text"]) if "number" in c["kinds"] or "result" in c["kinds"] else set()
        nums = {n for n in nums if not (n.isdigit() and len(n) == 4 and 1900 <= int(n) <= 2100)}
        linked = links.get(c["text"])
        support = None
        if linked is not None and linked in notes:
            if nums <= _numtokens(notes[linked]):  # every figure of the claim is a whole figure of the note, never part of a longer number
                support = linked
        elif nums:
            for nid, body in notes.items():
                if nums <= _numtokens(body):
                    support = nid
                    break
        c["source_note_id"] = support
        c["supported"] = support is not None
        c["message"] = "" if support is not None else "Needs a source or a founder fact: attach the note that shows this, or remove the line."
        out.append(c)
    return out


def check_all(text: str, rules: Rules, notes: dict[int, str], links: dict[str, int] | None = None) -> dict:
    style = check_style(text, rules)
    claims = check_claims(text, notes, links) if rules.require_sources else []
    unsupported = [c for c in claims if not c["supported"]]
    return {"style": style, "claims": claims, "unsupported_claims": unsupported, "ok": not style and not unsupported, "grade": reading_grade(text), "words": len(words(text))}
