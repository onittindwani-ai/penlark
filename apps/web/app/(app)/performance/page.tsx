"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AreaChart, Badge, Button, Card, DataTable, Dialog, EmptyState, Stat, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { FileDrop, LoadError, PageHead, Textarea } from "@/components/Parts";
import { useRole } from "@/lib/hooks";
import { plural } from "@/lib/labels";
import { get, post } from "@/lib/api";
import type { Learning, PerfRow, Trait } from "@/lib/types";

const NAME: Record<string, string> = { opens_with_question: "Opens with a question", number_in_first_line: "A number in the first line", has_number: "Uses a number", long_post_over_150_words: "Long post (over 150 words)", short_post_under_60_words: "Short post (under 60 words)", one_line_paragraphs: "Mostly one line paragraphs", asks_reader_a_question: "Asks the reader a question", uses_emoji: "Uses an emoji", uses_you: "Speaks to you or we", contains_link: "Contains a link", mentions_a_client: "Mentions a client" };

function TraitCard({ t }: { t: Trait }) {
  const total = t.with_n + t.without_n || 1;
  return (
    <div className="vp-trait" data-status={t.status}>
      <div className="sx-row" style={{ justifyContent: "space-between" }}><strong>{NAME[t.trait] ?? t.trait}</strong><Badge tone={t.status === "pattern" ? "accent" : t.status === "too_few" ? "warning" : "neutral"}>{t.status === "pattern" ? "a pattern in this data" : t.status === "too_few" ? "too few to say" : "no clear pattern"}</Badge></div>
      <div className="vp-size" role="img" aria-label={`${plural(t.with_n, "post")} with it, ${t.without_n} without`}><span style={{ width: `${(100 * t.with_n) / total}%` }} /><span style={{ width: `${(100 * t.without_n) / total}%` }} /></div>
      <span className="vp-mini">{plural(t.with_n, "post")} with it, {t.without_n} without{t.lift_percent !== null ? `. Rate ${t.with_rate}% against ${t.without_rate}% (${t.lift_percent > 0 ? "+" : ""}${t.lift_percent}%), p ${t.p}` : ""}.</span>
      <span className="vp-mini">{t.note}</span>
    </div>
  );
}

export default function PerformancePage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const NO = "Viewers cannot change anything";
  const rows = useQuery({ queryKey: ["performance"], queryFn: () => get<PerfRow[]>("/performance?limit=20000") });
  const learn = useQuery({ queryKey: ["learning"], queryFn: () => get<Learning>("/learning") });
  const [open, setOpen] = useState(false);
  const [csv, setCsv] = useState("");
  const [prev, setPrev] = useState<{ ok: boolean; rows: number; duplicates?: number; message?: string; problems: string[]; suggested: Record<string, string> } | null>(null);
  const check = useMutation({ mutationFn: () => post<NonNullable<typeof prev>>("/performance/import", { csv, preview: true }), onSuccess: setPrev, onError: (e: Error) => notify.error("Could not read the file", e.message) });
  const save = useMutation({ mutationFn: () => post("/performance/import", { csv, preview: false }), onSuccess: () => { notify.success("Imported."); setOpen(false); setCsv(""); setPrev(null); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Could not import", e.message) });
  const columns: Column<PerfRow>[] = [
    { key: "date", header: "Date", width: "110px", render: (r) => r.posted_on, sortValue: (r) => r.posted_on },
    { key: "text", header: "Post", width: "minmax(0, 3fr)", render: (r) => r.text.replace(/\s+/g, " ").slice(0, 90), sortValue: (r) => r.text },
    { key: "impressions", header: "Views", width: "90px", align: "right", sortValue: (r) => r.impressions },
    { key: "rate", header: "Engagement", width: "110px", align: "right", render: (r) => `${r.rate}%`, sortValue: (r) => r.rate },
  ];
  if (rows.isError || learn.isError) return <div className="vp-page"><PageHead title="Performance" /><LoadError error={rows.error ?? learn.error} onRetry={() => { rows.refetch(); learn.refetch(); }} what="performance" /></div>;
  const data = rows.data ?? [];
  const byMonth = Object.values(data.reduce<Record<string, { month: string; rate: number; n: number }>>((a, r) => { const m = r.posted_on.slice(0, 7) || "none"; (a[m] ??= { month: m, rate: 0, n: 0 }); a[m].rate += r.rate; a[m].n += 1; return a; }, {})).map((x) => ({ month: x.month, rate: Math.round((x.rate / x.n) * 100) / 100 })).sort((a, b) => a.month.localeCompare(b.month));
  const avg = data.length ? data.reduce((s, r) => s + r.rate, 0) / data.length : 0;
  return (
    <div className="vp-page">
      <PageHead title="Performance" sub="Import post numbers from a CSV. The learning loop compares posts and shows how many there were. It describes the past. It never says why a post worked." actions={<Button onClick={() => setOpen(true)} feedback={false} disabled={!canWrite} disabledReason={NO}>Import a CSV</Button>} />
      <div className="vp-stats">
        <Card><Stat label="Posts" value={data.length} /></Card>
        <Card><Stat label="Average engagement %" value={Math.round(avg * 100) / 100} format={(n) => n.toFixed(2)} /></Card>
        <Card><Stat label="Traits tested" value={learn.data?.tests_run ?? 0} /></Card>
      </div>
      {byMonth.length > 1 ? <Card title="Average engagement by month"><AreaChart data={byMonth} xKey="month" series={[{ key: "rate", label: "Engagement %" }]} height={220} /></Card> : null}
      <Card title="Learning loop">
        {!learn.data ? <TableSkeleton rows={3} columns={2} /> : learn.data.traits.length === 0 ? <EmptyState title="Not enough posts" body="Import at least 10 posts with their numbers." actionLabel={canWrite ? "Import a CSV" : undefined} onAction={() => setOpen(true)} /> : (
          <div className="vp-stack">
            {learn.data.warnings.map((w) => <p key={w} className="vp-flag vp-flag--claim">{w}</p>)}
            <p className="vp-mini" style={{ margin: 0 }}>{learn.data.n_posts} posts. Each trait needs at least 8 posts in both groups. {learn.data.tests_run} traits were tested at a strict bar (p under {learn.data.alpha}) because the more things you test, the more luck shows up as a pattern.</p>
            <div className="vp-cols">{learn.data.traits.map((t) => <TraitCard key={t.trait} t={t} />)}</div>
          </div>)}
      </Card>
      {!rows.data ? <TableSkeleton rows={8} columns={4} /> : <div className="vp-noopen"><DataTable label="Posts" rows={data} rowKey={(r) => String(r.id)} columns={columns} height={460} /></div>}
      <Dialog open={open} onOpenChange={setOpen} title="Import post numbers" description="Choose or paste a CSV with a header row. Columns for views (impressions), likes or reactions, comments, shares and the post text are found by name."
        actions={<><Button feedback={false} onClick={() => setOpen(false)}>Cancel</Button><Button onClick={async () => { await check.mutateAsync(); }} disabled={!csv.trim()} disabledReason="Paste a CSV first">Check the file</Button><Button variant="primary" onClick={async () => { await save.mutateAsync(); }} disabled={!prev?.ok || !prev.rows} disabledReason={prev?.ok ? "Nothing new to import" : "Check the file first"}>Import {plural(prev?.rows ?? 0, "post")}</Button></>}>
        <div className="vp-stack">
          <FileDrop accept=".csv,text/csv,text/plain" label="Choose a CSV file or drop it here" hint="Or paste the text below. Up to 5 MB." onFile={async (f) => { if (f.size > 5_000_000) { notify.error("That file is too big", "The limit is 5 MB."); return; } setCsv(await f.text()); setPrev(null); }} />
          <Textarea label="CSV text" value={csv} onChange={(e) => { setCsv(e.target.value); setPrev(null); }} />
          {prev ? (prev.ok ? <p className="vp-flag vp-flag--claim" role="status" style={{ background: "var(--sx-success-bg)", borderColor: "var(--sx-success)" }}>{prev.rows} rows are new. {prev.duplicates ? `${prev.duplicates} already in your numbers, skipped. ` : ""}Columns found: {Object.entries(prev.suggested).map(([k, v]) => `${k} = ${v}`).join(", ")}.{prev.problems.length ? ` ${prev.problems.length} rows skipped: ${prev.problems[0]}` : ""}</p> : <p className="vp-flag vp-flag--rule" role="alert">{prev.message}</p>) : null}
        </div>
      </Dialog>
    </div>
  );
}
