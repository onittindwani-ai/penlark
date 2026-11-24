"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, Button, Card, ConfirmDialog, CopyButton, EmptyState, Skeleton, notify } from "@sendora/ui-kit";
import { HighlightEditor } from "@/components/HighlightEditor";
import { MatchMeter } from "@/components/MatchMeter";
import { LoadError, PageHead } from "@/components/Parts";
import { get, post, put } from "@/lib/api";
import { wordDiff } from "@/lib/diff";
import { useRole, useSettings } from "@/lib/hooks";
import { DRAFT_STATUS } from "@/lib/labels";
import type { Author, Draft, Evaluation, Note } from "@/lib/types";

const STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "accent" | "danger"> = { draft: "neutral", pending_approval: "warning", approved: "success", scheduled: "accent", exported: "accent", published: "accent", rejected: "danger" };

export default function Studio() {
  const qc = useQueryClient();
  const router = useRouter();
  const { canWrite } = useRole();
  const authors = useQuery({ queryKey: ["authors"], queryFn: () => get<Author[]>("/authors") });
  const drafts = useQuery({ queryKey: ["drafts"], queryFn: () => get<Draft[]>("/drafts") });
  const notes = useQuery({ queryKey: ["notes"], queryFn: () => get<Note[]>("/notes") });
  const settings = useSettings();
  const [draftId, setDraftId] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [authorId, setAuthorId] = useState<number>(1);
  const [sources, setSources] = useState<number[]>([]);
  const [links, setLinks] = useState<Record<string, number>>({});
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);
  const [compare, setCompare] = useState<number | null>(null);
  const [switchTo, setSwitchTo] = useState<number | null>(null);
  const loaded = useRef<number | null>(null);
  const detail = useQuery({ queryKey: ["draft", draftId], queryFn: () => get<Draft>(`/drafts/${draftId}`), enabled: draftId !== null });

  useEffect(() => { if (draftId === null && drafts.data?.length) setDraftId((drafts.data.find((d) => d.status === "draft") ?? drafts.data[0])!.id); }, [drafts.data, draftId]);
  useEffect(() => {
    const d = detail.data;
    if (d && loaded.current !== d.id) { loaded.current = d.id; setText(d.text); setAuthorId(d.author_id); setSources(d.source_note_ids); setLinks(d.claim_links); setEv(d.evaluation ?? null); setCompare(null); }
  }, [detail.data]);
  // live match: a short pause after the last key, then one call that writes nothing
  const seq = useRef(0);
  useEffect(() => {
    if (loaded.current === null && draftId !== null) return;
    const mine = ++seq.current;
    setBusy(true);
    const t = setTimeout(async () => {
      try {
        const r = await post<Evaluation>("/match", { author_id: authorId, text, source_note_ids: sources, claim_links: links });
        if (mine === seq.current) setEv(r);
      } catch { /* the meter keeps its last value; the page shows an error only for loads */ }
      if (mine === seq.current) setBusy(false);
    }, 180);
    return () => clearTimeout(t);
  }, [text, authorId, sources, links, draftId]);

  const d = detail.data;
  const editable = canWrite && !!d && !["exported", "published"].includes(d.status);
  const dirty = !!d && (text !== d.text || authorId !== d.author_id || JSON.stringify(sources) !== JSON.stringify(d.source_note_ids) || JSON.stringify(links) !== JSON.stringify(d.claim_links));
  const body = () => ({ text, author_id: authorId, source_note_ids: sources, claim_links: links });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["drafts"] }); qc.invalidateQueries({ queryKey: ["draft", draftId] }); qc.invalidateQueries({ queryKey: ["overview"] }); qc.invalidateQueries({ queryKey: ["approvals"] }); };
  const save = useMutation({ mutationFn: () => put<Draft>(`/drafts/${draftId}`, body()), onSuccess: () => { if (d && ["pending_approval", "approved", "scheduled"].includes(d.status) && dirty) notify.info("Saved. The approval was withdrawn because the draft changed. Ask again when it is ready."); else notify.success("Draft saved."); refresh(); }, onError: (e: Error) => notify.error("Could not save", e.message) });
  const ask = useMutation({
    mutationFn: async () => { await put(`/drafts/${draftId}`, body()); return post(`/drafts/${draftId}/request-approval`); },
    onSuccess: () => { notify.success("Sent for approval. A second person has to approve it."); refresh(); }, onError: (e: Error) => notify.error("Not ready for approval", e.message),
  });
  const exp = useMutation({ mutationFn: () => post<{ detail: string }>(`/drafts/${draftId}/export`), onSuccess: (r) => { notify.success(`Exported. ${r.detail}`); refresh(); }, onError: (e: Error) => notify.error("Could not export", e.message) });
  const useVar = useMutation({ mutationFn: (id: number) => post<Draft>(`/drafts/${draftId}/variants/${id}/use`), onSuccess: (r) => { setText(r.text); setCompare(null); notify.info("Variant is now the draft."); refresh(); } });
  const diff = useMemo(() => { const v = d?.variants?.find((x) => x.id === compare); return v ? wordDiff(text, v.text) : null; }, [compare, d, text]);

  if (authors.isError || drafts.isError) return <div className="vp-page"><PageHead title="Studio" /><LoadError error={authors.error ?? drafts.error} onRetry={() => { authors.refetch(); drafts.refetch(); }} what="the studio" /></div>;
  if (!authors.data || !drafts.data) return <div className="vp-page"><PageHead title="Studio" /><div className="vp-two"><Skeleton height={560} radius={21} /><Skeleton height={640} radius={21} /></div></div>;
  const author = authors.data.find((a) => a.id === authorId);
  const threshold = settings.data?.rules.min_voice_match ?? 60;
  const unsupported = ev?.rules.unsupported_claims ?? [];
  return (
    <div className="vp-page">
      <PageHead title="Studio" sub="Write or edit a draft and watch how close it sounds to you. The meter is worked out by code from your own samples, not by a language model." actions={
        <>
          <select className="vp-select" aria-label="Voice" value={authorId} disabled={!editable} title={editable ? undefined : "This draft cannot be changed"} onChange={(e) => setAuthorId(Number(e.target.value))}>{authors.data.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        </>} />
      <div className="vp-two">
        <div className="vp-stack">
          <div className="vp-toolbar">
            <label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Draft</span>
              <select className="vp-select" aria-label="Draft" value={draftId ?? ""} onChange={(e) => { const id = Number(e.target.value); if (dirty && editable) setSwitchTo(id); else { loaded.current = null; setDraftId(id); } }}>
                {drafts.data.map((x) => <option key={x.id} value={x.id}>{x.title || `Draft ${x.id}`} ({DRAFT_STATUS[x.status] ?? x.status})</option>)}
              </select></label>
            {d ? <Badge tone={STATUS_TONE[d.status] ?? "neutral"}>{DRAFT_STATUS[d.status] ?? d.status}</Badge> : null}
            {dirty && editable ? <Badge tone="warning">unsaved changes</Badge> : null}
            <span className="vp-mini">{author ? `Voice: ${author.name}` : ""}</span>
          </div>
          {!drafts.data.length ? <EmptyState title="No drafts yet" body="Turn an idea into a draft from the Ideas page, and it opens here." actionLabel="Go to Ideas" onAction={() => router.push("/ideas")} /> : detail.isError ? <LoadError error={detail.error} onRetry={() => detail.refetch()} what="this draft" /> : (draftId === null || !detail.data) ? <Skeleton height={420} radius={21} /> : ( // no editor until the text is there, or what is typed meanwhile is overwritten by the text that arrives
            <>
              <HighlightEditor readOnly={!editable} value={text} onChange={setText} pull={ev?.match.pull_down ?? []} style={ev?.rules.style ?? []} claims={ev?.rules.claims ?? []} />
              <div className="vp-toolbar">
                <Button onClick={async () => { await save.mutateAsync(); }} disabled={!editable || !dirty} disabledReason={!canWrite ? "Viewers cannot change drafts" : !d || ["exported", "published"].includes(d.status) ? "This draft was already exported" : "No changes to save"}>Save draft</Button>
                <Button variant="primary" onClick={async () => { await ask.mutateAsync(); }} disabled={!editable || !text.trim() || d?.status === "pending_approval" || d?.status === "approved"} disabledReason={!canWrite ? "Viewers cannot ask for approval" : d?.status === "pending_approval" ? "Waiting for a second person" : d?.status === "approved" ? "Already approved" : "Write something first"}>Ask for approval</Button>
                <Button onClick={async () => { await exp.mutateAsync(); }} disabled={!canWrite || !d || !["approved", "scheduled"].includes(d.status)} disabledReason={!canWrite ? "Viewers cannot export" : "Only an approved draft can be exported"}>Export to a file</Button>
                {d ? <CopyButton value={d.text} label="Copy the text" /> : null}
                <span className="vp-mini">Editing a draft that is waiting or approved voids the approval.</span>
              </div>
            </>)}
          <Card title="Sources for the facts">
            <p className="vp-mini" style={{ marginTop: 0 }}>Any number, result, client or personal experience must come from a note you attach. Penlark never fills a gap by itself.</p>
            <div className="vp-stack vp-sources" style={{ maxHeight: 210, overflow: "auto" }} tabIndex={0} role="region" aria-label="Notes you can attach">
              {(notes.data ?? []).map((n) => (
                <label key={n.id} className="vp-mini" style={{ display: "flex", gap: 8, alignItems: "flex-start", minHeight: 24 }}>
                  <input type="checkbox" disabled={!editable} checked={sources.includes(n.id)} onChange={(e) => setSources(e.target.checked ? [...sources, n.id] : sources.filter((x) => x !== n.id))} aria-label={`Attach note ${n.id}`} />
                  <span><strong>#{n.id} {n.kind}</strong> {n.text.slice(0, 110)}</span>
                </label>))}
            </div>
            {unsupported.length ? (
              <div className="vp-stack" style={{ marginTop: 13 }}>
                {unsupported.slice(0, 4).map((c) => (
                  <label key={c.text} className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Link a note to: {c.text.slice(0, 80)}</span>
                    <select className="vp-select" disabled={!editable} aria-label={`Link a note to the claim ${c.text.slice(0, 30)}`} value={links[c.text] ?? ""} onChange={(e) => setLinks({ ...links, [c.text]: Number(e.target.value) })}>
                      <option value="">Choose a note</option>{(notes.data ?? []).map((n) => <option key={n.id} value={n.id}>#{n.id} {n.text.slice(0, 50)}</option>)}</select></label>))}
              </div>) : null}
          </Card>
          {d?.variants?.length ? (
            <Card title="Variants">
              <div className="vp-stack">
                {d.variants.map((v) => {
                  const sc = d.variant_scores?.find((x) => x.id === v.id)?.score;
                  return (
                    <div key={v.id} className="vp-field" style={{ gridTemplateColumns: "1fr auto" }}>
                      <span><strong>{v.label}</strong> {sc !== undefined ? <Badge tone={sc >= 80 ? "accent" : sc >= 60 ? "warning" : "danger"}>match {sc}</Badge> : null}<br /><span className="vp-mini">{v.note}</span></span>
                      <span className="sx-row"><Button size="sm" feedback={false} onClick={() => setCompare(compare === v.id ? null : v.id)}>{compare === v.id ? "Hide changes" : "Compare"}</Button><Button size="sm" onClick={async () => { await useVar.mutateAsync(v.id); }} disabled={!editable} disabledReason={!canWrite ? "Viewers cannot change drafts" : "This draft was already exported"}>Use this</Button></span>
                    </div>);
                })}
                {diff ? <p className="vp-diff" aria-label="Changes from the draft to the variant">{diff.map((p, i) => p.op === "same" ? <span key={i}>{p.text}</span> : p.op === "add" ? <ins key={i}>{p.text}</ins> : <del key={i}>{p.text}</del>)}</p> : null}
              </div>
            </Card>) : null}
        </div>
        <div className="vp-stack" style={{ position: "sticky", top: 13 }}>
          <Card title="Voice match, live"><MatchMeter ev={ev} busy={busy} threshold={threshold} /></Card>
        </div>
      </div>
      <ConfirmDialog open={switchTo !== null} onOpenChange={(o) => !o && setSwitchTo(null)} title="Leave this draft?" description="You have changes that are not saved. They will be lost if you open another draft." confirmLabel="Discard the changes" destructive onConfirm={() => { loaded.current = null; setDraftId(switchTo); setSwitchTo(null); }} />
    </div>
  );
}
