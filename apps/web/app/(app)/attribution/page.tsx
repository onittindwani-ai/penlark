"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, CopyButton, DataTable, EmptyState, Field, Stat, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Funnel, FunnelRow, Integrations, LinkRow } from "@/lib/types";

export default function AttributionPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const f = useQuery({ queryKey: ["attribution"], queryFn: () => get<Funnel>("/attribution") });
  const links = useQuery({ queryKey: ["links"], queryFn: () => get<LinkRow[]>("/links") });
  const integ = useQuery({ queryKey: ["integrations"], queryFn: () => get<Integrations>("/integrations") });
  const [target, setTarget] = useState("https://larkspur.example.test/start");
  const [campaign, setCampaign] = useState("");
  const [source, setSource] = useState("linkedin");
  const make = useMutation({ mutationFn: () => post<{ short_url: string; short_path: string; existing: boolean }>("/links", { target, campaign, source, medium: "social" }), onSuccess: (r) => { if (r.existing) notify.info(`You already have that link: ${origin}${r.short_path}`); else notify.success(`Link made: ${origin}${r.short_path}`); setCampaign(""); qc.invalidateQueries({ queryKey: ["links"] }); qc.invalidateQueries({ queryKey: ["attribution"] }); }, onError: (e: Error) => notify.error("Could not make the link", e.message) });
  // In the demo the app answers on its own address, not on the default one the server knows.
  const linkUrl = (l: { short_url: string; short_path: string; base_is_default: boolean }) => (l.base_is_default ? `${origin}${l.short_path}` : l.short_url);
  const columns: Column<FunnelRow>[] = [
    { key: "post", header: "Post", width: "minmax(0, 1fr)", render: (r) => r.post_ref || r.code, sortValue: (r) => r.post_ref },
    { key: "campaign", header: "Campaign", width: "minmax(0, 1fr)", sortValue: (r) => r.campaign },
    { key: "clicks", header: "Clicks", width: "80px", align: "right", sortValue: (r) => r.clicks },
    { key: "unique", header: "Unique", width: "80px", align: "right", sortValue: (r) => r.unique_clicks },
    { key: "leads", header: "Leads", width: "80px", align: "right", sortValue: (r) => r.leads },
    { key: "customers", header: "Customers", width: "100px", align: "right", sortValue: (r) => r.customers },
  ];
  if (f.isError) return <div className="vp-page"><PageHead title="Attribution" /><LoadError error={f.error} onRetry={() => f.refetch()} what="attribution" /></div>;
  const t = f.data?.totals;
  const max = Math.max(1, t?.clicks ?? 1);
  return (
    <div className="vp-page">
      <PageHead title="Attribution" sub="Tracked links show which posts bring clicks and leads. A link can only point at a host on your allow list, so it can never become an open redirect." />
      <div className="vp-stats">
        <Card><Stat label="Clicks" value={t?.clicks ?? 0} /></Card><Card><Stat label="Unique visitors" value={t?.unique_clicks ?? 0} /></Card><Card><Stat label="Leads" value={t?.leads ?? 0} /></Card><Card><Stat label="Customers" value={t?.customers ?? 0} /></Card>
      </div>
      <div className="vp-two">
        <Card title="Funnel">
          {!t ? <TableSkeleton rows={3} columns={2} /> : (
            <div className="vp-funnel">
              {[["Clicks", t.clicks], ["Unique", t.unique_clicks], ["Leads", t.leads], ["Customers", t.customers]].map(([l, n]) => (
                <div key={String(l)} className="vp-funnel__row"><span>{l}</span><span className="vp-bar" role="img" aria-label={`${l}: ${n}`}><span style={{ width: `${(100 * Number(n)) / max}%`, background: "var(--sx-accent)" }} /></span><span style={{ textAlign: "right" }}>{n}</span></div>))}
              <p className="vp-mini" style={{ margin: 0 }}>{f.data?.note}</p>
            </div>)}
        </Card>
        <Card title="Make a tracked link">
          <div className="vp-stack">
            <Field label="Where it points" value={target} onChange={setTarget} maxLength={800} hint={`Allowed hosts: ${(integ.data?.allow_hosts ?? []).join(", ") || "none set"}`} />
            <Field label="Campaign" value={campaign} onChange={setCampaign} maxLength={80} hint="For example invoice timing" />
            <Field label="Source" value={source} onChange={setSource} maxLength={60} />
            <Button variant="primary" onClick={async () => { await make.mutateAsync(); }} disabled={!canWrite || !campaign.trim()} disabledReason={!canWrite ? "Viewers cannot make links" : "Name the campaign"}>Make the link</Button>
          </div>
        </Card>
      </div>
      {!f.data ? <TableSkeleton rows={6} columns={6} /> : f.data.links.length === 0 ? <EmptyState title="No tracked links yet" body="Make a link above and use it in a post." /> : <div className="vp-noopen"><DataTable label="Links" rows={f.data.links} rowKey={(r) => String(r.id)} columns={columns} height={380} /></div>}
      <Card title="Short links you have made">
        <div className="vp-stack">{(links.data ?? []).slice(0, 8).map((l) => <div key={l.id} className="vp-field" style={{ gridTemplateColumns: "minmax(0, 1fr) auto" }}><span className="vp-link-row"><strong>{linkUrl(l)}</strong><br /><span className="vp-mini">{l.campaign} · {l.source}</span></span><CopyButton value={linkUrl(l)} label={`Copy ${l.code}`} /></div>)}</div>
        <p className="vp-mini">Lead events arrive on a signed webhook (POST /api/webhooks/lead, header x-penlark-signature). <Badge>Setup in the connect guide</Badge></p>
      </Card>
    </div>
  );
}
