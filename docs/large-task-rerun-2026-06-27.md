# Large Task Rerun - 2026-06-27

This rerun tested the current `file-swarm` pipeline after the Mimo endpoint and NVIDIA failover hardening.

## Environment

Live API keys were not present in the current process, user environment, or machine environment.

```text
NVIDIA_API_KEY_01: missing
NVIDIA_API_KEY_02: missing
NVIDIA_API_KEY_03: missing
NVIDIA_API_KEY_04: missing
NVIDIA_API_KEY_05: missing
MIMO_API_KEY_01: missing
```

Because no live key was available, this run did not claim live model quality. It used mock slots named after the intended live models.

## Test Project

Temporary project:

```text
C:\Users\MAOYAO~1\AppData\Local\Temp\file-swarm-large-task-20260627051828
```

Project shape:

```text
src/nebula3d/
  animation.py
  assets.py
  camera.py
  controls.py
  lighting.py
  material.py
  mesh.py
  physics.py
  renderer.py
  scene.py
  telemetry.py
  vector.py
tests/
  test_interaction.py
  test_runtime.py
  test_scene.py
```

The project was initialized as a clean git repository before running `file-swarm`.

## Slot Setup

| Slot | Provider | Model |
| --- | --- | --- |
| `mock_glm_primary` | `mock` | `z-ai/glm-5.1` |
| `mock_mimo_pro` | `mock` | `mimo-v2.5-pro` |
| `mock_mimo_multimodal` | `mock` | `mimo-v2.5` |

Routing order:

```text
z-ai/glm-5.1 -> mimo-v2.5-pro -> mimo-v2.5
```

## Commands

```powershell
file-swarm preflight --repo <temp_project>
file-swarm smoke-test --repo <temp_project>
file-swarm codex-contract "<large task>" --repo <temp_project>
file-swarm auto "<large task>" --repo <temp_project> --parallel 3 --dry-merge
file-swarm summary --run 20260627051856138848 --for-codex
file-swarm apply --run 20260627051856138848
```

## Results

| Metric | Result |
| --- | --- |
| Run ID | `20260627051856138848` |
| Execution mode | `mock` |
| Total tasks | `12` |
| Completed tasks | `12` |
| Failed tasks | `0` |
| Guard passed | `12` |
| Guard rejected | `0` |
| Final patch | generated, non-empty |
| Final patch size | `108` lines |
| Apply status | `applied` |
| Validation | `pytest`, `3 passed` |
| Max active workers | `3` |
| Slot overlap | none |
| Failover events | none |

## Task Distribution

| Task | File | Slot | Model | Status |
| --- | --- | --- | --- | --- |
| `task_001` | `src/nebula3d/animation.py` | `mock_glm_primary` | `z-ai/glm-5.1` | passed |
| `task_002` | `src/nebula3d/assets.py` | `mock_mimo_pro` | `mimo-v2.5-pro` | passed |
| `task_003` | `src/nebula3d/camera.py` | `mock_mimo_multimodal` | `mimo-v2.5` | passed |
| `task_004` | `src/nebula3d/controls.py` | `mock_glm_primary` | `z-ai/glm-5.1` | passed |
| `task_005` | `src/nebula3d/lighting.py` | `mock_mimo_pro` | `mimo-v2.5-pro` | passed |
| `task_006` | `src/nebula3d/material.py` | `mock_mimo_multimodal` | `mimo-v2.5` | passed |
| `task_007` | `src/nebula3d/mesh.py` | `mock_glm_primary` | `z-ai/glm-5.1` | passed |
| `task_008` | `src/nebula3d/physics.py` | `mock_mimo_pro` | `mimo-v2.5-pro` | passed |
| `task_009` | `src/nebula3d/renderer.py` | `mock_mimo_multimodal` | `mimo-v2.5` | passed |
| `task_010` | `src/nebula3d/scene.py` | `mock_glm_primary` | `z-ai/glm-5.1` | passed |
| `task_011` | `src/nebula3d/telemetry.py` | `mock_mimo_pro` | `mimo-v2.5-pro` | passed |
| `task_012` | `src/nebula3d/vector.py` | `mock_mimo_multimodal` | `mimo-v2.5` | passed |

## Interpretation

This run proves the orchestration path is stable for a medium-large file-level job:

- task splitting produced 12 file-level patch workers
- `--parallel 3` reached three active workers
- three slots were used without slot overlap
- every worker wrote transcripts, patch output, guard report, and metadata
- Patch Guard accepted all patches
- `final.patch` applied through default `git apply`
- post-apply pytest passed
- `codex_summary.md` moved from `yes_with_caution` before apply to applied/passed after apply

It does not prove live model implementation quality because live keys were unavailable. The mock provider generated deterministic safe marker patches, so implementation depth should be treated as pipeline validation rather than a real feature benchmark.

## Next Live Rerun

To rerun as a real GLM/Mimo benchmark:

1. Set `NVIDIA_API_KEY_01` through `NVIDIA_API_KEY_05` and `MIMO_API_KEY_01` in the environment outside the transcript.
2. Reopen the terminal so the process can see those variables.
3. Use `configs/model_slots.example.yaml` as the slot template.
4. Run `file-swarm preflight --repo <project> --live`.
5. Run `file-swarm smoke-test --repo <project> --live`.
6. Run `file-swarm auto "<large task>" --repo <project> --parallel 2 --dry-merge`.

The live rerun should verify NVIDIA rate-limit failover into Mimo `/anthropic`.
