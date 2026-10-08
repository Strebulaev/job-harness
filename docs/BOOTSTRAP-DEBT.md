<!-- bootstrap-generated: true -->
# Knowledge debt and skill-gap proposals

Produced by `bootstrap` on 2026-10-08. Proposals only; the team decides adoption.

## 1. Undeclared guardrails

No hand-written guardrails existed. The 5 seeded guardrails in `docs/guardrails/` have `governed-by: TBD` and `grounded-in: TBD`. Adopt each with a decision, or delete it. `no-redundant-guardrails` and `no-unenforced-guardrail` are about go-getter's own skills and likely don't apply here.

## 2. Facts with no governing decision (`governed-by: TBD`)

| Fact | Proposed governing decision |
|---|---|
| 0002 out-of-scope-list | New: spec §21 is binding scope |
| 0004–0007 router behavior | New: router hard-filter semantics follow spec §11.3 and golden-set expectations |
| 0009 baseline-json-excluded | Same as above, or fold into 0005 |
| 0011 llm-role-temperatures | New: temperatures per spec §5 |
| 0012 ci-enforced-checks | New: spec §0 / §18 CI gates |

## 3. Rules already enforced (fitness functions)

- CI (`.github/workflows/ci.yml`): `ruff check`, `mypy` strict, `pytest tests/unit tests/integration`, `jh init` + `jh profile validate`, router golden baseline (precision drop >3 pts fails). Fact 0012, decision 0005.
- Settings: unknown config keys are errors (`src/jobharness/settings.py`).
- Runtime: state machines (`src/jobharness/db/state_machine.py`); human `approve` before send.

## 4. Rules that could be automated but aren't

| Rule | Why not automated | Governing decision |
|---|---|---|
| Released prompts are immutable (new version per change) | No CI check against git history | TBD (spec §12) |
| Prompt, model or router-weight change ships with an eval-run artifact | Convention in PR review only | 0005 |
| Each required doc has its spec-named sections | Plan lists greps; none in CI | 0006 |
| Tests never hit a real LLM provider | No network-blocking fixture | TBD (spec §12, §18) |
| `send.autosend.enabled` defaults to `false` | No default-value test known | TBD (spec §2) |
| No secrets committed | No secret scanner in CI | TBD (spec §16) |
| Milestone N+1 starts only after N acceptance passes in CI | Process rule; no branch protection | 0001 |
| Claims and email eval suites gate CI | Planned for M5/M6; CI runs router only | 0005 |

## 5. Skill-gap proposals

Highest priority first (irreversible or public-facing claims).

1. **Compliance** (Compliance Reviewer). Owns truthfulness, source ToS, PII and AI-tools/NDA records. Constraint: no document content outside `profile.yaml`. Fitness candidate: G1 gate plus the adversarial corruption tests planned in M5-3.
2. **Test and eval verification** (QA/Test Owner). Owns golden sets, gates, baselines. Constraint: tests run offline with `FakeProvider`. Fitness candidate: pytest fixture that blocks network sockets.
3. **Pipeline and release** (Release Engineer). Owns CI and M8 Docker packaging. Constraint: no milestone N+1 work before N is green. Fitness candidate: branch protection requiring the `quality` job.
4. **Build tooling** (Build Engineer). Owns the Python 3.12 / uv toolchain. Constraint: `requires-python >=3.12,<3.13`. Fitness candidate: CI `uv sync --locked`.
5. **Product scope** (Product Strategist). Owns milestones, archetypes, positioning. Constraint: spec §21 out-of-scope list. Fitness candidate: compare `jh` command list to spec §14.

No recurring manual process lacks a written procedure (`docs/RUNBOOK.md` covers it).

## 6. Classification flags

- 0009: D1, D3, D4, D6 read as process-track but D9 forces product.
- 0010: knowledge layout is process-like; kept product under D9.
- 0011, 0012: drafts mirroring open items O3 and O4; need Principal sign-off.
- Spec F4/F5 from `docs/DECISIONS.md` were not stubbed; they restate 0007 and 0008.
