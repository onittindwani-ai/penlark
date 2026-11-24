# Instructions for Claude Code in this repo

- Read `docs/00-START-HERE.md` and `docs/ARCHITECTURE.md` first.
- Never edit `packages/`: it is a copy of the shared base. Report a needed change instead.
- Never invent a number, a result, a client or a personal story in a draft. Leave a [BRACKET].
- Nothing is sent without live mode, an approved draft and an explicit confirm. Keep `MODE=draft`.
- Style numbers and the voice match come from code. Do not replace them with a model.
- Held out files in `data/eval` and their `*_first_run.json` results are not edited or tuned against.
- Run `make test`, `python3 tools/check_docs.py` and `python3 tools/score_tools.py --check` before you say something works.
- No em dashes or en dashes in anything shipped. Plain words. Fictional examples are labelled.
- Use the recipe prompts in `prompts/` to connect a tool we did not build.
