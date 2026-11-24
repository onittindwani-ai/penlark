"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Badge, Button, Card, EmptyState, SegmentedControl, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { del, get, post, put } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { SCHEDULE_STATUS } from "@/lib/labels";
import type { Cadence, Draft, ScheduleItem } from "@/lib/types";

const PLATFORM_NAMES: Record<string, string> = { linkedin: "LinkedIn", x: "X", instagram: "Instagram", facebook: "Facebook", threads: "Threads", youtube: "YouTube", newsletter: "Newsletter", email: "Email" };

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
type Drag = { kind: "draft"; id: number } | { kind: "item"; id: number; from: string };

export default function CalendarPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const sched = useQuery({ queryKey: ["schedule"], queryFn: () => get<ScheduleItem[]>("/schedule") });
  const drafts = useQuery({ queryKey: ["drafts"], queryFn: () => get<Draft[]>("/drafts") });
  const now = useQuery({ queryKey: ["clock"], queryFn: () => get<{ now: string }>("/demo/state").catch(() => ({ now: new Date().toISOString() })) });
  const rhythm = useQuery({ queryKey: ["cadence"], queryFn: () => get<Cadence>("/cadence?weeks=4") });
  const [platform, setPlatform] = useState("linkedin");
  const [view, setView] = useState<"week" | "month">("week");
  const [offset, setOffset] = useState(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [moving, setMoving] = useState<{ id: number; value: string } | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["schedule"] }); qc.invalidateQueries({ queryKey: ["cadence"] }); qc.invalidateQueries({ queryKey: ["drafts"] }); qc.invalidateQueries({ queryKey: ["overview"] }); };
  const place = useMutation({ mutationFn: (v: { id: number; run_on: string }) => post(`/drafts/${v.id}/schedule`, { run_on: v.run_on, platform }), onSuccess: (_r, v) => { notify.success(`Planned on ${PLATFORM_NAMES[platform] ?? platform} for ${v.run_on}. Nothing is sent: this is a plan.`); refresh(); }, onError: (e: Error) => notify.error("Could not plan it", e.message) });
  const move = useMutation({
    mutationFn: (v: { id: number; run_on: string }) => put<{ from: string }>(`/schedule/${v.id}`, { run_on: v.run_on }),
    onSuccess: (r, v) => { notify.undo(`Moved to ${v.run_on}.`, async () => { await put(`/schedule/${v.id}`, { run_on: r.from }); refresh(); }); refresh(); }, onError: (e: Error) => notify.error("Could not move it", e.message),
  });
  const unplan = useMutation({ mutationFn: (id: number) => del(`/schedule/${id}`), onSuccess: () => { notify.info("Taken off the calendar."); refresh(); }, onError: (e: Error) => notify.error("Could not take it off", e.message) });
  const today = new Date((now.data?.now ?? new Date().toISOString()).slice(0, 10) + "T12:00:00");
  const days = useMemo(() => {
    const start = new Date(today);
    if (view === "week") { start.setDate(start.getDate() - ((start.getDay() + 6) % 7) + offset * 7); return Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; }); }
    start.setDate(1); start.setMonth(start.getMonth() + offset); const first = new Date(start); first.setDate(1 - ((first.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(first); d.setDate(first.getDate() + i); return d; });
  }, [view, offset, now.data]); // eslint-disable-line react-hooks/exhaustive-deps
  if (sched.isError || drafts.isError) return <div className="vp-page"><PageHead title="Calendar" /><LoadError error={sched.error ?? drafts.error} onRetry={() => { sched.refetch(); drafts.refetch(); }} what="the calendar" /></div>;
  if (!sched.data || !drafts.data) return <div className="vp-page"><PageHead title="Calendar" /><ListSkeleton /></div>;
  const planned = new Set(sched.data.map((s) => s.draft_id));
  const ready = drafts.data.filter((d) => d.status === "approved" && !planned.has(d.id));
  const drop = (day: string) => {
    if (!drag) return;
    if (drag.kind === "draft") place.mutate({ id: drag.id, run_on: day }); else if (drag.from !== day) move.mutate({ id: drag.id, run_on: day });
    setDrag(null); setOver(null);
  };
  const firstDay = iso(days[0]!);
  const hasTargets = Object.keys(rhythm.data?.targets ?? {}).length > 0;
  const shownWeek = hasTargets && rhythm.data ? (view === "week" ? rhythm.data.weeks.find((w) => w.week_start === firstDay) : rhythm.data.weeks[0]) : undefined;
  const short = (d: Date) => d.toLocaleString("en", { month: "short", day: "numeric" });
  const label = view === "week" ? `${short(days[0]!)} to ${short(days[6]!)}, ${days[6]!.getFullYear()}` : days[10]!.toLocaleString("en", { month: "long", year: "numeric" });
  return (
    <div className="vp-page">
      <PageHead title="Calendar" sub="Only approved drafts can be planned. Dragging plans a day, it never sends anything. Everything leaves through an export or an explicit send." actions={
        <><SegmentedControl label="View" value={view} onChange={(v) => { setView(v); setOffset(0); }} options={[{ value: "week", label: "Week" }, { value: "month", label: "Month" }]} />
          <Button size="sm" feedback={false} onClick={() => setOffset(offset - 1)} aria-label="Earlier">Earlier</Button><Button size="sm" feedback={false} disabled={offset === 0} disabledReason="Already showing today" onClick={() => setOffset(0)}>Today</Button><Button size="sm" feedback={false} onClick={() => setOffset(offset + 1)} aria-label="Later">Later</Button></>} />
      <div className="vp-two vp-two--rev">
        <Card title="Ready to plan" headingLevel={2}>
          {Object.keys(rhythm.data?.targets ?? {}).length > 0 ? (
            <div style={{ marginBottom: 13 }}><SegmentedControl label="Plan on" value={platform} onChange={setPlatform} options={Object.keys(rhythm.data!.targets).map((p) => ({ value: p, label: PLATFORM_NAMES[p] ?? p }))} /></div>) : null}
          {ready.length === 0 ? <EmptyState title="Nothing approved yet" body="Approve a draft on the Approvals page and it appears here." /> : (
            <div className="vp-stack">{ready.map((d) => (
              <div key={d.id} className="vp-chip-post" draggable={canWrite} data-dragging={drag?.kind === "draft" && drag.id === d.id} onDragStart={() => canWrite && setDrag({ kind: "draft", id: d.id })} onDragEnd={() => { setDrag(null); setOver(null); }} tabIndex={0} role="button" aria-label={`${d.title}. Press Enter to choose a day.`} onKeyDown={(e) => { if (e.key === "Enter" && canWrite) setMoving({ id: -d.id, value: iso(today) }); }}>
                <strong>{d.title}</strong><span className="vp-mini">{canWrite ? "approved, drag to a day or press Enter" : "approved"}</span></div>))}</div>)}
          {moving && moving.id < 0 ? (
            <div className="vp-toolbar" style={{ marginTop: 13 }}><label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Plan for</span><input className="vp-select" type="date" value={moving.value} onChange={(e) => setMoving({ ...moving, value: e.target.value })} /></label>
              <Button variant="primary" size="sm" onClick={async () => { await place.mutateAsync({ id: -moving.id, run_on: moving.value }); setMoving(null); }}>Plan it</Button><Button size="sm" feedback={false} onClick={() => setMoving(null)}>Cancel</Button></div>) : null}
        </Card>
        <Card title={label}>
          {shownWeek ? (
            <div className="vp-toolbar" style={{ marginBottom: 13, flexWrap: "wrap" }} aria-label="Posting rhythm">
              <span className="vp-mini">Rhythm for the week of {new Date(`${shownWeek.week_start}T12:00:00`).toLocaleDateString("en", { month: "short", day: "numeric" })}:</span>
              {Object.entries(shownWeek.platforms).map(([p, v]) => (
                <Badge key={p} tone={v.gap === 0 ? "success" : "neutral"}>{PLATFORM_NAMES[p] ?? p} {v.planned} of {v.target}</Badge>))}
              <span className="vp-mini">{rhythm.data!.weeks.filter((w) => !w.on_track).length} of the next {rhythm.data!.weeks.length} weeks still short. A plan, never a block.</span>
            </div>) : null}
          <div className="vp-cal">
            {days.map((d) => {
              const k = iso(d); const items = sched.data.filter((s) => s.run_on === k);
              return (
                <div key={k} className={`vp-day${over === k ? " vp-day--over" : ""}${view === "month" && d.getMonth() !== days[10]!.getMonth() ? " vp-day--out" : ""}`} data-day={k} onDragOver={(e) => { e.preventDefault(); setOver(k); }} onDragLeave={() => setOver(null)} onDrop={(e) => { e.preventDefault(); if (canWrite) drop(k); }}>
                  <span className="vp-day__n">{d.toLocaleString("en", { weekday: "short", day: "numeric", month: view === "week" ? "short" : undefined })}</span>
                  {items.map((s) => (
                    <div key={s.id} className="vp-chip-post" draggable={canWrite && s.status === "planned"} data-dragging={drag?.kind === "item" && drag.id === s.id} onDragStart={() => canWrite && setDrag({ kind: "item", id: s.id, from: s.run_on })} onDragEnd={() => { setDrag(null); setOver(null); }} tabIndex={0} role="button" aria-label={`${s.title}, ${PLATFORM_NAMES[s.platform] ?? s.platform}, ${SCHEDULE_STATUS[s.status] ?? s.status}.${canWrite && s.status === "planned" ? " Press Enter to move it." : ""}`} onKeyDown={(e) => { if (e.key === "Enter" && canWrite && s.status === "planned") setMoving({ id: s.id, value: s.run_on }); }}>
                      <strong>{s.title.slice(0, 38)}</strong><span className="vp-mini">{PLATFORM_NAMES[s.platform] ?? s.platform} <Badge tone={s.status === "planned" ? "accent" : "success"}>{SCHEDULE_STATUS[s.status] ?? s.status}</Badge></span></div>))}
                </div>);
            })}
          </div>
          {moving && moving.id > 0 ? (
            <div className="vp-toolbar" style={{ marginTop: 13 }}><label className="vp-stack" style={{ gap: 4 }}><span className="vp-mini">Move to</span><input className="vp-select" type="date" value={moving.value} onChange={(e) => setMoving({ ...moving, value: e.target.value })} /></label>
              <Button variant="primary" size="sm" onClick={async () => { await move.mutateAsync({ id: moving.id, run_on: moving.value }); setMoving(null); }}>Move</Button>
              <Button size="sm" onClick={async () => { await unplan.mutateAsync(moving.id); setMoving(null); }}>Take off the calendar</Button><Button size="sm" feedback={false} onClick={() => setMoving(null)}>Cancel</Button></div>) : null}
        </Card>
      </div>
    </div>
  );
}
