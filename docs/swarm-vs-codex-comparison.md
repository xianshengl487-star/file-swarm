# file-swarm vs Direct Codex Comparison

Date: 2026-06-27

This report compares the latest integrated `file-swarm` + `file-swarm-agent` capability against a direct Codex-style implementation on a medium-sized temporary project.

## Goal

Evaluate when a guarded multi-worker swarm is better than direct editing, and when direct editing remains the simpler choice.

## Skills Used

| Skill | Role |
| --- | --- |
| `$file-swarm` | File-level guarded patch orchestration |
| `$file-swarm-agent` | Structured action planning, dry-run execution, benchmark interpretation |

## Medium Project Shape

Temporary project name: `FlowKit`

Files:

```text
src/flowkit/orders.py
src/flowkit/inventory.py
src/flowkit/pricing.py
src/flowkit/reporting.py
src/flowkit/quality.py
src/flowkit/shipping.py
tests/test_flowkit.py
pyproject.toml
```

Task:

```text
Add a safe file-swarm marker function to each FlowKit source module while preserving all existing behavior and tests.
```

## Run A: file-swarm

Command shape:

```bash
file-swarm auto "<task>" --repo . --parallel 3 --dry-merge
file-swarm apply --run <run_id> --allow-dirty
python -m pytest -q
```

Configuration:

```text
3 mock slots
6 file-level workers
parallel=3
Patch Guard enabled
dry merge enabled
```

Observed result:

| Field | Value |
| --- | --- |
| run_id | `20260627040556577521` |
| auto orchestration time | `1.23s` |
| tasks | `6` |
| used slots | `mock_alpha`, `mock_beta`, `mock_gamma` |
| used models | `mock-model` |
| worker statuses | all `passed` |
| modified files | 6 source modules |
| apply | success |
| pytest | `1 passed` |
| recommendation | `recommend_apply: yes` |

Artifacts produced:

```text
dispatch_report.json
timeline.jsonl
transcripts/*.input.md
transcripts/*.output.md
transcripts/*.meta.json
guard_reports/*.guard.json
final.patch
codex_summary.md
apply_report.md
```

## Run B: Direct Codex-Style Edit

Implementation style:

```text
Directly edit the six source modules in one pass.
Run pytest.
Use git diff as the only patch artifact.
```

Observed result:

| Field | Value |
| --- | --- |
| edit time | `0.01s` |
| changed files | 6 source modules |
| pytest | `1 passed` |
| guard reports | none |
| transcripts | none |
| model/slot assignment | none |
| apply recommendation | not applicable |

## Agent Dry-Run Check

To validate the `$file-swarm-agent` side of the integrated story, I ran a dry-run structured action task with a local fake provider.

Result:

| Field | Value |
| --- | --- |
| provider | `fake-agent` |
| model | `fake-action-model` |
| task category | `mixed` |
| actions planned | 4 |
| action types | `shell`, `mcp_call`, `mcp_call`, `browser_fetch` |
| blocked actions | 0 |
| mode | dry run |

This checked that the structured-action pipeline can parse and dry-run mixed action plans without executing real side effects.

## Strengths And Weaknesses

### file-swarm strengths

- Strong audit trail.
- Per-file ownership.
- Model and slot visibility.
- Patch Guard before merge.
- Reproducible `final.patch`.
- Apply recommendation in `codex_summary.md`.
- Better fit for multi-model experiments.
- Better fit for teams that need transparent worker input/output.

### file-swarm weaknesses

- More setup and artifacts.
- More overhead for tiny edits.
- Quality depends on provider output and patch normalization.
- Requires slot configuration.
- Mock mode proves orchestration, not model intelligence.

### Direct Codex strengths

- Fastest path for simple work.
- Flexible when the change requires cross-file reasoning in one context.
- Less ceremony.
- Easier for one-off local refactors.

### Direct Codex weaknesses

- No slot/model accountability.
- No built-in Patch Guard.
- No transcript per worker.
- Harder to scale across models.
- Harder to prove which model did what.

## Practical Recommendation

Use `file-swarm` when:

- the task spans several files
- multiple providers or models should participate
- auditability matters
- patch-only safety matters
- Codex should decide based on reports rather than intuition

Use direct Codex editing when:

- the change is small
- speed matters more than audit trails
- the repository owner accepts direct edits
- one model/context can safely reason about the whole change

Best hybrid workflow:

```text
Codex designs constraints.
file-swarm runs parallel guarded workers.
Codex reads codex_summary.md.
Codex applies or repairs.
Codex directly handles tiny follow-up fixes if needed.
```

## Caveats

- This comparison used mock slots to avoid real API keys.
- Mock slots validate orchestration, leases, guard/merge/apply, and reporting.
- Real provider quality must be evaluated with live preflight and smoke-test.
- Benchmark results are environment-specific and should not be treated as universal model rankings.
