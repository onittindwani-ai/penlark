# Penlark specification

Penlark helps one person or one small team write posts, scripts, emails and newsletters in their own voice, with a person approving everything. It never publishes by itself. All people, companies, numbers and posts in the demo are sample data.

## Hard limits
1. It never invents personal facts or results. Any number, result, client or personal experience in a draft must link to a source note, or it is flagged "needs a source or a founder fact".
2. Nothing publishes without a person. The default is export to a file and copy. A publish call needs live mode, an approved draft and an explicit confirm, and the person who asked for approval cannot approve it.
3. It reads only text the user owns or provides. There is no scraping of other people's accounts.
4. Voice profiles are for the user's own writing. It does not imitate a named public person.
5. Platform APIs (LinkedIn, X, Instagram and others) need their own approvals from each platform. Penlark says so in the integration wizard.

## Entities (tables, prefix vp_)
Author, Sample, VoiceProfile (versioned, lockable), Note (calls, comments, emails, founder notes: the idea and claim source), Idea, Draft, Variant, Approval (the shared base approvals table, action `draft.approve`), Schedule, Performance, Link (tracked), Click, Conversion (attribution), Experiment, HouseRule, State.

## Pipeline
1. Ingest: markdown, text, PDF, a pasted post, a transcript file (plain, WebVTT, SRT, "Speaker: text"), a LinkedIn export (Shares.csv layout, UNVERIFIED), an X archive (tweets.js layout, UNVERIFIED), YouTube transcript text.
2. Build a voice profile. Code measures 14 style dimensions. A guide in plain words is written by the offline stand in (rules, NOT a language model) or by the live model path (`model_tasks.py`, run only against a local mock server, UNVERIFIED). The human edits the guide and locks the profile. Versions keep a diff.
3. Idea finder: notes become ranked ideas. Each idea carries a verbatim evidence quote that code proves exists in the source note. Score rubric in code.
4. Writers: the offline stand in fills templates from the evidence and the profile. Labelled "not a language model". The live path goes through the base LLM wrapper (`model_tasks.py`, UNVERIFIED live); code re scores every model draft.
5. Voice match score: pure code, 0 to 100, per dimension, with the sentences that pull the score down and a plain suggestion per dimension. Fast enough to run on every keystroke.
6. House rules: banned phrases (a long default list), banned patterns, no dashes option, reading level limits, and the claims check.
7. Approval queue, then export or schedule through the Postiz, Metricool or Buffer adapter (tier B, mocks) or a file export.
8. Performance import from CSV with a column mapping. Learning loop with sample sizes and a permutation test. No causation claims.
9. Attribution: tracked short links with UTM parameters, a click recorder, a redirect behind an allow list (never an open redirect), conversion events from a signed lead webhook.
10. Experiments: A/B variants with a simple honest significance note.

## Pages
Studio (signature: live voice match meter), Ideas, Calendar, Voice profile (signature: fingerprint radar), Library, House rules, Performance, Attribution, Experiments, Integrations, Approvals, Audit log.

## Evals (held out sets written first, first run saved untouched)
Voice match discrimination, house rule and claim flag precision and recall, evidence quote validity (must be 100 percent), idea ranking sanity, learning loop on a planted tiny sample.
