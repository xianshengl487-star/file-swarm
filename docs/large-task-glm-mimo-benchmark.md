# Large Task GLM/Mimo Skill Benchmark

Date: 2026-06-27

This report records a large-task test of the latest `$file-swarm` skill flow.

## Live API Status

Requested live model plan:

| Role | Model | Provider style | Endpoint |
| --- | --- | --- | --- |
| Primary | `glm-5.1` | OpenAI-compatible | `https://integrate.api.nvidia.com/v1` |
| Auxiliary | `mimo-v2.5-pro` | OpenAI-compatible | `https://token-plan-cn.xiaomimimo.com/v1` |

The local environment did not expose the required key variables:

```text
NVIDIA_API_KEY_01=missing
MIMO_API_KEY_01=missing
```

`file-swarm preflight --repo . --live` therefore skipped live slots with `reason: missing key`.

No live GLM/Mimo result is claimed in this report. To avoid fake success, the large-task run below used deterministic mock slots named after the requested models.

## Test Project

Temporary benchmark repo:

```text
.workbuddy/large_task_skill_benchmark_git_clean/
```

Project shape:

- 8 source modules under `src/largeflow/`
- 1 pytest module under `tests/`
- local nested Git repo
- `file-swarm` mock slots:
  - `mock_glm_primary` -> `glm-5.1`
  - `mock_mimo_aux_01` -> `mimo-v2.5-pro`
  - `mock_mimo_aux_02` -> `mimo-v2.5-pro`

Task:

```text
Append a harmless file-swarm marker function to every LargeFlow source module,
preserving existing behavior and tests.
```

## file-swarm Result

Commands:

```bash
file-swarm auto "Append a harmless file-swarm marker function to every LargeFlow source module, preserving existing behavior and tests." --repo . --parallel 3 --dry-merge
file-swarm summary --run 20260627042257146410 --for-codex
file-swarm apply --run 20260627042257146410 --allow-dirty --allow-fallback-apply
python -m pytest -q
```

Run:

```text
run_id: 20260627042257146410
execution_mode: mock
auto_time: 1.159s
total_tasks: 8
completed_tasks: 8
guard_passed_tasks: 8
guard_rejected_tasks: 0
final_patch_generated: yes
final_patch_empty: no
validation_status: passed
apply_status: applied
recommend_apply: yes
pytest: 1 passed
implementation_completeness: 8/8 source modules
```

Model/task mapping:

| Task | File | Slot | Model | Status |
| --- | --- | --- | --- | --- |
| `task_001` | `src/largeflow/audit.py` | `mock_glm_primary` | `glm-5.1` | passed |
| `task_002` | `src/largeflow/forecast.py` | `mock_mimo_aux_01` | `mimo-v2.5-pro` | passed |
| `task_003` | `src/largeflow/inventory.py` | `mock_mimo_aux_02` | `mimo-v2.5-pro` | passed |
| `task_004` | `src/largeflow/orders.py` | `mock_glm_primary` | `glm-5.1` | passed |
| `task_005` | `src/largeflow/pricing.py` | `mock_mimo_aux_01` | `mimo-v2.5-pro` | passed |
| `task_006` | `src/largeflow/quality.py` | `mock_mimo_aux_02` | `mimo-v2.5-pro` | passed |
| `task_007` | `src/largeflow/reporting.py` | `mock_glm_primary` | `glm-5.1` | passed |
| `task_008` | `src/largeflow/shipping.py` | `mock_mimo_aux_01` | `mimo-v2.5-pro` | passed |

Slot split:

```text
glm-5.1: 3 files
mimo-v2.5-pro: 5 files
```

## Direct Codex Baseline

On the same baseline project, a direct edit pass appended the same marker functions.

```text
direct_edit_time: 0.046s
implementation_completeness: 8/8 source modules
pytest: 1 passed
patch_guard: no
transcripts: no
dispatch_report: no
codex_summary: no
```

## Skill Advantages Observed

`file-swarm` was slower than direct editing on this deterministic workload, but it produced a stronger control plane:

- Every source file had a separate task and allowed-file boundary.
- Slot/model assignment was visible in `dispatch_report.json`.
- Timeline events showed `slot_acquired`, `worker_started`, `worker_finished`, and `slot_released`.
- Patch Guard accepted 8/8 patches before merge.
- `final.patch` was generated from guarded patches only.
- `codex_summary.md` gave an apply recommendation based on guard, merge, validation, and contract state.
- The final implementation could be checked as `8/8` files plus pytest.

Direct Codex editing was much faster:

- `0.046s` direct edit vs `1.159s` swarm orchestration.
- Less ceremony for a trusted, mechanical change.

But direct editing did not provide:

- model/task mapping,
- slot lease evidence,
- per-worker transcripts,
- Patch Guard reports,
- a Codex-readable apply decision summary.

## Implementation Findings

This test found and fixed three patch pipeline issues:

1. `patch_normalizer` must preserve blank unified-diff context lines represented as a single space.
2. fallback apply must honor hunk start lines from `@@ -start,count +start,count @@`.
3. `_extract_diff_block()` must not skip the first file when a bare multi-file patch starts at line 1.

Regression coverage was added in `tests/test_patch_apply_and_normalizer.py`.

Known apply boundary:

- Native `git apply` failed in the temporary Windows benchmark repo before explicit fallback.
- Explicit `--allow-fallback-apply` succeeded and produced `8/8` implementation completeness.
- Future hardening should make generated patches friendlier to native Git apply on Windows before relying on fallback.

## How To Rerun With Real GLM/Mimo

Set environment variables outside the repository. Do not write keys into files.

PowerShell:

```powershell
$env:NVIDIA_API_KEY_01 = "<your NVIDIA key>"
$env:MIMO_API_KEY_01 = "<your Mimo key>"
file-swarm preflight --repo . --live
file-swarm smoke-test --repo . --live
file-swarm auto "Append a harmless file-swarm marker function to every LargeFlow source module, preserving existing behavior and tests." --repo . --parallel 3 --dry-merge
```

Expected decision rule:

- If live preflight skips a slot, do not call that slot.
- If live smoke-test returns non-diff text, treat it as failed.
- Only apply when `codex_summary.md` says `recommend_apply: yes` or `yes_with_caution`.
