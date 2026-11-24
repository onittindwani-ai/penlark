"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, Field, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post, put } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { ExperimentRow } from "@/lib/types";

const TONE: Record<string, "accent" | "warning" | "neutral" | "danger"> = { difference: "accent", too_small: "warning", no_difference: "neutral", invalid: "danger" };
const NAME: Record<string, string> = { difference: "A difference", too_small: "Too few to call", no_difference: "No clear difference", invalid: "Check the numbers" };

function Row({ e, onSaved, canWrite }: { e: ExperimentRow; onSaved: () => void; canWrite: boolean }) {
  const [v, setV] = useState({ a_n: String(e.a_n), a_hits: String(e.a_hits), b_n: String(e.b_n), b_hits: String(e.b_hits) });
  const save = useMutation({ mutationFn: () => put(`/experiments/${e.id}`, { a_n: Number(v.a_n), a_hits: Number(v.a_hits), b_n: Number(v.b_n), b_hits: Number(v.b_hits) }), onSuccess: () => { notify.success("Counts saved."); onSaved(); }, onError: (x: Error) => notify.error("Could not save", x.message) });
  const num = (s: string) => (/^\d{1,9}$/.test(s) ? null : "Whole number, 0 or more");
  const r = e.result;
  return (
    <Card title={e.name} headingLevel={3}>
      <div className="vp-stack">
        <div className="sx-row"><Badge tone={TONE[r.verdict] ?? "neutral"}>{NAME[r.verdict] ?? r.verdict}</Badge><span className="vp-mini">Measured by {e.metric}</span></div>
        {r.a_rate !== undefined ? <p style={{ margin: 0 }}>{e.a_label} <strong>{r.a_rate}%</strong> against {e.b_label} <strong>{r.b_rate}%</strong>. Difference {r.difference_points} points (95% range {r.ci_low} to {r.ci_high}).</p> : null}
        <p className="vp-mini" style={{ margin: 0 }}>{r.note}</p>
        <div className="vp-cols">
          <Field label={`${e.a_label} views`} value={v.a_n} onChange={(x) => setV({ ...v, a_n: x })} validate={num} inputMode="numeric" /><Field label={`${e.a_label} hits`} value={v.a_hits} onChange={(x) => setV({ ...v, a_hits: x })} validate={num} inputMode="numeric" />
          <Field label={`${e.b_label} views`} value={v.b_n} onChange={(x) => setV({ ...v, b_n: x })} validate={num} inputMode="numeric" /><Field label={`${e.b_label} hits`} value={v.b_hits} onChange={(x) => setV({ ...v, b_hits: x })} validate={num} inputMode="numeric" />
        </div>
        <div><Button disabled={!canWrite} disabledReason="Viewers cannot change anything" onClick={async () => { await save.mutateAsync(); }}>Save counts</Button></div>
      </div>
    </Card>
  );
}

export default function ExperimentsPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const q = useQuery({ queryKey: ["experiments"], queryFn: () => get<ExperimentRow[]>("/experiments") });
  const [name, setName] = useState("");
  const [aName, setAName] = useState("");
  const [bName, setBName] = useState("");
  const make = useMutation({ mutationFn: () => post("/experiments", { name, a_label: aName.trim() || "A", b_label: bName.trim() || "B" }), onSuccess: () => { notify.success("Experiment started. Enter the counts as they come in."); setName(""); setAName(""); setBName(""); qc.invalidateQueries({ queryKey: ["experiments"] }); }, onError: (e: Error) => notify.error("Could not start", e.message) });
  if (q.isError) return <div className="vp-page"><PageHead title="Experiments" /><LoadError error={q.error} onRetry={() => q.refetch()} what="experiments" /></div>;
  return (
    <div className="vp-page">
      <PageHead title="Experiments" sub="Two versions, one question. The note under each result is honest about small numbers: one test is a lead, not a rule." />
      <Card title="Start one"><div className="vp-toolbar"><div style={{ flex: 1, minWidth: 220 }}><Field label="What are you comparing?" value={name} onChange={setName} maxLength={200} hint="For example: question opener against statement opener" /></div><div style={{ width: 150 }}><Field label="Name of version A" value={aName} onChange={setAName} maxLength={40} hint="For example: Question" /></div><div style={{ width: 150 }}><Field label="Name of version B" value={bName} onChange={setBName} maxLength={40} hint="For example: Statement" /></div><Button variant="primary" onClick={async () => { await make.mutateAsync(); }} disabled={!canWrite || name.trim().length < 3} disabledReason={!canWrite ? "Viewers cannot change anything" : "Name the test"}>Start</Button></div></Card>
      {!q.data ? <ListSkeleton /> : q.data.length === 0 ? <EmptyState title="No experiments yet" body="Start one above." /> : <div className="vp-cols">{q.data.map((e) => <Row key={`${e.id}-${e.a_n}-${e.b_n}`} canWrite={canWrite} e={e} onSaved={() => qc.invalidateQueries({ queryKey: ["experiments"] })} />)}</div>}
    </div>
  );
}
