# Contributing

1. Set up with `docs/05-RUN-LOCALLY.md` (`make install`), then `make test` and `pnpm e2e` before you open a change.
2. Do not edit `packages/` (a copy of the shared base).
3. A new check needs a test. A new number in the docs comes from `data/counts.json` (`python3 tools/make_counts.py`, then `python3 tools/check_docs.py`). `python3 tools/check_docs.py` fails when `data/counts.json` no longer agrees with the files, and `python3 tools/check_counts.py` also compares the number of tests with the number recorded.
4. Never edit or tune against the held out files in `data/eval`. Add a new held out set instead.
5. Plain words, no em or en dashes, sample examples labelled.
