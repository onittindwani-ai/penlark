"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead, Textarea } from "@/components/Parts";
import { AddVoice, NoVoices } from "@/components/AddVoice";
import { Radar } from "@/components/Radar";
import { get, post, put } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Author, ProfileResp, RadarRow, Sample } from "@/lib/types";

const round = (n: number | undefined) => (n === undefined ? "" : String(Math.round(n * 100) / 100));

export default function VoicePage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const NO = "Viewers cannot change anything";
  const authors = useQuery({ queryKey: ["authors"], queryFn: () => get<Author[]>("/authors") });
  const [aid, setAid] = useState(1);
  const prof = useQuery({ queryKey: ["profile", aid], queryFn: () => get<ProfileResp>(`/profile?author_id=${aid}`) });
  const samples = useQuery({ queryKey: ["samples", aid], queryFn: () => get<Sample[]>(`/samples?author_id=${aid}`) });
  const [sel, setSel] = useState<string | null>("sentence_length");
  const [overlay, setOverlay] = useState("");
  const [radar, setRadar] = useState<RadarRow[] | null>(null);
  const [guide, setGuide] = useState("");
  const p = prof.data?.profile;
  useEffect(() => { if (p) setGuide(p.guide); setRadar(null); setOverlay(""); }, [p?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = () => { qc.invalidateQueries({ queryKey: ["profile"] }); qc.invalidateQueries({ queryKey: ["authors"] }); };
  const overlayText = async (text: string) => {
    if (!text.trim()) { setRadar(null); return; }
    const r = await post<{ radar: RadarRow[] }>("/profile/compare", { author_id: aid, text });
    setRadar(r.radar);
  };
  const build = useMutation({ mutationFn: () => post<{ version: number }>("/profile/build", { author_id: aid }), onSuccess: (r) => { notify.success(`Version ${r.version} built from ${samples.data?.length ?? 0} samples. Review the guide, then lock it.`); refresh(); }, onError: (e: Error) => notify.error("Could not build", e.message) });
  const saveGuide = useMutation({ mutationFn: () => put(`/profile/${p?.id}/guide`, { guide }), onSuccess: () => { notify.success("Guide saved."); refresh(); }, onError: (e: Error) => notify.error("Could not save", e.message) });
  const lock = useMutation({ mutationFn: () => post(`/profile/${p?.id}/lock`), onSuccess: () => { notify.success("Locked. Scores now use this voice."); refresh(); }, onError: (e: Error) => notify.error("Could not lock", e.message) });
  if (authors.isError || prof.isError) return <div className="vp-page"><PageHead title="Voice profile" /><LoadError error={authors.error ?? prof.error} onRetry={() => { authors.refetch(); prof.refetch(); }} what="the voice profile" /></div>;
  if (!authors.data) return <div className="vp-page"><PageHead title="Voice profile" /><ListSkeleton /></div>;
  if (authors.data.length === 0) return <NoVoices title="Voice profile" />;
  if (!prof.data) return <div className="vp-page"><PageHead title="Voice profile" /><ListSkeleton /></div>;
  const rows = radar ?? p?.radar ?? [];
  const meaning = sel && p ? p.dimension_meanings[sel] : null;
  const ex = (sel && p?.examples[sel]) || [];
  return (
    <div className="vp-page">
      <PageHead title="Voice profile" sub="Code measures how this person writes: 14 style dimensions from their own samples. This is for your own writing, not for copying a named public person." actions={
        <select className="vp-select" aria-label="Voice" value={aid} onChange={(e) => setAid(Number(e.target.value))}>{authors.data.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>} />
      {!p ? <EmptyState title="No profile yet" body="Add at least a few writing samples in the Library, then build the profile." actionLabel={canWrite ? "Build from samples" : undefined} onAction={async () => { await build.mutateAsync(); }} /> : (
        <>
          <div className="vp-two">
            <Card title="Fingerprint radar">
              <Radar rows={rows} selected={sel} onSelect={setSel} overlayLabel="the text you pasted" />
              <div className="vp-toolbar">
                <label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Lay another sample over it</span>
                  <select className="vp-select" aria-label="Lay a sample over the radar" value={overlay} onChange={async (e) => { setOverlay(e.target.value); const s = samples.data?.find((x) => String(x.id) === e.target.value); await overlayText(s?.text ?? ""); }}>
                    <option value="">None</option>{(samples.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.title.slice(0, 40)}</option>)}</select></label>
              </div>
              <Textarea label="Or paste any text to overlay" placeholder="Paste a draft or a stranger's paragraph" onBlur={async (e) => { await overlayText(e.target.value); }} />
            </Card>
            <div className="vp-stack">
              <Card title={meaning?.label ?? "Pick an axis"} headingLevel={2}>
                <p className="vp-mini" style={{ marginTop: 0 }}>{meaning?.meaning ?? "Click a label on the radar."}</p>
                {sel && rows.find((r) => r.key === sel) ? <p style={{ margin: "0 0 13px" }}>Own centre <strong>{round(rows.find((r) => r.key === sel)?.own_raw)}</strong>{rows.find((r) => r.key === sel)?.other_raw !== undefined ? <>; overlay <strong>{round(rows.find((r) => r.key === sel)?.other_raw)}</strong></> : null}</p> : null}
                {ex.length ? ex.map((s) => <blockquote key={s} className="vp-quote vp-mini" style={{ marginBottom: 8 }}>{s}</blockquote>) : <p className="vp-mini">No example sentence for this axis (it is measured over the whole text).</p>}
              </Card>
              <Card title="Favourite words and phrases">
                <div className="sx-row">{p.stats.favourite_words.map((w) => <span key={w} className="vp-chip">{w}</span>)}{p.stats.signature_phrases.map((w) => <span key={w} className="vp-chip">{w}</span>)}{!p.stats.favourite_words.length && !p.stats.signature_phrases.length ? <span className="vp-mini">Not enough samples to say.</span> : null}</div>
              </Card>
            </div>
          </div>
          <div className="vp-two">
            <Card title={`Guide, version ${p.version}`}>
              <div className="vp-stack">
                <div className="sx-row"><Badge tone={p.locked ? "success" : "warning"}>{p.locked ? `locked by ${p.locked_by}` : "not locked"}</Badge><Badge>{p.n_samples} samples</Badge><Badge>{p.guide_source}</Badge></div>
                <Textarea label="Guide in plain words" value={guide} onChange={(e) => setGuide(e.target.value)} disabled={p.locked || !canWrite} style={{ minHeight: 260 }} />
                <div className="sx-row">
                  <Button onClick={async () => { await saveGuide.mutateAsync(); }} disabled={!canWrite || p.locked || guide === p.guide} disabledReason={!canWrite ? NO : p.locked ? "Locked. Build a new version to change the guide." : "No change to save"}>Save guide</Button>
                  <Button variant="primary" onClick={async () => { await lock.mutateAsync(); }} disabled={!canWrite || p.locked} disabledReason={!canWrite ? NO : "Already locked"}>Lock this profile</Button>
                  <Button disabled={!canWrite} disabledReason={NO} onClick={async () => { await build.mutateAsync(); }}>Build a new version</Button>
                </div>
              </div>
            </Card>
            <Card title="Versions and what changed">
              <div className="vp-stack">
                {prof.data.versions.map((v) => <div key={v.id} className="vp-field" style={{ gridTemplateColumns: "1fr auto" }}><span>Version {v.version}<br /><span className="vp-mini">{v.n_samples} samples</span></span><Badge tone={v.locked ? "success" : "neutral"}>{v.locked ? "locked" : "open"}</Badge></div>)}
                {p.diff.length ? p.diff.map((d) => <p key={d.key} className="vp-mini" style={{ margin: 0 }}><strong>{d.label}</strong> went {d.change} ({d.before} to {d.after}).</p>) : <p className="vp-mini" style={{ margin: 0 }}>No large change from the version before.</p>}
              </div>
            </Card>
          </div>
        </>)}
      <AddVoice />
    </div>
  );
}
