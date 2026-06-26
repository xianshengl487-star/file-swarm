# file-swarm

`file-swarm` supports any OpenAI-compatible model worker. Claude is optional, not required.

## When to Use

Use `file-swarm` when a task should be split into guarded patches and handled by OpenAI-compatible workers under Codex supervision.

## Codex Lite Workflow

1. Build `hard_constraints.yaml`.
2. Build `interface_contract.yaml`.
3. Run the orchestrator.
4. Read the summary.
5. Decide whether to apply the final patch.

## `hard_constraints.yaml`

This file defines the worker sandbox at the policy level:

- allowed file scope
- forbidden directories
- dependency restrictions
- patch format requirements
- secret handling rules

## `interface_contract.yaml`

This file defines behavior expectations for code shape, error handling, imports, tests, and documentation.

## Model Slot

A model slot is a single provider connection identified by:

- `base_url`
- `api_key_env`
- model allow-list
- concurrency budget

## Stateless Patch Worker

The default worker type in `file-swarm` is stateless and patch-only.
It must not directly modify repository files.

## OpenAI-compatible Worker Support

`file-swarm` supports any OpenAI-compatible Chat Completions API.
Claude is optional, not required.

## Visible Communication

Worker input, summaries, validation, and merge decisions should remain inspectable on disk.

## Patch Guard

Patch Guard rejects:

- out-of-scope edits
- unauthorized file creation
- direct secret exposure
- dependency changes not allowed by policy

## Final Validation

Codex should only apply a final patch after reading:

- the summary
- the validation report
- the guarded patch result
