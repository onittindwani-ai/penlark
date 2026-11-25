# Limits and honest notes

- **The offline writer is templates.** It builds a skeleton and leaves brackets. It is not a language model, so a draft is only as good as what you add. The live model path (`LLM_BACKEND=anthropic`) is real code tested against a local fake server and recorded fixtures, and was never run with a real key: UNVERIFIED. A model draft is re scored by code and flagged, never auto approved, and the approval request refuses a draft under the minimum voice match.
- **The voice match is a style measure, not a taste judge.** It says how close the measured habits are to the profile. It cannot tell if the writing is good or true.
- **Held out numbers are from short, fictional texts** (<!--n:eval.voice.correct-->24<!--/n--> of <!--n:eval.voice.of-->24<!--/n--> correct author, mean AUC <!--n:eval.voice.auc-->0.975<!--/n-->). The same person wrote the samples and the test texts. A formal profile gave generic machine sounding prose a mean best score of <!--n:eval.voice.generic_mean_best-->79.0<!--/n-->, so a high match is not proof of a human voice. On two independent sets generic text still averaged about 61 (4 to 5 of 10 above the minimum of 60) and a punchy outsider passed the voice match 10 of 10; the house rules stopped all generic text. See `INDEPENDENT-EVAL.md`.
- **The banned phrase list catches what it lists.** A paraphrase such as "Turbocharge the potential of your cash flow" alone is not caught. Add your own phrases.
- **The claims check is strict but literal.** A number must appear in an attached note. An experience claim needs a person to link a note. It cannot check that a note is true.
- **The idea finder is rules.** On held out notes it found <!--n:eval.ideas.themes_found-->2<!--/n--> of <!--n:eval.ideas.themes_total-->3<!--/n--> planted themes and leaked <!--n:eval.ideas.noise_leaked-->0<!--/n--> noise notes. Every evidence quote is verbatim (<!--n:eval.ideas.quotes_valid-->7<!--/n--> of <!--n:eval.ideas.quotes-->7<!--/n-->).
- **The learning loop describes, it does not explain.** With 60 posts it can miss real effects and the strict bar is on purpose. A pattern is a lead for an experiment.
- **Attribution counts clicks.** People who see a post and type the address later are not counted.
- **Scheduler adapters are untested against the real services.** Metricool's request shape is from memory.
- **LinkedIn and X export layouts are from memory** and unverified against a fresh export.
- **SQLite is the tested path for the full suites.** The migration was run up, down and up on Postgres 17 only.
- **Single tenant.** One workspace is one client.
- **Hosting.** The GitHub workflow builds the Docker images and starts the compose stack on a GitHub machine. No Vercel, Railway or Hetzner account was used, so the hosting guides are UNVERIFIED and the Caddy and backup files were never run on a real server.
- **A send that is cut off.** A draft is marked "being sent" before the scheduling tool is called. If the app stops at that moment nothing says whether the post was made: the draft is released after 30 minutes and the audit log says so, so check the scheduling tool before sending again.
- **PDFs.** A PDF is read inside the API process, with a cap of 8 MB and 200 pages. A hostile PDF can still make that request slow.
- **Rate limits are per process.** They are not shared between several API processes.
- **Two lead events at the same instant** with the same `lead_ref` can both be counted: there is no database rule against it.
- Not done: screen reader testing, a run on a real host, an independent security test.
