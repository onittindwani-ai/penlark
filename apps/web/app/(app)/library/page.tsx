"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { useRole } from "@/lib/hooks";
import { NoVoices } from "@/components/AddVoice";
import { FileDrop, LoadError, PageHead, Textarea } from "@/components/Parts";
import { api, get, post } from "@/lib/api";
import type { Author, Sample } from "@/lib/types";

export default function LibraryPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const NO = "Viewers cannot change anything";
  const authors = useQuery({ queryKey: ["authors"], queryFn: () => get<Author[]>("/authors") });
  const [aid, setAid] = useState(1);
  const samples = useQuery({ queryKey: ["samples", aid], queryFn: () => get<Sample[]>(`/samples?author_id=${aid}`) });
  const [text, setText] = useState("");
  const [kind, setKind] = useState("text");
  const [rm, setRm] = useState<Sample | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["samples"] }); qc.invalidateQueries({ queryKey: ["authors"] }); };
  const add = useMutation({ mutationFn: () => post("/samples", { author_id: aid, text, kind }), onSuccess: () => { notify.success("Sample added. Build a new profile version to use it."); setText(""); refresh(); }, onError: (e: Error) => notify.error("Could not add the sample", e.message) });
  const upload = useMutation({
    mutationFn: async (f: File) => api<{ added: number; skipped?: number }>(`/samples/upload?author_id=${aid}`, { method: "POST", raw: await f.arrayBuffer(), headers: { "x-filename": f.name } }),
    onSuccess: (r) => { if (r.added === 0) notify.info("Nothing new: every text in that file is already in the library."); else notify.success(`Added ${r.added} sample${r.added === 1 ? "" : "s"}.${r.skipped ? ` ${r.skipped} already in the library, skipped.` : ""}`); refresh(); }, onError: (e: Error) => notify.error("Could not read that file", e.message),
  });
  const remove = useMutation({ mutationFn: (id: number) => api(`/samples/${id}`, { method: "DELETE" }), onSuccess: () => { notify.info("Sample removed."); refresh(); }, onError: (e: Error) => notify.error("Could not remove it", e.message) });
  const columns: Column<Sample>[] = [
    { key: "title", header: "Sample", width: "minmax(0, 2fr)", sortValue: (r) => r.title },
    { key: "kind", header: "Kind", width: "90px", sortValue: (r) => r.kind },
    { key: "words", header: "Words", width: "80px", align: "right", sortValue: (r) => r.words },
    { key: "source", header: "Source", width: "minmax(0, 1fr)", sortValue: (r) => r.source },
  ];
  if (authors.isError || samples.isError) return <div className="vp-page"><PageHead title="Library" /><LoadError error={authors.error ?? samples.error} onRetry={() => samples.refetch()} what="the library" /></div>;
  if (authors.data && authors.data.length === 0) return <NoVoices title="Library" />;
  return (
    <div className="vp-page">
      <PageHead title="Library" sub="Writing that belongs to this voice: posts, emails, transcripts of talks. Only text you own or provide. Nothing is fetched from anyone's account." actions={
        <select className="vp-select" aria-label="Voice" value={aid} onChange={(e) => setAid(Number(e.target.value))}>{(authors.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>} />
      <div className="vp-two">
        {!samples.data ? <TableSkeleton rows={8} columns={4} /> : samples.data.length === 0 ? <EmptyState title="No samples yet" body="Paste a post or upload a file on the right. Fifteen or more samples give a steadier profile." /> : (
          <div className="vp-act-88 vp-noopen"><DataTable label="Samples" rows={samples.data} rowKey={(r) => String(r.id)} columns={columns} height={460} rowActions={(r) => <Button size="sm" variant="ghost" disabled={!canWrite} disabledReason={NO} onClick={() => setRm(r)} feedback={false} aria-label={`Remove ${r.title}`}>Remove</Button>} /></div>)}
        <div className="vp-stack">
          <Card title="Paste a sample">
            <div className="vp-stack">
              <select className="vp-select" aria-label="Kind of text" value={kind} onChange={(e) => setKind(e.target.value)}><option value="text">Plain text or a post</option><option value="markdown">Markdown</option><option value="transcript">Transcript (VTT, SRT or captions)</option></select>
              <Textarea label="Text" value={text} readOnly={!canWrite} onChange={(e) => setText(e.target.value)} />
              <Button variant="primary" onClick={async () => { await add.mutateAsync(); }} disabled={!canWrite || text.trim().length < 20} disabledReason={!canWrite ? NO : "Paste at least a few sentences"}>Add sample</Button>
            </div>
          </Card>
          <Card title="Upload a file">
            <p className="vp-mini" style={{ marginTop: 0 }}>Text, markdown, PDF, a transcript, a LinkedIn Shares.csv or an X archive tweets.js. Up to 8 MB.</p>
            <FileDrop accept=".txt,.md,.pdf,.vtt,.srt,.csv,.js" label="Choose a file or drop it here" disabled={!canWrite} disabledReason={NO} onFile={async (f) => { if (f.size > 8 * 1024 * 1024) { notify.error("That file is too big", "The limit is 8 MB."); return; } await upload.mutateAsync(f).catch(() => null); }} />
            <Badge>LinkedIn and X layouts: UNVERIFIED</Badge>
          </Card>
        </div>
      </div>
      <ConfirmDialog open={rm !== null} onOpenChange={(o) => !o && setRm(null)} title="Remove this sample?" description="It stops counting the next time you build a profile version. Old versions keep their numbers." confirmLabel="Remove" destructive onConfirm={() => { if (rm) void remove.mutateAsync(rm.id); }} />
    </div>
  );
}
