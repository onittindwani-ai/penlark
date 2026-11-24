# Recipes for tools we did not build

Use these when your scheduler or link tool is not Postiz, Buffer or Metricool.

## A new scheduler adapter
```
Read apps/api/src/penlark/adapters/schedulers.py and mock/scheduler_mocks.py. Write an adapter for <tool> from its current public API docs (cite the URL and date in docs/facts/<tool>.md). It must refuse to send unless the draft is approved, confirm is true and guard_write allows it, default to saving a draft, use safe_base_url, and have a mock server and tests. Register it in registry.py as tier B. Mark it UNVERIFIED live.
```

## Import clicks from another link tool
```
Read apps/api/src/penlark/attribution.py. Write a CSV importer for the click export of <tool> that adds Click rows to the matching Link by short code. Do not change the redirect or the allow list. Add tests.
```
