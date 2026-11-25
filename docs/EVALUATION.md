# Evaluation

Independent sets written by agents who never saw the code are in `INDEPENDENT-EVAL.md` and are the honest numbers; the self written sets below are kept for comparison. Held out sets were written before the code they test, run once, and the first run was saved untouched in `data/eval/*_first_run.json`. Everything is fictional. Scores come from code, not a language model. Re run with `make seed-check`.

## Voice match (`tools/eval_voice.py`)
Three fictional authors (a terse founder, a warm teacher, a formal consultant), <!--n:seed.samples_per_author-->16<!--/n--> training samples each. <!--n:seed.heldout_texts-->40<!--/n--> held out texts: 8 per author, 8 by a fourth author the profiles never saw, 8 generic machine sounding texts.

| Result | Value |
|---|---|
| Right author ranked first | <!--n:eval.voice.correct-->24<!--/n--> of <!--n:eval.voice.of-->24<!--/n--> |
| Mean AUC (own text against everyone else's, per profile) | <!--n:eval.voice.auc-->0.975<!--/n--> (tobias 1.0, imani 0.969, gareth 0.957) |
| Mean own score against others | tobias 88 against 55, imani 82.5 against 60, gareth 86 against 62 |
| Fourth author, best profile score | <!--n:eval.voice.outsider_mean_best-->56.7<!--/n--> (assigned to imani 4, gareth 3, tobias 1) |
| Generic machine sounding text, best profile score | <!--n:eval.voice.generic_mean_best-->79.0<!--/n--> (7 of 8 went to the formal profile) |

Confusion pairs: none among the three authors. Honest caveats: the texts are short (30 to 90 words), one writer made all of them, and a formal profile does not reject generic corporate prose. The match is a style measure, not proof of a human voice.

## House rules and claims (`tools/eval_flags.py`)
<!--n:seed.heldout_drafts-->26<!--/n--> drafts with planted violations. Draft level: style precision <!--n:eval.flags.style_precision-->1.0<!--/n-->, recall <!--n:eval.flags.style_recall-->1.0<!--/n-->; claims precision <!--n:eval.flags.claim_precision-->1.0<!--/n-->, recall <!--n:eval.flags.claim_recall-->1.0<!--/n-->. This is optimistic: the drafts were written by the same team that wrote the phrase list and every violating draft contains a listed phrase. A paraphrase that is on no list is not caught (a test proves it).

## Ideas (`tools/eval_ideas.py`)
Held out notes from a different fictional business: <!--n:eval.ideas.themes_found-->2<!--/n--> of <!--n:eval.ideas.themes_total-->3<!--/n--> planted themes found, <!--n:eval.ideas.noise_leaked-->0<!--/n--> noise notes leaked into an idea, evidence quotes valid <!--n:eval.ideas.quotes_valid-->7<!--/n--> of <!--n:eval.ideas.quotes-->7<!--/n--> (must be 100 percent). The seed notes are a development set the finder was tuned on and are not an honest score: 2 of 4 themes there.

## Learning loop
On the <!--n:seed.posts-->60<!--/n--> planted posts the loop reported the planted long post penalty and the question opener lift at its strict bar, and missed other planted effects (low power at this size). It reported the planted emoji lead (3 posts, 3.2 times the base rate by luck) as "too few to say", never as a pattern. Tests: `apps/api/tests/test_engine.py`.

## Code
<!--n:tests.passed-->280<!--/n--> Python tests passed, <!--n:tests.skipped-->1<!--/n--> skipped (the Postgres cycle needs `TEST_POSTGRES_URL`), coverage <!--n:tests.coverage_percent-->94.8<!--/n--> percent. <!--n:e2e.tests-->45<!--/n--> browser tests.
