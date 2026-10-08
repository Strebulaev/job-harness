# bootstrap-generated: true
id,title,tags,status
0001,"Golden sets: ≥30 jobs, ≥60 claims, ≥50 emails; metric floors","eval, testing",active
0002,Out-of-scope list: what the system must never build,"compliance, safety",active
0003,"Required docs: README, DECISIONS, SOURCES, PROMPTS, RUNBOOK",docs,active
0004,Router hard filters all run and accumulate reasons,routing,active
0005,Overlap filter also runs for onsite jobs,routing,active
0006,"Unknown compensation with high hours is rejected, not asked",routing,active
0007,Archetype must_have keywords match whole words only,routing,active
0008,"Router golden baseline: P=1.0, R=0.933, archetype acc=0.867","routing, eval",active
0009,Golden loaders skip baseline.json and expected_downgrades.json,eval,active
0010,We Work Remotely RSS feed permits programmatic reads,"ingest, compliance",active
0011,"LLM temperatures: parse/classify/judge 0.0, compose 0.4",llm,active
0012,"CI enforces ruff, mypy strict, pytest, init/validate, router baseline","ci, testing",active
0013,config/config.yaml model ids are still placeholders,"llm, config",active
0014,Telegram bot chats are not end-to-end encrypted,safety,active
superjob-api-shape-unverified,SuperJob API v2 shape is assumed not verified against official docs,"ingest, compliance",draft
docs-manifest,Docs manifest: doc sections mapped to content and watch paths,docs,active
