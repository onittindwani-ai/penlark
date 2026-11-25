"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, Field, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead, Textarea } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Author, Idea, Note } from "@/lib/types";

const KINDS = ["post", "script", "email", "newsletter"];
type IdeasStatus = { status: "none" | "queued" | "running" | "done" | "failed"; ideas: number; message: string };

export default function IdeasPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const { canWrite } = useRole();
  const NO = "Viewers cannot change anything";
  const ideas = useQuery({ queryKey: ["ideas"], queryFn: () => get<Idea[]>("/ideas") });
  const authors = useQuery({ queryKey: ["authors"], queryFn: () => get<Author[]>("/authors") });
  const notes = useQuery({ queryKey: ["notes"], queryFn: () => get<Note[]>("/notes") });
  const [pick, setPick] = useState<Idea | null>(null);
  const [author, setAuthor] = useState(1);
  const [kind, setKind] = useState("post");
  const [adding, setAdding] = useState(false);
  const [nk, setNk] = useState("call");
  const [nw, setNw] = useState("");
  const [nt, setNt] = useState("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["ideas"] }); qc.invalidateQueries({ queryKey: ["notes"] }); qc.invalidateQueries({ queryKey: ["overview"] }); qc.invalidateQueries({ queryKey: ["drafts"] }); };
  const drop = useMutation({ mutationFn: (id: number) => post(`/ideas/${id}/drop`), onSuccess: () => { notify.info("Idea dropped."); refresh(); }, onError: (e: Error) => notify.error("Could not drop the idea", e.message) });
  const [waiting, setWaiting] = useState(false);
  const status = useQuery({ queryKey: ["ideas-status"], queryFn: () => get<IdeasStatus>("/ideas/status"), enabled: waiting, refetchInterval: waiting ? 3000 : false });
  useEffect(() => {
    const st = status.data?.status;
    if (!waiting || (st !== "done" && st !== "failed")) return;
    setWaiting(false);
    if (st === "done") { notify.success(status.data!.ideas === 0 ? "Looked through all notes again. No new ideas." : `Looked through all notes again. ${status.data!.ideas} new idea${status.data!.ideas === 1 ? "" : "s"}.`); refresh(); }
    else notify.error("Could not look again", status.data!.message);
  }, [status.data, waiting]); // eslint-disable-line react-hooks/exhaustive-deps
  const find = useMutation({ mutationFn: () => post<{ ideas: number; queued?: boolean }>("/ideas/refresh"), onSuccess: (r) => { if (r.queued) { notify.info("Looking through your notes. New ideas appear here when it is done."); qc.removeQueries({ queryKey: ["ideas-status"] }); setWaiting(true); return; } notify.success(r.ideas === 0 ? "Looked through all notes again. No new ideas." : `Looked through all notes again. ${r.ideas} new idea${r.ideas === 1 ? "" : "s"}.`); refresh(); }, onError: (e: Error) => notify.error("Could not look again", e.message) });
  const write = useMutation({ mutationFn: () => post<{ id: number }>(`/ideas/${pick?.id}/draft`, { author_id: author, kind }), onSuccess: () => { notify.success("Draft written from your evidence. Fill the brackets in the Studio."); refresh(); setPick(null); router.push("/"); }, onError: (e: Error) => notify.error("Could not write a draft", e.message) });
  const addNote = useMutation({ mutationFn: () => post("/notes", { kind: nk, who: nw, text: nt }), onSuccess: () => { notify.success("Note added."); setAdding(false); setNt(""); setNw(""); refresh(); }, onError: (e: Error) => notify.error("Could not add the note", e.message) });
  if (ideas.isError) return <div className="vp-page"><PageHead title="Ideas" /><LoadError error={ideas.error} onRetry={() => ideas.refetch()} what="ideas" /></div>;
  if (!ideas.data) return <div className="vp-page"><PageHead title="Ideas" /><ListSkeleton /></div>;
  const inbox = ideas.data.filter((i) => i.status !== "dropped").sort((a, b) => Number(a.status === "approved") - Number(b.status === "approved") || b.score - a.score); // ideas that still need a draft come first
  return (
    <div className="vp-page">
      <PageHead title="Ideas" sub="Themes that come back across your calls, comments and emails, each with the exact words people used. The quotes are checked by code against the notes." actions={<><Button feedback={false} disabled={!canWrite} disabledReason={NO} onClick={() => setAdding(true)}>Add a note</Button><Button disabled={!canWrite || waiting} disabledReason={waiting ? "Looking through your notes" : NO} onClick={async () => { await find.mutateAsync(); }}>Find ideas again</Button></>} />
      {waiting && status.data ? <p className="vp-mini" role="status">{status.data.message}</p> : null}
      {inbox.length === 0 ? <EmptyState title="No ideas yet" body="Add the calls, comments and emails you got this week, then find ideas again." actionLabel={canWrite ? "Add a note" : undefined} onAction={() => setAdding(true)} /> : (
        <div className="vp-cols">
          {inbox.map((i) => (
            <Card key={i.id} title={i.title} headingLevel={3} lift>
              <div className="vp-stack">
                <div className="sx-row"><Badge tone={i.score >= 60 ? "accent" : "neutral"}>score {Math.round(i.score)}</Badge><Badge>{i.note_ids.length} note{i.note_ids.length === 1 ? "" : "s"}</Badge>{i.status === "approved" ? <Badge tone="success">has a draft</Badge> : null}</div>
                <p className="vp-mini" style={{ margin: 0 }}>Recurrence {Math.round((i.parts.recurrence ?? 0))}, pain {Math.round((i.parts.pain ?? 0))}, questions {Math.round((i.parts.questions ?? 0))}, specifics {Math.round((i.parts.specifics ?? 0))}, variety {Math.round((i.parts.variety ?? 0))}.</p>
                {i.evidence.map((e) => <blockquote key={e.note_id} className="vp-quote">{e.quote}<br /><span className="vp-mini">Note #{e.note_id}</span></blockquote>)}
                <div className="sx-row"><Button variant="primary" size="sm" disabled={!canWrite} disabledReason={NO} onClick={() => setPick(i)}>{i.status === "approved" ? "Write another draft" : "Write a draft"}</Button><Button size="sm" disabled={!canWrite} disabledReason={NO} onClick={async () => { await drop.mutateAsync(i.id); }}>Drop</Button></div>
              </div>
            </Card>))}
        </div>)}
      <Card title={`Notes (${notes.data?.length ?? 0})`}>
        <div className="vp-stack" style={{ maxHeight: 280, overflow: "auto" }} tabIndex={0} role="region" aria-label="All notes">{(notes.data ?? []).map((n) => <div key={n.id} className="vp-mini"><strong>#{n.id} {n.kind}</strong> {n.who ? `(${n.who}) ` : ""}{n.text}</div>)}</div>
      </Card>
      <Dialog open={pick !== null} onOpenChange={(o) => !o && setPick(null)} title="Write a draft" description="The offline templates build a skeleton from the evidence in the voice you pick. You fill the brackets with your own facts."
        actions={<><Button onClick={() => setPick(null)} feedback={false}>Cancel</Button><Button variant="primary" onClick={async () => { await write.mutateAsync(); }}>Write the draft</Button></>}>
        <div className="vp-stack">
          <label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Voice</span><select className="vp-select" value={author} onChange={(e) => setAuthor(Number(e.target.value))}>{(authors.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          <label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Kind</span><select className="vp-select" value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
        </div>
      </Dialog>
      <Dialog open={adding} onOpenChange={setAdding} title="Add a note" description="A call, a comment, an email, a founder note, or a fact you can stand behind. Notes are the only source for numbers in a draft."
        actions={<><Button onClick={() => setAdding(false)} feedback={false}>Cancel</Button><Button variant="primary" disabled={nt.trim().length < 8} disabledReason="Write at least a short sentence" onClick={async () => { await addNote.mutateAsync(); }}>Add note</Button></>}>
        <div className="vp-stack">
          <label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Kind</span><select className="vp-select" value={nk} onChange={(e) => setNk(e.target.value)}>{["call", "comment", "email", "note", "fact"].map((k) => <option key={k}>{k}</option>)}</select></label>
          <Field label="Who or where from" value={nw} onChange={setNw} maxLength={200} />
          <Textarea label="Text" value={nt} onChange={(e) => setNt(e.target.value)} maxLength={20000} />
        </div>
      </Dialog>
    </div>
  );
}
