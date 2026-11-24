"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, Sheet, TableSkeleton, formatWhen, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { auditAction, auditTarget } from "@/lib/labels";
import type { AuditRow } from "@/lib/types";

export default function AuditPage() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => get<AuditRow[]>("/audit?limit=500") });
  const v = useQuery({ queryKey: ["audit-verify"], queryFn: () => get<{ ok: boolean; first_bad_id: number | null }>("/audit/verify") });
  const check = useMutation({ mutationFn: () => v.refetch(), onSuccess: (r) => (r.data?.ok ? notify.success("The audit log is intact. No entry was changed or removed.") : notify.error("The audit log was changed", `The first bad entry is number ${r.data?.first_bad_id}.`)), onError: (e: Error) => notify.error("Could not check the chain", e.message) });
  const [open, setOpen] = useState<AuditRow | null>(null);
  const columns: Column<AuditRow>[] = [
    { key: "id", header: "No.", width: "70px", align: "right", sortValue: (r) => r.id },
    { key: "at", header: "When", width: "150px", render: (r) => formatWhen(new Date(r.at)), sortValue: (r) => r.at },
    { key: "actor", header: "Who", width: "minmax(0, 1fr)", sortValue: (r) => r.actor },
    { key: "action", header: "What", width: "minmax(0, 1.4fr)", render: (r) => <button type="button" className="vp-linkbtn" tabIndex={-1} onClick={() => setOpen(r)}><Badge>{auditAction(r.action)}</Badge></button>, sortValue: (r) => auditAction(r.action) },
    { key: "target", header: "About", width: "minmax(0, 1fr)", render: (r) => auditTarget(r.target), sortValue: (r) => r.target ?? "" },
  ];
  return (
    <div className="vp-page">
      <PageHead title="Audit log" sub="Every change, who made it and when. Each line is chained to the one before, so an edit after the fact shows." actions={<Button onClick={async () => { await check.mutateAsync(); }}>Check the chain</Button>} />
      <Card>{v.isError ? <Badge tone="danger">Could not check the chain</Badge> : v.data ? <Badge tone={v.data.ok ? "success" : "danger"}>{v.data.ok ? "Chain intact" : `Chain broken at entry ${v.data.first_bad_id}`}</Badge> : <Badge>Checking</Badge>}</Card>
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="the audit log" /> : !q.data ? <TableSkeleton rows={8} columns={5} /> : q.data.length === 0 ? <Card><EmptyState title="Nothing logged yet" body="Actions show up here as they happen." /></Card> : <div className="vp-act-72"><DataTable label="Audit log" rows={q.data} rowKey={(r) => String(r.id)} columns={columns} height={520} onRowOpen={setOpen} rowActions={(r) => <Button size="sm" feedback={false} onClick={() => setOpen(r)}>Open</Button>} /></div>}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open ? auditAction(open.action) : "Entry"} description={open ? `Entry number ${open.id}` : undefined}>
        {open ? (
          <dl className="vp-stack" style={{ margin: 0 }}>
            <div><dt className="vp-mini">When</dt><dd style={{ margin: 0 }}>{new Date(open.at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "medium" })}</dd></div>
            <div><dt className="vp-mini">Who</dt><dd style={{ margin: 0 }}>{open.actor}</dd></div>
            <div><dt className="vp-mini">About</dt><dd style={{ margin: 0 }}>{auditTarget(open.target) || "Nothing in particular"}</dd></div>
            <div><dt className="vp-mini">Details</dt><dd style={{ margin: 0 }}>{Object.keys(open.detail ?? {}).length ? Object.entries(open.detail).map(([k, x]) => <p key={k} className="vp-mini" style={{ margin: "0 0 4px" }}><strong>{k.replace(/_/g, " ")}</strong> {typeof x === "object" ? JSON.stringify(x) : String(x)}</p>) : "None recorded."}</dd></div>
          </dl>
        ) : null}
      </Sheet>
    </div>
  );
}
