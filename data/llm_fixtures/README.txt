Recorded from a LOCAL MOCK server that answers with the offline stand in. Not answers of a real model.
They prove the replay path and the request shape only. Replay with LLM_BACKEND=fixture LLM_FIXTURES_DIR=data/llm_fixtures GUIDE_WRITER=model DRAFT_WRITER=model IDEA_FINDER=model.
Regenerate: python tools/record_llm_fixtures.py
