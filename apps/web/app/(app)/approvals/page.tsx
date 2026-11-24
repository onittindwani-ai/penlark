"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, EmptyState, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import Link from "next/link";
import type { ApprovalRow } from "@/lib/types";

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const NO = "Viewers cannot decide";
  const q = useQuery({ queryKey: ["approvals"], queryFn: () => get<ApprovalRow[]>("/approvals") });
  const decide = useMutation({
    mutationFn: (v: { id: number; approve: boolean }) => post(`/approvals/${v.id}/decide`, { approve: v.approve, note: "" }),
    onSuccess: (_r, v) => { notify.success(v.approve ? "Approved." : "Rejected."); qc.invalidateQueries(); },
    onError: (e: Error) => { notify.error("Could not decide", e.message); qc.invalidateQueries({ queryKey: ["approvals"] }); },
  });
  if (q.isError) return <div className="vp-page"><PageHead title="Approvals" /><LoadError error={q.error} onRetry={() => q.refetch()} what="approvals" /></div>;
  if (!q.data) return <div className="vp-page"><PageHead title="Approvals" /><ListSkeleton /></div>;
  const pending = q.data.filter((a) => a.status === "pending");
  const past = q.data.filter((a) => a.status !== "pending");
  return (
    <div className="vp-page">
      <PageHead title="Approvals" sub="Anything that reaches outside this app waits here for a person. The person who asked cannot approve their own request." />
      <Card title={`Waiting (${pending.length})`}>{pending.length === 0 ? <EmptyState title="Nothing waiting" body="Risky actions such as sending a reminder show up here." /> : (
        <div className="vp-stack">{pending.map((a) => (
          <div key={a.id} className="vp-field" style={{ gridTemplateColumns: "1fr auto" }}>
            <span><strong>{a.summary}</strong> <Badge tone={a.risk === "high" ? "danger" : "warning"}>{a.risk} risk</Badge><br /><span className="vp-mini" style={{ fontSize: "var(--sx-text-caption)", color: "var(--sx-ink-2)" }}>Asked by {a.requested_by} on {a.created_at.slice(0, 10)}</span>{a.preview ? <><blockquote className="vp-quote vp-approval-text">{a.preview.text}</blockquote><Link href="/" className="vp-mini vp-approval-link">Open the Studio</Link></> : null}</span>
            <span className="sx-row"><Button size="sm" variant="primary" disabled={!canWrite} disabledReason={NO} onClick={async () => { await decide.mutateAsync({ id: a.id, approve: true }).catch(() => null); }}>Approve</Button><Button size="sm" disabled={!canWrite} disabledReason={NO} onClick={async () => { await decide.mutateAsync({ id: a.id, approve: false }).catch(() => null); }}>Reject</Button></span>
          </div>))}</div>)}</Card>
      <Card title="Decided">{past.length === 0 ? <EmptyState title="No history yet" body="Decisions appear here." /> : <div className="vp-stack">{past.map((a) => <div key={a.id} className="vp-field" style={{ gridTemplateColumns: "1fr auto" }}><span>{a.summary}{a.note ? <><br /><span className="vp-mini">{a.note}</span></> : null}</span><Badge tone={a.status === "approved" ? "success" : "neutral"}>{a.status === "approved" ? "approved" : "rejected"} by {a.decided_by}</Badge></div>)}</div>}</Card>
    </div>
  );
}
