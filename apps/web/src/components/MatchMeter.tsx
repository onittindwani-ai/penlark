"use client";
import { Badge, Gauge } from "@sendora/ui-kit";
import type { Evaluation } from "@/lib/types";

const tone = (s: number) => (s >= 80 ? "accent" : s >= 60 ? "warning" : "danger");
const word = (s: number) => (s >= 80 ? "Sounds like you" : s >= 60 ? "Close, a few things drift" : "Does not sound like you yet");

/** The live voice match meter: ring, one bar per dimension, the three weakest dimensions with a plain suggestion, and the house rule and claim checks. */
export function MatchMeter({ ev, busy, threshold }: { ev: Evaluation | null; busy: boolean; threshold: number }) {
  if (!ev) return <div className="vp-meter" aria-busy="true"><div className="vp-mini">Scoring...</div></div>;
  const m = ev.match;
  return (
    <div className="vp-meter" aria-live="polite" data-busy={busy}>
      <div className="vp-meter__top">
        <Gauge value={m.score / 100} size={144} label="Voice match" display={String(m.score)} />
        <div className="vp-stack" style={{ gap: 6 }}>
          <Badge tone={tone(m.score)}>{m.confidence === "none" ? "Waiting for text" : word(m.score)}</Badge>
          <span className="vp-mini">{m.n_words} words{m.note ? `. ${m.note}` : ""}</span>
          <span className="vp-mini">Needs {threshold} to go to approval. Scored in {m.ms} ms by code, not a language model.</span>
        </div>
      </div>
      <ul className="vp-bars" aria-label="Match by dimension">
        {m.dimensions.map((d) => (
          <li key={d.key} title={d.advice ?? "Close to this voice"}>
            <span className="vp-bars__label">{d.label}</span>
            <span className="vp-bar" role="img" aria-label={`${d.label} ${Math.round(d.score)} of 100`}><span style={{ width: `${d.score}%`, background: d.score >= 70 ? "var(--sx-accent)" : d.score >= 45 ? "var(--sx-warning)" : "var(--sx-danger)" }} /></span>
            <span className="vp-bars__n">{Math.round(d.score)}</span>
          </li>
        ))}
      </ul>
      {m.weakest.length ? (
        <div className="vp-stack">
          <h3 className="vp-h3">What to change</h3>
          {m.weakest.map((w) => <p key={w.key} className="vp-mini" style={{ margin: 0 }}><strong>{w.label}.</strong> {w.advice}</p>)}
        </div>
      ) : null}
      <div className="vp-stack">
        <h3 className="vp-h3">House rules</h3>
        {ev.rules.style.length === 0 && ev.rules.unsupported_claims.length === 0 && ev.placeholders.length === 0 ? <Badge tone="success">No rule broken</Badge> : null}
        {ev.rules.style.slice(0, 5).map((f, i) => <p key={i} className="vp-flag vp-flag--rule">{f.message}</p>)}
        {ev.rules.unsupported_claims.slice(0, 4).map((c, i) => <p key={i} className="vp-flag vp-flag--claim"><strong>Needs a source or a founder fact:</strong> {c.text.slice(0, 90)}</p>)}
        {ev.placeholders.length ? <p className="vp-flag vp-flag--claim">Fill in {ev.placeholders.length} bracket{ev.placeholders.length > 1 ? "s" : ""} with your own words: {ev.placeholders.slice(0, 3).join(", ")}</p> : null}
        <span className="vp-mini">Reading level grade {ev.rules.grade}. Profile version {ev.profile_version ?? "none"}{ev.profile_locked ? ", locked" : ", not locked yet"}.</span>
      </div>
    </div>
  );
}
