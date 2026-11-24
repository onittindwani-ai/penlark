"use client";
import { useId } from "react";
import type { RadarRow } from "@/lib/types";

/** The voice fingerprint radar: one axis per style dimension, the own voice as a filled shape, an optional overlay as a line. Plain SVG with a table for screen readers. */
export function Radar({ rows, selected, onSelect, size = 420, overlayLabel }: { rows: RadarRow[]; selected?: string | null; onSelect?: (key: string) => void; size?: number; overlayLabel?: string }) {
  const id = useId();
  const c = size / 2, R = size / 2 - 76, n = rows.length;
  const pt = (i: number, v: number) => { const a = (Math.PI * 2 * i) / n - Math.PI / 2; return [c + Math.cos(a) * R * (v / 100), c + Math.sin(a) * R * (v / 100)] as const; };
  const path = (vals: number[]) => vals.map((v, i) => pt(i, v).join(",")).join(" ");
  const hasOther = rows.some((r) => r.other !== undefined);
  return (
    <figure className="vp-radar" style={{ margin: 0 }}>
      <svg viewBox={`-100 0 ${size + 200} ${size}`} role="img" aria-labelledby={`${id}-t`} width="100%" style={{ maxWidth: size + 200 }}>
        <title id={`${id}-t`}>Voice fingerprint radar with {n} style dimensions{hasOther ? `, own voice and ${overlayLabel ?? "an overlay"}` : ""}</title>
        {[25, 50, 75, 100].map((g) => <polygon key={g} points={path(rows.map(() => g))} fill="none" stroke="var(--sx-line)" strokeWidth={1} />)}
        {rows.map((r, i) => { const [x, y] = pt(i, 100); return <line key={r.key} x1={c} y1={c} x2={x} y2={y} stroke="var(--sx-line)" />; })}
        <polygon className="vp-radar__own" points={path(rows.map((r) => r.own))} fill="var(--sx-accent)" fillOpacity={0.22} stroke="var(--sx-accent)" strokeWidth={2} />
        {hasOther ? <polygon className="vp-radar__other" points={path(rows.map((r) => r.other ?? 0))} fill="none" stroke="var(--sx-ink)" strokeWidth={2} strokeDasharray="6 4" /> : null}
        {rows.map((r, i) => {
          const [lx, ly] = pt(i, 122);
          const anchor = lx < c - 8 ? "end" : lx > c + 8 ? "start" : "middle";
          return (
            <g key={r.key}>
              <circle cx={pt(i, r.own)[0]} cy={pt(i, r.own)[1]} r={selected === r.key ? 6 : 3.5} fill="var(--sx-accent)" />
              <text x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle" fontSize={11} fill="var(--sx-ink)" fontWeight={selected === r.key ? 700 : 400} style={{ cursor: onSelect ? "pointer" : undefined }} onClick={() => onSelect?.(r.key)}>{r.label}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="sx-sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
        <table><caption>Style dimensions, 0 to 100 on a fixed scale</caption><thead><tr><th>Dimension</th><th>Own voice</th>{hasOther ? <th>{overlayLabel ?? "Overlay"}</th> : null}</tr></thead>
          <tbody>{rows.map((r) => <tr key={r.key}><td>{r.label}</td><td>{r.own}</td>{hasOther ? <td>{r.other}</td> : null}</tr>)}</tbody></table>
      </figcaption>
    </figure>
  );
}
