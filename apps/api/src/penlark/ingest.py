"""Read writing the user owns or provides. Markdown, text, PDF, a pasted post, a transcript, and three export layouts.

Export layouts: LinkedIn Shares.csv (columns Date, ShareLink, ShareCommentary, SharedUrl, MediaUrl, Visibility), X archive tweets.js
(`window.YTD.tweets.part0 = [ { "tweet": { "full_text", "created_at", "retweeted" ... } } ]`), YouTube transcript text. The LinkedIn and X layouts
are written from memory of the exports and are UNVERIFIED against a fresh export. Nothing is fetched from any account: the user brings the file.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass

MAX_BYTES = 8_000_000


class IngestError(ValueError):
    pass


@dataclass
class Item:
    title: str
    text: str
    kind: str = "post"
    date: str = ""


def clean(t: str) -> str:
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def from_markdown(text: str, title: str = "") -> Item:
    t = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"(\*\*|__|\*|_|`)", "", t)
    return Item(title or (t.strip().split("\n")[0][:60] if t.strip() else "Untitled"), clean(t), "markdown")


def from_text(text: str, title: str = "") -> Item:
    t = clean(text)
    return Item(title or (t.split("\n")[0][:60] if t else "Untitled"), t, "text")


def from_pdf(data: bytes, title: str = "") -> Item:
    if len(data) > MAX_BYTES:
        raise IngestError("That PDF is larger than 8 MB.")
    try:
        from pypdf import PdfReader

        rd = PdfReader(io.BytesIO(data))
        t = "\n\n".join((p.extract_text() or "") for p in rd.pages[:200])
    except Exception as exc:  # a damaged file must give a clear message, never a crash
        raise IngestError("That PDF could not be read. Export it again or paste the text.") from exc
    if not t.strip():
        raise IngestError("That PDF has no text layer (it may be a scan). Paste the text instead.")
    return Item(title or "PDF", clean(t), "pdf")


_TS = re.compile(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?(?:\s*-->\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?.*)?\s*$")


def from_transcript(text: str, title: str = "", speaker: str | None = None) -> Item:
    """Plain text, WebVTT, SRT, YouTube transcript text with timestamps, or `Speaker: words` lines. With `speaker`, keep only that person's lines."""
    lines, out = clean(text).split("\n"), []
    for ln in lines:
        s = ln.strip()
        if not s or s.upper() == "WEBVTT" or s.isdigit() or _TS.match(s) or s.startswith(("NOTE ", "Kind:", "Language:")):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        m = re.match(r"^([A-Z][\w .'-]{0,40}):\s+(.*)$", s)
        if speaker is not None:
            if not m or m.group(1).strip().lower() != speaker.strip().lower():
                continue
            s = m.group(2)
        elif m:
            s = m.group(2)
        out.append(s)
    body = clean(" ".join(out) if not speaker else "\n".join(out))
    if not body:
        raise IngestError("No spoken text was found in that transcript.")
    return Item(title or "Transcript", body, "transcript")


def from_linkedin_csv(data: str) -> list[Item]:
    rd = csv.DictReader(io.StringIO(data))
    need = {"ShareCommentary"}
    if not rd.fieldnames or not need <= set(rd.fieldnames):
        raise IngestError("This does not look like LinkedIn's Shares.csv. Expected a ShareCommentary column.")
    out = []
    for row in rd:
        t = clean(row.get("ShareCommentary") or "")
        if len(t.split()) >= 8:
            out.append(Item(t[:60], t, "post", (row.get("Date") or "")[:10]))
    return out


def from_x_archive(data: str) -> list[Item]:
    m = re.search(r"=\s*(\[.*\])\s*;?\s*$", data.strip(), flags=re.S)
    try:
        rows = json.loads(m.group(1) if m else data)
    except ValueError as exc:
        raise IngestError("This does not look like tweets.js from an X archive.") from exc
    out = []
    for r in rows if isinstance(rows, list) else []:
        t = r.get("tweet", r) if isinstance(r, dict) else {}
        txt = t.get("full_text") or ""
        if not txt or txt.startswith("RT @") or t.get("retweeted") is True:
            continue
        txt = re.sub(r"https?://\S+", "", txt)
        txt = re.sub(r"^(?:@\w+\s+)+", "", txt)
        if len(txt.split()) >= 6:
            out.append(Item(txt[:60], clean(txt), "post", str(t.get("created_at", ""))[:30]))
    return out


ALLOWED_EXTENSIONS = (".txt", ".md", ".pdf", ".vtt", ".srt", ".csv", ".js")
MIN_CHARS = 20  # the same bar as a pasted sample: a few sentences, not a stray word


def detect(filename: str, data: bytes) -> list[Item]:
    name = filename.lower()
    if "." in name.rsplit("/", 1)[-1] and not name.endswith(ALLOWED_EXTENSIONS):
        raise IngestError("That file type is not supported. Use .txt, .md, .pdf, .vtt, .srt, .csv or .js, or paste the text.")
    items = _detect(filename, data)
    kept = [i for i in items if len(i.text.strip()) >= MIN_CHARS]
    if not kept:
        raise IngestError("There is no text in that file, or too little of it (at least a few sentences).")
    return kept


def _detect(filename: str, data: bytes) -> list[Item]:
    if len(data) > MAX_BYTES:
        raise IngestError("That file is larger than 8 MB.")
    name = filename.lower()
    if name.endswith(".pdf"):
        return [from_pdf(data, filename)]
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError("That file is not UTF-8 text.") from exc
    if name.endswith((".vtt", ".srt")):
        return [from_transcript(text, filename)]
    if name.endswith(".md"):
        return [from_markdown(text, filename)]
    if name.endswith(".csv") and "ShareCommentary" in text[:2000]:
        return from_linkedin_csv(text)
    if name.endswith(".js") and "tweet" in text[:4000]:
        return from_x_archive(text)
    if "transcript" in name:
        return [from_transcript(text, filename)]
    return [from_text(text, filename)]
