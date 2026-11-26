"use client";
import { useRef, type ChangeEvent } from "react";
import { buildSpans, codePoints, segments } from "@/lib/highlight";
import type { Claim, PullDown, StyleFlag } from "@/lib/types";

/** A transparent textarea on top of a mirrored layer that underlines sentences and flags. The mirror uses the same font, padding and wrapping, so the marks sit under the right words. */
export function HighlightEditor({ value, onChange, pull, style, claims, label = "Draft text", rows = 14, readOnly = false }: { value: string; onChange: (v: string) => void; readOnly?: boolean; pull: PullDown[]; style: StyleFlag[]; claims: Claim[]; label?: string; rows?: number }) {
  const mirror = useRef<HTMLDivElement>(null);
  // positions from the API count characters (an emoji is one), so the text is cut by code point, never by UTF-16 index
  const parts: React.ReactNode[] = segments(value, buildSpans(codePoints(value).length, pull, style, claims)).map((seg, i) => seg.span ? <mark key={i} className={`vp-hl ${seg.span.cls}`} title={seg.span.title}>{seg.text}</mark> : seg.text);
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
