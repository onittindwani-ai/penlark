"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, CalendarDays, ClipboardCheck, FlaskConical, Fingerprint, Lightbulb, Library, ListChecks, LogOut, Pause, PenLine, Plug, ShieldCheck, Target } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell, Badge, Button, CommandPalette, ConfirmDialog, notify, useTheme, type PaletteItem } from "@sendora/ui-kit";
import { useBlockStrayFileDrops } from "@/components/Parts";
import { api, get, post } from "@/lib/api";
import { useLiveRefresh, useMe, useRole, useSettings } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const NAV = [
  { id: "/", label: "Studio", icon: PenLine },
  { id: "/ideas", label: "Ideas", icon: Lightbulb },
  { id: "/calendar", label: "Calendar", icon: CalendarDays },
  { id: "/voice", label: "Voice profile", icon: Fingerprint },
  { id: "/library", label: "Library", icon: Library },
  { id: "/rules", label: "House rules", icon: ListChecks },
  { id: "/performance", label: "Performance", icon: BarChart3 },
  { id: "/attribution", label: "Attribution", icon: Target },
  { id: "/experiments", label: "Experiments", icon: FlaskConical },
  { id: "/integrations", label: "Integrations", icon: Plug },
  { id: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { id: "/audit", label: "Audit log", icon: ShieldCheck },
];

export function AppFrame({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const me = useMe();
  const { canWrite, owner } = useRole();
  const settings = useSettings();
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") });
  const { setChoice } = useTheme();
  const [palette, setPalette] = useState(false);
  const [confirmKill, setConfirmKill] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  useLiveRefresh();
  useBlockStrayFileDrops();
  const killOn = !!settings.data?.kill_switch;
  const active = NAV.find((n) => (n.id === "/" ? path === "/" : path.startsWith(n.id)))?.id ?? "/";
  const demo = me.data?.demo_mode ?? false;
  const clock = useQuery({ queryKey: ["clock"], queryFn: () => get<{ now: string }>("/demo/state"), enabled: demo });
  const demoDate = clock.data ? new Date(`${clock.data.now.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) : "";
  const refresh = () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  const run = useMutation({ mutationFn: () => post("/demo/tick"), onSuccess: () => { notify.success("Ran the jobs: ideas were found again and what the posts say was worked out again."); refresh(); }, onError: (e: Error) => notify.error("The run failed", e.message) });
  const advance = useMutation({ mutationFn: (h: number) => post("/demo/advance", { hours: h }), onSuccess: () => { notify.info("Moved the demo clock forward one day."); refresh(); }, onError: (e: Error) => notify.error("Could not move the clock", e.message) });
  const toggleKill = useMutation({ mutationFn: (on: boolean) => post("/settings", { kill_switch: on }), onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["settings"] }); }, onError: (e: Error) => notify.error("Could not change the kill switch", e.message) });
  const reset = useMutation({ mutationFn: () => post("/demo/reset"), onSuccess: () => { notify.success("Demo data reset."); refresh(); }, onError: (e: Error) => notify.error("Could not reset", e.message) });
  const signOut = () => void api("/session", { method: "DELETE" }).catch(() => null).then(() => window.location.assign("/login"));

  // The palette lists "G then 1" to "G then 9" next to the first nine pages, so they have to work: press G, then the number, outside text fields and dialogs.
  useEffect(() => {
    let armed = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.closest("[role=dialog], [role=alertdialog]"))) return;
      if (e.key.toLowerCase() === "g") { armed = Date.now(); return; }
      if (armed && Date.now() - armed < 1500 && /^[1-9]$/.test(e.key)) { armed = 0; const target = NAV[Number(e.key) - 1]; if (target) router.push(target.id); return; }
      armed = 0;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const items: PaletteItem[] = useMemo(() => [
    ...NAV.map((n, i) => ({ id: `go-${n.id}`, label: `Go to ${n.label}`, group: "Pages", shortcut: i < 9 ? ["G", String(i + 1)] : undefined, onSelect: () => router.push(n.id) })),
    { id: "signout", label: "Sign out", group: "Account", onSelect: signOut },
    ...(owner ? [killOn ? { id: "kill", label: "Turn the kill switch off", group: "Account", onSelect: () => toggleKill.mutate(false) } : { id: "kill", label: "Pause all (kill switch)", group: "Account", onSelect: () => setConfirmKill(true) }] : []),
    { id: "dark", label: "Switch to dark theme", group: "Actions", onSelect: () => setChoice("dark") },
    { id: "light", label: "Switch to light theme", group: "Actions", onSelect: () => setChoice("light") },
    ...(demo && canWrite ? [{ id: "run", label: "Run the jobs now", group: "Demo", onSelect: () => void run.mutateAsync() }, { id: "adv", label: "Move the demo clock forward one day", group: "Demo", onSelect: () => void advance.mutateAsync(24) }] : []),
    ...(demo && owner ? [{ id: "reset", label: "Reset the demo data", group: "Demo", onSelect: () => setConfirmReset(true) }] : []),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [router, setChoice, demo, run, advance, owner, canWrite, killOn, toggleKill]);
  const s = settings.data, o = overview.data;
  return (
    <>
      {s?.kill_switch ? (
        <div className="vp-banner vp-banner--danger" role="status"><strong>Kill switch is on.</strong> <span className="vp-hide-sm vp-grow">Nothing is sent to a scheduler. Writing, approving and exporting to a file still work.</span><span className="vp-grow vp-show-sm" /> <Button size="sm" variant="ghost" disabled={!owner} disabledReason="Only the owner can turn it off" onClick={async () => { await toggleKill.mutateAsync(false); }}>Turn it off</Button></div>
      ) : s && demo ? (
        <div className="vp-banner vp-banner--info" role="status"><strong>Demo mode.</strong> <span className="vp-grow vp-hide-sm">Fictional authors and posts. Offline templates write the drafts, not a language model. {demoDate ? `Demo date: ${demoDate}.` : ""}</span><span className="vp-grow vp-show-sm" />
          <Button size="sm" variant="primary" disabled={!canWrite} disabledReason="Viewers cannot run jobs" onClick={async () => { await run.mutateAsync(); }}>Run now</Button>
          <Button size="sm" disabled={!canWrite} disabledReason="Viewers cannot move the clock" onClick={async () => { await advance.mutateAsync(24); }}>+1 day</Button></div>
      ) : s?.effective_mode === "draft" ? (
        <div className="vp-banner" role="status"><strong>Draft mode.</strong> <span className="vp-hide-sm">Nothing is sent to a scheduler. Exports to a file still work.</span></div>
      ) : s ? (
        <div className="vp-banner vp-banner--live" role="status"><strong>Live.</strong> <span className="vp-hide-sm">A scheduler call needs an approved draft and a confirm each time.</span></div>
      ) : (
        <div className="vp-banner vp-banner--info" role="status">Checking the mode...</div>
      )}
      <AppShell
        productName="Penlark"
        nav={NAV.map((n) => ({ ...n, count: n.id === "/ideas" ? o?.ideas_inbox || undefined : n.id === "/approvals" ? o?.pending_approvals || undefined : undefined }))}
        activeId={active}
        onNavigate={(id) => router.push(id)}
        onOpenPalette={() => setPalette(true)}
        breadcrumbs={["Penlark", NAV.find((n) => n.id === active)?.label ?? ""]}
        topRight={
          <>
            {owner ? <Button size="sm" variant="ghost" feedback={false} className="vp-iconify" aria-label={killOn ? "Turn it off (kill switch)" : "Pause all"} onClick={() => (killOn ? toggleKill.mutate(false) : setConfirmKill(true))}><Pause size={14} aria-hidden /><span className="vp-hide-sm">{killOn ? "Turn it off" : "Pause all"}</span></Button> : null}
            {me.data ? <span className="vp-hide-sm"><Badge tone="accent">{me.data.role}</Badge></span> : null}
            <Button size="sm" variant="ghost" feedback={false} className="vp-iconify" aria-label="Sign out" onClick={signOut}><LogOut size={14} aria-hidden /><span className="vp-hide-sm">Sign out</span></Button>
          </>
        }
      >
        {children}
      </AppShell>
      <CommandPalette items={items} open={palette} onOpenChange={setPalette} placeholder="Go to a page or run an action" />
      <ConfirmDialog open={confirmKill} onOpenChange={setConfirmKill} title="Pause all sending?" description="The kill switch stops every send to a scheduler at once. Writing, approving and exporting to a file keep working. You can turn it off again from the banner or the top bar." confirmLabel="Pause all" destructive onConfirm={() => void toggleKill.mutateAsync(true)} />
      <ConfirmDialog open={confirmReset} onOpenChange={setConfirmReset} title="Reset the demo?" description="This puts the fictional seed data back and clears everything you did in the demo." confirmLabel="Reset" destructive onConfirm={() => void reset.mutateAsync()} />
    </>
  );
}
