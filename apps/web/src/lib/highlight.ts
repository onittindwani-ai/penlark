import type { Claim, PullDown, StyleFlag } from "./types";

export interface Span { start: number; end: number; cls: string; title: string }
export interface Segment { text: string; span?: Span }

/** The API counts positions in characters as Python does (one emoji is one position), but a JavaScript string counts UTF-16 units (an emoji is two).
 *  Every position here is therefore a position in the list of code points, never an index into the string. */
export function codePoints(text: string): string[] {
  return Array.from(text);
}

/** The marks to draw: pulls, style flags and unsupported claims, in order of position, with overlapping ones dropped (the first wins). `length` is the number of code points of the text. */
export function buildSpans(length: number, pull: PullDown[], style: StyleFlag[], claims: Claim[]): Span[] {
  const out: Span[] = [];
  for (const p of pull) out.push({ start: p.start, end: p.end, cls: "vp-hl--pull", title: `Removing this sentence would raise the match by ${p.delta} points` });
  for (const f of style) if (f.end > f.start) out.push({ start: f.start, end: f.end, cls: "vp-hl--rule", title: f.message });
  for (const c of claims) if (!c.supported) out.push({ start: c.start, end: c.end, cls: "vp-hl--claim", title: c.message });
  const ok = out.filter((s) => s.start >= 0 && s.end <= length && s.end > s.start).sort((a, b) => a.start - b.start || b.end - a.end);
  const res: Span[] = [];
  let at = 0;
  for (const s of ok) if (s.start >= at) { res.push(s); at = s.end; }
  return res;
}

/** The text cut into plain stretches and marked ones, by code point position. */
export function segments(text: string, spans: Span[]): Segment[] {
  const cps = codePoints(text);
  const parts: Segment[] = [];
  let at = 0;
  for (const s of spans) {
    if (s.start > at) parts.push({ text: cps.slice(at, s.start).join("") });
    parts.push({ text: cps.slice(s.start, s.end).join(""), span: s });
    at = s.end;
  }
  parts.push({ text: cps.slice(at).join("") });
  return parts;
}
