# AGENTS.md

Codex is a lightweight controller in this project, not the primary coder.

## Codex Responsibilities

1. Generate `hard_constraints.yaml`.
2. Generate `interface_contract.yaml`.
3. Call `file-swarm`.
4. Read `codex_summary.md`.
5. Decide whether to apply `final.patch` based on the final report.

## Codex Should Not

1. Read a large amount of source code directly.
2. Implement every file by hand.
3. Review every worker output line by line.
4. Inject full repository content into the prompt.
5. Bypass Patch Guard and modify files directly.

## Required Rules

- Do not hide worker input or output.
- Do not call slots without an API key.
- Do not call slots that fail preflight.
- Do not let one slot serve multiple workers at the same time.
- Do not let workers modify files outside allowed files.
- Do not log API keys in full.
- All patches must pass through Patch Guard first.
- Downstream models should not write files directly by default.
- `final.patch` must be accompanied by a summary and validation report before application.
