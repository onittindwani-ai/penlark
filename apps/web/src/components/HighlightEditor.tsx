"use client";
import { useRef, type ChangeEvent } from "react";
import type { Claim, PullDown, StyleFlag } from "@/lib/types";

interface Span { start: number; end: number; cls: string; title: string }

function spans(text: string, pull: PullDown[], style: StyleFlag[], claims: Claim[]): Span[] {
  const out: Span[] = [];
  for (const p of pull) out.push({ start: p.start, end: p.end, cls: "vp-hl--pull", title: `Removing this sentence would raise the match by ${p.delta} points` });
  for (const f of style) if (f.end > f.start) out.push({ start: f.start, end: f.end, cls: "vp-hl--rule", title: f.message });
  for (const c of claims) if (!c.supported) out.push({ start: c.start, end: c.end, cls: "vp-hl--claim", title: c.message });
  const ok = out.filter((s) => s.start >= 0 && s.end <= text.length && s.end > s.start).sort((a, b) => a.start - b.start || b.end - a.end);
  // keep non overlapping spans, the first (rules and claims were pushed after pulls, so a flag sorts by position) wins
  const res: Span[] = [];
  let at = 0;
  for (const s of ok) if (s.start >= at) { res.push(s); at = s.end; }
  return res;
}

/** A transparent textarea on top of a mirrored layer that underlines sentences and flags. The mirror uses the same font, padding and wrapping, so the marks sit under the right words. */
export function HighlightEditor({ value, onChange, pull, style, claims, label = "Draft text", rows = 14, readOnly = false }: { value: string; onChange: (v: string) => void; readOnly?: boolean; pull: PullDown[]; style: StyleFlag[]; claims: Claim[]; label?: string; rows?: number }) {
  const mirror = useRef<HTMLDivElement>(null);
  const parts: React.ReactNode[] = [];
  let at = 0;
  spans(value, pull, style, claims).forEach((s, i) => {
    if (s.start > at) parts.push(value.slice(at, s.start));
    parts.push(<mark key={i} className={`vp-hl ${s.cls}`} title={s.title}>{value.slice(s.start, s.end)}</mark>);
    at = s.end;
  });
  parts.push(value.slice(at));
  return (
    <div className="vp-editor">
      <div className="vp-editor__mirror" ref={mirror} aria-hidden="true">{parts}{"\n"}</div>
      <textarea
        className="vp-editor__input"
        aria-label={label}
        rows={rows}
        value={value}
        spellCheck
        maxLength={30000}
        readOnly={readOnly}
        aria-readonly={readOnly || undefined}
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
        onScroll={(e) => { if (mirror.current) mirror.current.scrollTop = e.currentTarget.scrollTop; }}
      />
    </div>
  );
}
