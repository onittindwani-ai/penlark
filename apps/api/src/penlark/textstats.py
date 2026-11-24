"""Plain text measurement. No model, no network. Everything here is deterministic."""

from __future__ import annotations

import re
from dataclasses import dataclass

WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*|\d[\d,.]*%?")
ABBREV = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|St|vs|etc|e\.g|i\.e|No)\.", re.I)
CONTRACTION = re.compile(r"\b\w+['’](?:t|s|re|ve|ll|d|m)\b", re.I)
NUMBER = re.compile(r"\b\d[\d,.]*%?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|percent)\b", re.I)
FORMAL = {"furthermore", "moreover", "accordingly", "therefore", "consequently", "whilst", "thus", "hence", "regarding", "pursuant", "herein", "thereof", "notwithstanding", "recommend", "recommended", "organisations", "organisation", "organizations", "organization", "considered", "ought", "shall", "principal", "material", "respectfully", "enclose", "enclosed", "kindly", "prior", "commencement", "whereas", "otherwise", "should", "must", "provisions", "demonstrated", "established", "observed", "pleased", "grateful", "regard", "concerning", "further"}
CASUAL = {"honestly", "kinda", "gonna", "gotta", "yeah", "yep", "wow", "ok", "okay", "like", "literally", "basically", "stuff", "guys", "cool", "awesome", "super", "tiny", "lovely", "little", "really", "just", "so", "lol", "ish"}
I_WORDS = {"i", "me", "my", "mine", "myself", "i'm", "i've", "i'd", "i'll"}
YOU_WORDS = {"you", "your", "yours", "you're", "you've", "you'll", "you'd", "yourself"}
WE_WORDS = {"we", "our", "ours", "us", "let's", "we're", "we've", "we'll"}


def words(text: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD.findall(text)]


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def split_sentences(text: str) -> list[tuple[str, int]]:
    """(sentence, start offset). A line break also ends a sentence, so headings and one line lines count on their own."""
    masked = ABBREV.sub(lambda m: m.group(0).replace(".", "\u0001"), text)
    masked = re.sub(r"(?<=\d)\.(?=\d)", "\u0001", masked)
    out: list[tuple[str, int]] = []
    for m in re.finditer(r"[^.!?\n]+(?:[.!?]+[\"'”’)]*|\n|$)", masked):
        raw = m.group(0)
        s = raw.strip()
        if s and re.search(r"[A-Za-z0-9]", s):
            lead = len(raw) - len(raw.lstrip())
            out.append((text[m.start() + lead:m.start() + lead + len(s)], m.start() + lead))
    return out


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def reading_grade(text: str) -> float:
    ws = [w for w in words(text) if w[0].isalpha()]
    sents = split_sentences(text)
    if not ws or not sents:
        return 0.0
    syl = sum(syllables(w) for w in ws)
    return round(0.39 * (len(ws) / len(sents)) + 11.8 * (syl / len(ws)) - 15.59, 1)


def mattr(ws: list[str], window: int = 25) -> float:
    """Moving average type token ratio: vocabulary richness that does not collapse as texts get longer."""
    if len(ws) < window:
        return len(set(ws)) / max(1, len(ws))
    seen: dict[str, int] = {}
    tot, n = 0.0, 0
    for i, w in enumerate(ws):
        seen[w] = seen.get(w, 0) + 1
        if i >= window:
            old = ws[i - window]
            seen[old] -= 1
            if not seen[old]:
                del seen[old]
        if i >= window - 1:
            tot += len(seen) / window
            n += 1
    return tot / n


def sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


@dataclass
class Measured:
    n_words: int
    n_sentences: int
    values: dict[str, float]
    openers: dict[str, float]
    habits: dict[str, float]


FUNCTION_WORDS = ("the a an and but or so because if then when while as of in on at to for with from by about into over after before it this that these those is are was were be been am not no do does did have has had will would can could should may might must i you he she we they me him her us them my your our their there here what which who how why all some any each more most just also very too than only even still yet again really quite rather however therefore thus though although whilst furthermore moreover indeed perhaps maybe actually honestly well now one").split()
OPENER_KINDS = ("question", "number", "i", "you_we", "conjunction", "the_it", "other")
_CONJ = {"and", "but", "so", "because", "then", "or", "yet", "while", "if", "when"}


def opener_kind(sentence: str) -> str:
    ws = words(sentence)
    if not ws:
        return "other"
    w = ws[0]
    if sentence.rstrip().endswith("?"):
        return "question"
    if w[0].isdigit():
        return "number"
    if w in I_WORDS:
        return "i"
    if w in YOU_WORDS or w in WE_WORDS:
        return "you_we"
    if w in _CONJ:
        return "conjunction"
    if w in {"the", "it", "this", "that", "there", "these", "those", "a", "an"}:
        return "the_it"
    return "other"


def measure(text: str) -> Measured:
    ws = words(text)
    sents = split_sentences(text)
    paras = paragraphs(text)
    n = max(1, len(ws))
    ns = max(1, len(sents))
    lens = [float(len(words(s))) for s, _ in sents] or [0.0]
    para_sents = [len(split_sentences(p)) for p in paras] or [1]
    heavy = len(re.findall(r"[;:()]|\.\.\.|…", text)) + len(re.findall(r"[\"“”]", text)) / 2
    v = {
        "sentence_length": sum(lens) / len(lens),
        "sentence_variety": sd(lens),
        "paragraph_length": sum(para_sents) / len(para_sents),
        "one_line_paragraphs": sum(1 for p in para_sents if p == 1) / len(para_sents),
        "contractions": 100 * len(CONTRACTION.findall(text)) / n,
        "questions": text.count("?") / ns,
        "exclamations": text.count("!") / ns,
        "commas": text.count(",") / ns,
        "heavy_punctuation": heavy / ns,
        "numbers": 100 * len(NUMBER.findall(text)) / n,
        "vocabulary_richness": mattr(ws),
        "formality": 100 * (sum(1 for w in ws if w in FORMAL) - sum(1 for w in ws if w in CASUAL)) / n,
        "you_address": 100 * sum(1 for w in ws if w in YOU_WORDS or w in WE_WORDS) / n,
        "i_voice": 100 * sum(1 for w in ws if w in I_WORDS) / n,
    }
    kinds = [opener_kind(s) for s, _ in sents]
    openers = {k: kinds.count(k) / ns for k in OPENER_KINDS}
    habits = {w: ws.count(w) / n for w in FUNCTION_WORDS}
    return Measured(len(ws), len(sents), v, openers, habits)
