"""Build a voice profile from writing samples. Code computes statistics; no model is involved here."""

from __future__ import annotations

import re
from collections import Counter

from penlark import dimensions as D
from penlark.textstats import FORMAL, FUNCTION_WORDS, OPENER_KINDS, measure, split_sentences, words

STOP = set(FUNCTION_WORDS) | {"is", "i'm", "it's", "don't", "that's", "we're", "i've", "you're", "can't", "let's"}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _vec_dist(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine distance for the word habits, total variation for the openers (kept simple and deterministic)."""
    keys = list(a)
    dot = sum(a[k] * b.get(k, 0.0) for k in keys)
    na = sum(a[k] ** 2 for k in keys) ** 0.5
    nb = sum(b.get(k, 0.0) ** 2 for k in keys) ** 0.5
    return 1.0 - (dot / (na * nb) if na and nb else 0.0)


def _tv(a: dict[str, float], b: dict[str, float]) -> float:
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in OPENER_KINDS)


def _centroid(ms: list) -> tuple[dict[str, float], dict[str, float]]:
    return ({k: _mean([m.habits[k] for m in ms]) for k in FUNCTION_WORDS}, {k: _mean([m.openers[k] for m in ms]) for k in OPENER_KINDS})


def build_profile(samples: list[str]) -> dict:
    """The profile is plain JSON: per dimension a centre and a tolerance, the word and opener centres, the calibration of the vector distances, favourite words and phrases, and sentence level numbers."""
    ms = [measure(t) for t in samples if t.strip()]
    if not ms:
        raise ValueError("Add at least one writing sample first.")
    dims: dict[str, dict] = {}
    for k, (_l, _m, lo, hi, floor, weight, *_r) in D.SCALAR.items():
        vals = [m.values[k] for m in ms]
        c = _mean(vals)
        dims[k] = {"centre": round(c, 4), "tolerance": round(max(_sd(vals), floor, 0.1 * abs(c)), 4), "weight": weight, "min": min(vals), "max": max(vals)}
    hab, opn = _centroid(ms)
    loo_h, loo_o = [], []
    if len(ms) >= 3:
        # leave one out: the centre of the other samples is the running total minus this sample, so the work grows with the number of samples, not with its square
        n = len(ms)
        tot_h = {k: hab[k] * n for k in FUNCTION_WORDS}
        tot_o = {k: opn[k] * n for k in OPENER_KINDS}
        for m in ms:
            h = {k: (tot_h[k] - m.habits[k]) / (n - 1) for k in FUNCTION_WORDS}
            o = {k: (tot_o[k] - m.openers[k]) / (n - 1) for k in OPENER_KINDS}
            loo_h.append(_vec_dist(m.habits, h))
            loo_o.append(_tv(m.openers, o))
    else:
        loo_h, loo_o = [0.1], [0.3]
    calib = {"word_habits": {"d0": round(_mean(loo_h), 4), "tolerance": round(max(_sd(loo_h), 0.04), 4), "weight": D.VECTOR["word_habits"][2]},
             "openers": {"d0": round(_mean(loo_o), 4), "tolerance": round(max(_sd(loo_o), 0.06), 4), "weight": D.VECTOR["openers"][2]}}
    sent_lens = [len(words(s)) for t in samples for s, _ in split_sentences(t)]
    toks = [w for t in samples for w in words(t)]
    common = Counter(w for w in toks if w not in STOP and len(w) > 3 and not w[0].isdigit())
    per_sample = Counter()
    for t in samples:
        per_sample.update({w for w in set(words(t)) if w in common})
    favourite = [w for w, c in common.most_common(60) if c >= 3 and per_sample[w] >= 2][:12]
    bigrams = Counter(" ".join(p) for p in zip(toks, toks[1:]) if not (p[0] in STOP and p[1] in STOP))
    phrases = [b for b, c in bigrams.most_common(40) if c >= 3][:8]
    return {"n_samples": len(ms), "n_words": sum(m.n_words for m in ms), "dims": dims, "habits_centre": {k: round(v, 5) for k, v in hab.items()}, "openers_centre": {k: round(v, 4) for k, v in opn.items()},
            "vector_calibration": calib, "sentence": {"length_mean": round(_mean(sent_lens), 3), "length_sd": round(max(_sd(sent_lens), 1.0), 3)}, "favourite_words": favourite, "signature_phrases": phrases}


def radar(profile: dict, values: dict[str, float] | None = None) -> list[dict]:
    """Each scalar dimension scaled 0 to 100 against a fixed range, for the radar chart. `values` draws a draft or sample on top."""
    out = []
    for k, (lab, _m, lo, hi, *_r) in D.SCALAR.items():
        sc = lambda x: round(max(0.0, min(1.0, (x - lo) / (hi - lo))) * 100, 1)  # noqa: E731
        row = {"key": k, "label": lab, "own": sc(profile["dims"][k]["centre"]), "own_raw": profile["dims"][k]["centre"]}
        if values is not None:
            row["other"], row["other_raw"] = sc(values[k]), round(values[k], 3)
        out.append(row)
    return out


def examples(samples: list[str], per: int = 2) -> dict[str, list[str]]:
    """Real sentences from the samples that show each dimension, so a person can see what the number means."""
    lens: dict[str, int] = {}
    sents = []
    for t in samples:
        for s, _ in split_sentences(t):
            n = len(words(s))
            if 3 <= n <= 45:
                sents.append(s)
                lens[s] = n
    if not sents:
        return {}
    mean_len = _mean([lens[x] for x in sents])  # once: it is the same for every sentence
    pick = {
        "sentence_length": lambda s: -abs(lens[s] - mean_len),
        "contractions": lambda s: len(re.findall(r"\w['’]\w", s)),
        "questions": lambda s: 1 if s.rstrip().endswith("?") else 0,
        "exclamations": lambda s: s.count("!"),
        "commas": lambda s: s.count(","),
        "heavy_punctuation": lambda s: len(re.findall(r"[;:()]|\.\.\.", s)),
        "numbers": lambda s: len(re.findall(r"\d", s)),
        "formality": lambda s: sum(1 for w in words(s) if w in FORMAL),
        "you_address": lambda s: sum(1 for w in words(s) if w in {"you", "your", "we", "our", "let's"}),
        "i_voice": lambda s: sum(1 for w in words(s) if w in {"i", "my", "me"}),
    }
    out = {}
    for k, f in pick.items():
        ranked = sorted(sents, key=lambda s: (-f(s), len(s)))
        out[k] = [s for s in ranked if f(s) > (-1e9 if k == "sentence_length" else 0)][:per]
    return out
