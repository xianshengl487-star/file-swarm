# How to Reference the file-swarm Skill

This project includes a `file-swarm` skill at:

```text
.claude/skills/file-swarm/SKILL.md
```

Use it when you want Codex to act as a lightweight controller and let `file-swarm` split work into guarded patch workers.

## Explicit Reference

In Codex, say:

```text
Use $file-swarm to implement this task:
<your coding task>
```

Examples:

```text
Use $file-swarm to add a safe mouse clicker demo with core logic, UI helpers, and tests.
```

```text
Use $file-swarm to split this feature across model slots, generate guarded patches, and show which model handled each task.
```

## Natural Language Trigger

The skill should also be used when the request mentions:

- file-level coding swarm
- multi-slot model cooperation
- OpenAI-compatible workers
- guarded patch workers
- `hard_constraints.yaml`
- `interface_contract.yaml`
- `file-swarm auto`
- showing which model did which task

Example:

```text
Run file-swarm on this repo, split the task into guarded patch workers, and summarize which slots and models handled each file.
```

## Expected Workflow

The skill instructs Codex to run:

```bash
file-swarm init --repo .
file-swarm preflight --repo .
file-swarm codex-contract "<task>" --repo .
file-swarm auto "<task>" --repo . --parallel 2 --dry-merge
file-swarm summary --run <run_id> --for-codex
```

If the summary recommends applying:

```bash
file-swarm apply --run <run_id> --allow-dirty
```

If guard or validation fails:

```bash
file-swarm repair --run <run_id>
```

## How To See Model Assignment

After a run, inspect:

```text
.swarm/runs/<run_id>/dispatch_report.json
.swarm/runs/<run_id>/dispatch_report.md
.swarm/runs/<run_id>/timeline.jsonl
.swarm/runs/<run_id>/transcripts/task_xxx.meta.json
.swarm/runs/<run_id>/codex_summary.md
```

Report model assignment like this:

```text
task_id | file(s) | slot | model | provider | status
task_001 | src/clicker_core.py | mock1 | mock-model | mock | passed
task_002 | src/clicker_ui.py | mock2 | mock-model | mock | passed
```

Use `dispatch_report.json` as the source of truth for:

- task id
- slot id
- model
- provider
- mock/live mode
- status
- modified files
- provider error, if any

Use `timeline.jsonl` to prove slot leasing:

- `slot_acquired`
- `worker_started`
- `worker_finished`
- `slot_released`

## Safety Rules

Do not ask workers to modify files directly. Workers return unified diff patches only.

Do not print, write, or commit API keys. Configure real keys only through environment variables referenced by `api_key_env`.

Do not apply `final.patch` unless `codex_summary.md` says `recommend_apply: yes` or `recommend_apply: yes_with_caution` and Patch Guard passed.
