export interface Me { user: string; role: "owner" | "approver" | "viewer"; demo_mode: boolean }
export interface Settings { mode: string; effective_mode: string; kill_switch: boolean; demo_mode: boolean; problems: string[]; writer: string; scheduler: string; rules: { no_dashes: boolean; max_reading_grade: number; min_voice_match: number } }
export interface Overview { drafts: Record<string, number>; ideas_inbox: number; pending_approvals: number; scheduled: number; posts: number; engagement_rate: number; clicks: number; leads: number }
export interface Author { id: number; slug: string; name: string; about: string; samples: number; profile_version: number | null; locked: boolean }
export interface Sample { id: number; title: string; kind: string; source: string; words: number; text: string }
export interface RadarRow { key: string; label: string; own: number; own_raw: number; other?: number; other_raw?: number }
export interface Profile { id: number; author_id: number; version: number; guide: string; guide_source: string; locked: boolean; locked_by: string | null; diff: { key: string; label: string; before: number; after: number; change: string }[]; n_samples: number; created_at: string; stats: { favourite_words: string[]; signature_phrases: string[] }; radar: RadarRow[]; examples: Record<string, string[]>; dimension_meanings: Record<string, { label: string; meaning: string }> }
export interface ProfileResp { profile: Profile | null; versions: { id: number; version: number; locked: boolean; n_samples: number; created_at: string }[] }
export interface DimScore { key: string; label: string; score: number; value: number; centre: number; direction: string; advice: string | null }
export interface PullDown { start: number; end: number; text: string; delta: number }
export interface MatchResult { score: number; confidence: string; dimensions: DimScore[]; weakest: { key: string; label: string; score: number; advice: string }[]; pull_down: PullDown[]; n_words: number; ms: number; note: string }
export interface StyleFlag { kind: string; start: number; end: number; text: string; message: string }
export interface Claim { text: string; start: number; end: number; kinds: string[]; supported: boolean; source_note_id: number | null; message: string }
export interface Evaluation { match: MatchResult; rules: { style: StyleFlag[]; claims: Claim[]; unsupported_claims: Claim[]; ok: boolean; grade: number; words: number }; placeholders: string[]; links: string[]; profile_version: number | null; profile_locked: boolean; ready: boolean }
export interface Evidence { note_id: number; quote: string; start: number }
export interface Idea { id: number; title: string; score: number; parts: Record<string, number>; status: string; evidence: Evidence[]; note_ids: number[] }
export interface Variant { id: number; label: string; text: string; note: string }
export interface Draft { id: number; author_id: number; idea_id: number | null; kind: string; title: string; text: string; status: string; source_note_ids: number[]; claim_links: Record<string, number>; approval_id: number | null; created_by: string; updated_at: string; variants?: Variant[]; evaluation?: Evaluation; variant_scores?: { id: number; score: number }[] }
export interface Note { id: number; kind: string; who: string; text: string; occurred_on: string }
export interface ScheduleItem { id: number; draft_id: number; title: string; platform: string; run_on: string; status: string; adapter: string; detail: string }
export interface Rule { id: number; kind: string; value: string; note: string; builtin: boolean; enabled: boolean }
export interface RulesResp { rules: Rule[]; settings: { no_dashes: boolean; max_reading_grade: number; min_voice_match: number; require_sources: boolean } }
export interface PerfRow { id: number; post_ref: string; platform: string; posted_on: string; text: string; impressions: number; likes: number; comments: number; shares: number; clicks: number; rate: number }
export interface Trait { trait: string; with_n: number; without_n: number; status: string; with_rate: number | null; without_rate: number | null; lift_percent: number | null; p: number | null; note: string }
export interface Learning { n_posts: number; traits: Trait[]; tests_run: number; alpha?: number; warnings: string[] }
export interface LinkRow { id: number; code: string; short_url: string; short_path: string; base_is_default: boolean; target: string; post_ref: string; source: string; medium: string; campaign: string }
export interface FunnelRow { id: number; code: string; post_ref: string; campaign: string; source: string; clicks: number; unique_clicks: number; leads: number; customers: number; value: number; lead_rate: number | null }
export interface Funnel { links: FunnelRow[]; totals: { links: number; clicks: number; unique_clicks: number; leads: number; customers: number; value: number }; note: string }
export interface ExperimentRow { id: number; name: string; metric: string; a_label: string; b_label: string; a_n: number; a_hits: number; b_n: number; b_hits: number; status: string; result: { a_rate?: number; b_rate?: number; difference_points?: number; ci_low?: number; ci_high?: number; p?: number; verdict: string; note: string } }
export interface ApprovalRow { id: number; action: string; summary: string; risk: string; status: string; requested_by: string; decided_by: string | null; created_at: string; payload: Record<string, unknown>; preview: { draft_id: number; text: string; truncated: boolean; text_sha256: string; approved_text_sha256: string | null; status: string; author_id: number } | null; note?: string | null }
export interface AuditRow { id: number; actor: string; action: string; target: string | null; at: string; detail: Record<string, unknown> }
export interface Integrations { categories: string[]; adapters: { category: string; name: string; tier: string; live_verified: boolean; notes: string; selected: boolean; env_vars: string[]; configured: boolean }[]; demo_mode: boolean; allow_hosts: string[]; platform_note: string }
export interface CadenceWeek { week_start: string; week_end: string; on_track: boolean; platforms: Record<string, { planned: number; target: number; gap: number }> }
export interface Cadence { targets: Record<string, number>; weeks: CadenceWeek[] }
