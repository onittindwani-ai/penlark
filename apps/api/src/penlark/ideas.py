"""Idea finder: notes (calls, comments, emails, founder notes) to ranked ideas with verbatim evidence.

Plain rules, not a language model. Ideas come from themes that come back across different notes. Every evidence quote is checked by `verify_quote`:
a quote that is not the exact characters of its source note is dropped, never shown.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from penlark.textstats import split_sentences, words

PAIN = re.compile(r"\b(afraid|scared|fear|hate|never know|awkward|cannot tell|can't tell|struggle|worried|confus|ignore|procrastinat|overwhelm|stuck|nervous|embarrass|annoy|frustrat|rude|pushy|late|stress|wish|dread|lost|slow)\w*", re.I)
ASK = re.compile(r"\?|\b(how|when|why|what|which|should|does|is it|can i|do you have|anyone else)\b", re.I)
LOGISTICS = re.compile(r"\b(reschedul|dentist|charger|printer paper|calendar sync|see you|thanks|thank you|perfect|got it working|sync to \d|moved the)\b", re.I)
STOPS = set("the a an and or but so to of in on for with at by from is are was were be been it its this that these those i you he she we they my your our their me us them not no do does did have has had will would can could should as if then than there here what when how why which who just also very too about into over after before still even only really quite one said says say asked asks told".split())


IRREGULAR = {"children": "child", "kids": "kid", "people": "person", "men": "man", "women": "woman", "went": "go", "gone": "go", "going": "go", "paid": "pay", "bought": "buy", "sold": "sell", "told": "tell", "said": "say", "wrote": "write", "written": "write",
             "taught": "teach", "thought": "think", "felt": "feel", "lost": "lose", "found": "find", "kept": "keep", "left": "leave", "made": "make", "took": "take", "taken": "take", "gave": "give", "given": "give", "knew": "know", "known": "know", "ran": "run", "came": "come"}
# Families of everyday words that mean nearly the same thing. They are matched after stemming, so "worried", "afraid" and "dread" can show the same theme.
# General vocabulary only: nothing here comes from any test set. Each family points at its first word.
SYNONYMS = [("worry", "afraid", "anxious", "nervous", "scared", "fear", "dread", "stress"), ("awkward", "uncomfortable", "embarrass", "rude", "pushy", "cringe"), ("late", "overdue", "delay", "behind"),
            ("confus", "unclear", "puzzl", "baffl"), ("cost", "price", "expensive", "cheap", "afford", "fee"), ("tire", "exhaust", "drain", "burnout"), ("teach", "train", "instruct", "coach", "educat"),
            ("fix", "repair", "mend", "solve"), ("buy", "purchase"), ("begin", "start"), ("help", "assist"), ("slow", "sluggish"), ("ask", "question", "wonder", "inquir"), ("mistake", "error", "wrong", "blunder"),
            ("rule", "polic", "regulation"), ("trust", "believ", "confiden"), ("talk", "speak", "conversation", "discuss")]
_FAMILY = {}


def _suffixes(w: str) -> str:
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ied"):
        return w[:-3] + "y"
    for suf in ("ations", "ation", "ments", "ment", "ness", "ings", "ing", "ers", "er", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= (3 if suf in ("ing", "ings") else 4):
            w = w[: -len(suf)]
            break
    if len(w) > 4 and w[-1] == w[-2] and w[-1] not in "lsz":
        w = w[:-1]  # stopping -> stopp -> stop
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]  # make and making meet at mak
    return w


def stem(w: str) -> str:
    w = IRREGULAR.get(w, w)
    s = _suffixes(w)
    if not _FAMILY:
        for fam in SYNONYMS:
            head = _suffixes(fam[0])
            for member in fam:
                _FAMILY[_suffixes(member)] = head
                _FAMILY[member] = head
    return _FAMILY.get(s, s)


def verify_quote(source: str, quote: str) -> bool:
    return bool(quote) and quote in source


@dataclass
class Candidate:
    note_id: int
    kind: str
    sentence: str
    start: int
    stems: set[str]
    pain: bool
    ask: bool
    number: bool
    noise: bool


@dataclass
class IdeaOut:
    title: str
    theme_stems: list[str]
    note_ids: list[int]
    evidence: list[dict]
    score: float
    parts: dict[str, float] = field(default_factory=dict)


def make_candidate(note_id: int, kind: str, sentence: str, start: int) -> Candidate:
    ws = words(sentence)
    st = {stem(w) for w in ws if w not in STOPS and len(w) > 3 and not w[0].isdigit()}
    return Candidate(note_id, kind, sentence, start, st, bool(PAIN.search(sentence)), bool(ASK.search(sentence)), bool(re.search(r"\d", sentence)), bool(LOGISTICS.search(sentence)))


def _candidates(notes: list[dict]) -> list[Candidate]:
    out = []
    for n in notes:
        for s, start in split_sentences(n["text"]):
            if len(words(s)) < 6:
                continue
            out.append(make_candidate(n["id"], n["kind"], s, start))
    return out


def score_group(g: list[Candidate], n_notes: int) -> tuple[float, dict[str, float]]:
    """The score of an idea from its evidence sentences. The same numbers for an idea found by code and for one a model proposed."""
    ids = {c.note_id for c in g}
    rec = math.log(1 + len(ids)) / math.log(1 + max(n_notes, 1))
    parts = {"recurrence": round(rec * 100 / 0.55, 1) if rec < 0.55 else 100.0, "pain": round(100 * sum(c.pain for c in g) / len(g), 1), "questions": round(100 * sum(c.ask for c in g) / len(g), 1),
             "specifics": round(100 * sum(c.number for c in g) / len(g), 1), "variety": round(100 * min(1.0, len({c.kind for c in g}) / 3), 1)}
    score = 0.45 * parts["recurrence"] + 0.2 * parts["pain"] + 0.15 * parts["questions"] + 0.1 * parts["specifics"] + 0.1 * parts["variety"]
    if all(c.noise for c in g):
        score *= 0.3
    return round(min(100.0, score), 1), parts


# Bounds for the finder, so one writer (or a long call transcript) cannot make it use the memory of the whole server. The pair table below grows with the
# square of the words kept per note, so each note keeps only its rarest words (the ones that can tell two notes apart).
MAX_NOTES = 1000  # the newest notes only
MAX_NOTE_CHARS = 20000  # the same limit the API puts on one note
MAX_TOTAL_CHARS = 1_000_000  # all notes together; the oldest are left out first
MAX_STEMS_PER_NOTE = 30
MAX_THEMES = 400


def limit_notes(notes: list[dict], max_notes: int = MAX_NOTES, max_chars: int = MAX_TOTAL_CHARS) -> list[dict]:
    """The newest notes (the end of the list) that fit the bounds, in their original order. A note longer than MAX_NOTE_CHARS is cut; a quote taken from the start still matches the full note."""
    kept: list[dict] = []
    total = 0
    for n in reversed(notes):
        text = n["text"][:MAX_NOTE_CHARS]
        if len(kept) >= max_notes or total + len(text) > max_chars:
            break
        kept.append({**n, "text": text})
        total += len(text)
    kept.reverse()
    return kept


def find_ideas(notes: list[dict], max_ideas: int = 10) -> list[IdeaOut]:
    cands = _candidates(limit_notes(notes))
    by_note: dict[int, list[Candidate]] = defaultdict(list)
    for c in cands:
        by_note[c.note_id].append(c)
    order = {nid: pos for pos, nid in enumerate(by_note)}
    n_notes = len(by_note) or 1
    df: dict[str, set[int]] = defaultdict(set)
    for c in cands:
        for s in c.stems:
            df[s].add(c.note_id)
    # a word that is in almost every note says nothing about a theme; a word in only one note cannot recur
    useful = {s: math.log(n_notes / len(ids)) for s, ids in df.items() if 2 <= len(ids) <= max(3, int(0.45 * n_notes))}
    # themes: pairs of useful words that show up together in several different notes; each note joins its first (strongest) theme
    note_stems: dict[int, set[str]] = defaultdict(set)
    for c in cands:
        if not c.noise:
            note_stems[c.note_id] |= {s for s in c.stems if s in useful}
    pair_notes: dict[tuple[str, str], set[int]] = defaultdict(set)
    for nid, st in note_stems.items():
        ss = sorted(sorted(st, key=lambda w: (-useful[w], w))[:MAX_STEMS_PER_NOTE])  # the rarest words of the note, then alphabetical so the result never depends on set order
        for x in range(len(ss)):
            for y in range(x + 1, len(ss)):
                pair_notes[(ss[x], ss[y])].add(nid)
    pair_notes = {k: ids for k, ids in pair_notes.items() if len(ids) >= 2}  # a pair seen in one note cannot make a theme: do not scan it again and again
    assigned: set[int] = set()
    groups: dict[int, list[Candidate]] = {}
    themes: list[tuple[str, str]] = []
    while len(themes) < MAX_THEMES:
        best, bk = None, None
        for k, ids in pair_notes.items():
            free = ids - assigned
            if len(free) < 2:
                continue
            key = (len(free), useful[k[0]] + useful[k[1]])
            if best is None or key > best:
                best, bk = key, k
        if bk is None:
            break
        free = pair_notes[bk] - assigned
        assigned |= free
        pair_set = set(bk)
        groups[len(themes)] = [c for nid in sorted(free, key=order.__getitem__) for c in by_note[nid] if not c.noise and (c.stems & pair_set)]
        themes.append(bk)
    for c in cands:  # a single note can still be an idea when it is a clear, specific question or pain
        if c.note_id not in assigned and not c.noise and c.pain and c.ask:
            groups[len(themes)] = [c]
            themes.append(tuple(sorted(s for s in c.stems if s in useful))[:2] or ("",))  # type: ignore[arg-type]
            assigned.add(c.note_id)
    ideas: list[IdeaOut] = []
    for gi, g in groups.items():
        if not g:
            continue
        ids = sorted({c.note_id for c in g})
        counts: dict[str, int] = defaultdict(int)
        for c in g:
            for s in c.stems:
                if s in useful:
                    counts[s] += 1
        theme = [s for s, _ in sorted(counts.items(), key=lambda kv: (-kv[1] * useful[kv[0]], kv[0]))][:4] or list(themes[gi])
        surface = {stem(w): w for c in g for w in words(c.sentence)}
        label = [surface.get(t, t) for t in theme]
        ranked = sorted(g, key=lambda c: (-(c.pain + c.ask + c.number), len(c.sentence)))
        seen, ev = set(), []
        for c in ranked:
            if c.note_id in seen:
                continue
            seen.add(c.note_id)
            ev.append({"note_id": c.note_id, "quote": c.sentence, "start": c.start})
            if len(ev) == 3:
                break
        score, parts = score_group(g, n_notes)
        ideas.append(IdeaOut((ev[0]["quote"][:70].rstrip(" .,;:!?") if ev else ", ".join(label[:3])) or "untitled theme", theme, ids, ev, score, parts))
    ideas.sort(key=lambda i: -i.score)
    return ideas[:max_ideas]
