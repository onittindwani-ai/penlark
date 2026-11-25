/** Plain words for names the server uses inside. One place, so no screen shows a raw name like draft.approval_voided. */

const AUDIT_ACTION: Record<string, string> = {
  "approval.requested": "Approval asked for", "approval.approved": "Approved", "approval.rejected": "Rejected", "approval.withdrawn": "Approval withdrawn after an edit",
  "draft.created": "Draft written", "draft.approved": "Draft approved", "draft.rejected": "Draft rejected", "draft.approval_voided": "Approval voided by an edit", "draft.scheduled": "Draft planned on the calendar", "draft.exported": "Draft exported to a file", "draft.sent": "Draft sent to a scheduler", "draft.send_failed": "A send did not go through", "draft.edited": "Draft edited", "author.created": "Voice added", "idea.dropped": "Idea dropped", "schedule.removed": "Planned post removed", "rule.deleted": "House rule deleted", "experiment.created": "Experiment started", "experiment.updated": "Experiment counts changed",
  "ideas.refreshed": "Ideas found again", "ideas.model_proposed": "Ideas proposed by the language model", "note.added": "Note added",
  "link.created": "Tracked link made", "performance.imported": "Post numbers imported",
  "profile.built": "Voice profile built", "profile.guide_edited": "Voice guide edited", "profile.locked": "Voice profile locked",
  "rule.added": "House rule added", "rule.toggled": "House rule turned on or off", "sample.added": "Writing sample added", "sample.removed": "Writing sample removed", "sample.uploaded": "Writing file uploaded",
  "schedule.moved": "Planned post moved", "settings.kill_switch": "Kill switch changed", "settings.force_draft": "Draft mode changed", "demo.stress": "Demo rows added",
};
export const auditAction = (a: string) => AUDIT_ACTION[a] ?? a.replace(/[._]/g, " ");
/** "draft:2" as "Draft 2". Anything else is shown as it is. */
export const auditTarget = (t: string | null) => {
  if (!t) return "";
  const m = /^([a-z]+):(\d+)$/.exec(t);
  return m ? `${m[1]!.charAt(0).toUpperCase()}${m[1]!.slice(1)} ${m[2]}` : t;
};

export const DRAFT_STATUS: Record<string, string> = { draft: "draft", pending_approval: "waiting for approval", approved: "approved", scheduled: "planned", sending: "being sent", exported: "exported", published: "published", rejected: "rejected" };
export const SCHEDULE_STATUS: Record<string, string> = { planned: "planned", exported: "exported to a file", sent: "sent", published: "published" };
export const IDEA_BADGE = (status: string) => (status === "approved" ? "has a draft" : "");
/** An adapter name as a person writes it. */
export const ADAPTER_NAME: Record<string, string> = { seed: "Offline demo", export: "File export", postiz: "Postiz", buffer: "Buffer", metricool: "Metricool" };
export const CATEGORY_TITLE: Record<string, string> = { scheduler: "Scheduler (where an approved draft goes)" };
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
