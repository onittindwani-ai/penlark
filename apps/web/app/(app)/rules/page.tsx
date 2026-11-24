"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, DataTable, Field, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { api, get, post, put } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Rule, RulesResp } from "@/lib/types";

export default function RulesPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const NO = "Viewers cannot change anything";
  const q = useQuery({ queryKey: ["rules"], queryFn: () => get<RulesResp>("/rules") });
  const [kind, setKind] = useState("phrase");
  const [value, setValue] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["rules"] });
  const add = useMutation({ mutationFn: () => post("/rules", { kind, value, note: "Added by you." }), onSuccess: () => { notify.success("Rule added. It applies to every draft from now on."); setValue(""); refresh(); }, onError: (e: Error) => notify.error("Could not add the rule", e.message) });
  const toggle = useMutation({ mutationFn: (r: Rule) => put(`/rules/${r.id}`, { enabled: !r.enabled }), onSuccess: (_x, r) => { notify.undo(r.enabled ? "Rule turned off." : "Rule turned on.", async () => { await put(`/rules/${r.id}`, { enabled: r.enabled }); refresh(); }); refresh(); }, onError: (e: Error) => notify.error("Could not change the rule", e.message) });
  const remove = useMutation({ mutationFn: (r: Rule) => api(`/rules/${r.id}`, { method: "DELETE" }), onSuccess: () => { notify.info("Rule deleted."); refresh(); }, onError: (e: Error) => notify.error("Could not delete", e.message) });
  const columns: Column<Rule>[] = [
    { key: "value", header: "Banned", width: "minmax(0, 2fr)", render: (r) => <span style={{ opacity: r.enabled ? 1 : 0.5 }}>{r.value}</span>, sortValue: (r) => r.value },
    { key: "kind", header: "Kind", width: "90px", sortValue: (r) => r.kind },
    { key: "src", header: "Source", width: "110px", render: (r) => <Badge tone={r.builtin ? "neutral" : "accent"}>{r.builtin ? "built in" : "yours"}</Badge>, sortValue: (r) => String(r.builtin) },
    { key: "on", header: "State", width: "90px", render: (r) => (r.enabled ? "on" : "off"), sortValue: (r) => String(r.enabled) },
  ];
  if (q.isError) return <div className="vp-page"><PageHead title="House rules" /><LoadError error={q.error} onRetry={() => q.refetch()} what="the house rules" /></div>;
  const st = q.data?.settings;
  return (
    <div className="vp-page">
      <PageHead title="House rules" sub="Checked on every keystroke in the Studio. Built in phrases can be turned off, not deleted. Add your own banned words and patterns." />
      <div className="vp-stats">
        <Card title="Dashes" headingLevel={3}>{st ? (st.no_dashes ? "Banned" : "Allowed") : "..."}</Card>
        <Card title="Reading level" headingLevel={3}>{st ? `Grade ${st.max_reading_grade} or lower` : "..."}</Card>
        <Card title="Minimum match" headingLevel={3}>{st ? `${st.min_voice_match} to go to approval` : "..."}</Card>
        <Card title="Facts need a source" headingLevel={3}>{st ? (st.require_sources ? "Always" : "Off") : "..."}</Card>
      </div>
      <p className="vp-mini" style={{ margin: 0 }}>These four settings are environment variables on the server (see the environment guide). Phrases and patterns are edited here.</p>
      <div className="vp-two">
        {!q.data ? <TableSkeleton rows={8} columns={4} /> : (
          <div className="vp-act-168 vp-noopen"><DataTable label="Banned phrases and patterns" rows={q.data.rules} rowKey={(r) => String(r.id)} columns={columns} height={460} rowActions={(r) => (
            <span className="sx-row"><Button size="sm" disabled={!canWrite} disabledReason={NO} onClick={async () => { await toggle.mutateAsync(r); }} aria-label={`${r.enabled ? "Turn off" : "Turn on"} ${r.value}`}>{r.enabled ? "Turn off" : "Turn on"}</Button>{!r.builtin ? <Button size="sm" variant="ghost" disabled={!canWrite} disabledReason={NO} onClick={async () => { await remove.mutateAsync(r); }} aria-label={`Delete ${r.value}`}>Delete</Button> : null}</span>)} /></div>)}
        <Card title="Add a rule">
          <div className="vp-stack">
            <select className="vp-select" aria-label="Kind of rule" value={kind} onChange={(e) => setKind(e.target.value)}><option value="phrase">A phrase</option><option value="pattern">A pattern (regular expression)</option></select>
            <Field label={kind === "phrase" ? "Phrase to ban" : "Pattern"} value={value} onChange={setValue} maxLength={200} hint={kind === "phrase" ? "Matched in any case, for example: circle back" : "For example: \\bsynerg\\w+"} />
            <Button variant="primary" onClick={async () => { await add.mutateAsync(); }} disabled={!canWrite || value.trim().length < 2} disabledReason={!canWrite ? NO : "Type at least two characters"}>Add rule</Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
