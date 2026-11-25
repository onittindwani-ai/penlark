# Architecture

```
Browser -> Next.js web app (apps/web) -> proxy adds the session cookie -> FastAPI (apps/api)
                                                                         |-> SQLite or Postgres (<!--n:tables-->15<!--/n--> vp_ tables on the shared base)
                                                                         |-> worker (learning loop hourly, Find ideas when asked)
                                                                         |-> scheduler adapter (file export, Postiz, Buffer, Metricool)
Public: /r/<code> (tracked link) and /api/webhooks/lead (signed)
```

## Where the logic lives (`apps/api/src/penlark`)
| Module | Job |
|---|---|
| `textstats.py`, `dimensions.py` | Measure a text: sentences, punctuation, contractions, openers, vocabulary. Plain meanings and advice for each dimension. |
| `fingerprint.py` | Build the profile from samples: centre and tolerance per dimension, word habits, openers, favourite words, examples, the radar. |
| `match.py` | The voice match score by code, per dimension, with the sentences that pull it down. |
| `house_rules.py`, `safe_regex.py` | Banned phrases and patterns, dashes, reading level, the claims check; and the check that refuses a pattern that could take far too long. |
| `ingest.py` | Readers for markdown, text, PDF, transcripts, LinkedIn CSV, X archive. |
| `guide.py`, `writers.py` | The offline guide and draft templates (labelled, not a language model), and the model path in `model_tasks.py` (voice guide, draft variants, idea finder; code re scores every draft). |
| `ideas.py` | Notes to ranked ideas with verified quotes. Bounded: the newest 1,000 notes, 1 million characters, 30 rarest words per note. |
| `dbsetup.py` | The database engine. On SQLite a request that can write takes the write lock first, so the audit chain cannot fork; reads never wait for it. Also the check that a SQLite file is not older than the code, and the indexes that a later version added to a file from an earlier one. |
| `learning.py` | CSV import with mapping, trait comparison, permutation test. |
| `attribution.py`, `experiments.py` | Tracked links, allow list, signature check, funnel, A/B analysis. |
| `adapters/schedulers.py`, `registry.py` | The scheduler adapters and their tiers. |
| `service.py`, `world.py`, `demo.py` | Orchestration (including the fingerprint that ties an approval to its exact text, the link check and the hold on a send nobody can vouch for), the demo world, reset. A call that waits (a scheduling tool, a model, the idea finder) lets go of the SQLite write lock first. |
| `config.py`, `datadir.py`, `dburl.py`, `admin.py` | Settings and what is wrong with them, where the demo data folder is, which database the command line tools open, and `python -m penlark.admin`. |
| `purge.py`, `proxywatch.py` | Taking a note, sample, draft, voice or imported rows out for good with every copy of their words the app made; and the notice that requests come through a proxy the server does not trust. |
| `api/` | Routes: read, write, delete (owner only), admin, public, demo, auth. Request bodies share `api/bodies.py`, which takes NUL characters out of every text. |

The shared base (`packages/core-py`, `packages/ui-kit`) is a copy and is never edited here. Version in `packages/BASE_MANIFEST.json`.

## Rules the code keeps
1. Style numbers and scores come from code, never from a model.
2. A model (if one is ever wired) only writes text, and its output passes the same checks.
3. Every outside write goes through `guard_write` (draft mode and the kill switch stop it) or, for the file export, the kill switch check. Both read the switches set in the app from the database.
4. Every change is audited. Every approval needs a second person and is for the exact text it was asked for.

API: <!--n:api_paths-->60<!--/n--> paths and <!--n:api_operations-->72<!--/n--> operations in `openapi.json`.
