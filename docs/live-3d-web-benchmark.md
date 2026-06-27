# Live 3D Web Benchmark

Date: 2026-06-27

This report records a larger live `file-swarm` test against a temporary 3D web project.

## Safety

The API keys were injected only as process environment variables for the benchmark commands.

No raw API key was written to repository files, reports, transcripts, or README content.

## Target Project

Temporary project:

```text
.workbuddy/large_3d_web_live_benchmark/
```

Shape:

- 13 source files:
  - `src/app.js`
  - `src/audio.js`
  - `src/camera.js`
  - `src/controls.js`
  - `src/hud.js`
  - `src/index.html`
  - `src/lighting.js`
  - `src/materials.js`
  - `src/particles.js`
  - `src/performance.js`
  - `src/postprocessing.js`
  - `src/scene.js`
  - `src/styles.css`
- Node built-in validation through `npm test`
- No external npm dependencies

Task:

```text
Complete every TODO(file-swarm) in this larger 3D web project so npm test passes.
Keep each file scoped and return unified diffs only.
```

Baseline:

```text
npm test: failed
first failure: bootstrapExperience().ready was false
```

## Live Model Discovery

The NVIDIA endpoint listed the canonical GLM model as:

```text
z-ai/glm-5.1
```

The Mimo endpoint listed:

```text
mimo-v2.5-pro
```

At the time of this run, a minimal Mimo `/v1` chat probe returned `ok=True` with empty text, and `file-swarm preflight --live` reported `unexpected response`. Mimo was therefore not used for dispatch in this historical run.

Follow-up hardening changed that failure mode:

- Mimo `/v1` empty text is now `empty_response`, not success.
- Mimo `/anthropic` is supported directly.
- `rate_limit`, `timeout`, `connection_error`, `empty_response`, and 429/502/503 errors are failoverable for patch workers.
- The recommended Mimo order is `/anthropic` first, `/v1` compatibility second.

## Preflight And Smoke

After switching from `glm-5.1` to `z-ai/glm-5.1`:

```text
nvidia_glm_01: live_ok
nvidia_glm_02: live_ok
nvidia_glm_03: live_ok
nvidia_glm_04: live_ok
mimo_aux_01: failed, unexpected response
```

Live smoke-test passed on NVIDIA:

```text
status: passed
slot_id: nvidia_glm_01
provider: openai_compatible
model: z-ai/glm-5.1
patch_generated: true
```

## Run 1: 12-Task Live Pass

Run:

```text
run_id: 20260627043956399876
parallel: 4
model: z-ai/glm-5.1
slots: nvidia_glm_01, nvidia_glm_02, nvidia_glm_03, nvidia_glm_04
elapsed: 24.482s
```

Result:

```text
completed_tasks: 12
failed_tasks: 0
guard_passed_tasks: 12
guard_rejected_tasks: 0
final_patch_generated: yes
```

Implementation status after apply:

```text
12/13 source expectations implemented
npm test: failed
missing file: src/styles.css
failure: --swarm-depth-glow was not defined
```

Root cause:

```text
The generic planner capped file-level tasks at 12, so the 13th web source file was not planned.
```

Fix made in this repository:

```text
Web source splitting now supports .html/.css/.js/.jsx/.ts/.tsx and allows up to 16 tasks.
```

## Run 2: Full 13-Task Retry

After raising the task cap, a clean 13-file run was attempted.

Run:

```text
run_id: 20260627044314387928
parallel: 4
elapsed: 81.383s
```

Result:

```text
completed_tasks: 4
failed_tasks: 9
guard_passed_tasks: 4
guard_rejected_tasks: 9
failure_reason: rate_limit
recommend_apply: no
```

The first four files were patched successfully:

```text
src/app.js
src/audio.js
src/camera.js
src/controls.js
```

The remaining tasks failed with `rate_limit`.

## Run 3: Cooldown Retry

A retry using only selected NVIDIA slots was attempted after a short cooldown.

Run:

```text
run_id: 20260627044513614175
parallel: 3
```

Preflight immediately before the run reported `rate_limit` for all selected slots.

Result:

```text
completed_tasks: 0
failed_tasks: 13
guard_passed_tasks: 0
guard_rejected_tasks: 13
failure_reason: rate_limit
recommend_apply: no
```

A style-only repair attempt using the remaining NVIDIA key also hit `rate_limit`, so it was skipped.

## Implementation Completeness

Best applied implementation from the live benchmark:

```text
12/13 source expectations implemented
JS/HTML behavior: passed expected values
CSS behavior: missing --swarm-depth-glow
overall npm test: failed
```

This is a useful result, not a fake pass:

- GLM live patch generation worked.
- Patch Guard accepted real model diffs.
- The first larger run applied meaningful code to 12 files.
- The final validation caught the missing CSS file.
- Rate limiting prevented completing the full 13-file live run in one session.

## Engineering Fixes From This Test

This benchmark produced concrete improvements:

1. Planner now includes Web source files, not only Python files.
2. Planner cap increased from 12 to 16 tasks for medium Web projects.
3. Windows validator now uses `shutil.which()` resolved paths such as `npm.cmd`.
4. Dispatcher task loading now accepts UTF-8 BOM JSON run artifacts.

Tests were added for the Web planner, Node validator, and UTF-8 BOM task loading.

## Next Live Test Plan

To get a full 13/13 passing live run:

1. Wait for NVIDIA rate-limit cooldown or use fresh quota.
2. Run `file-swarm preflight --repo . --live`.
3. Disable every slot that is not `live_ok`.
4. Start with `--parallel 1` or `--parallel 2`.
5. Re-enable higher parallelism only after smoke and one small task pass.
6. Include Mimo `/anthropic` slots after they return `live_ok`; keep Mimo `/v1` as compatibility only because empty text now triggers failover.

Recommended command shape:

```powershell
file-swarm preflight --repo . --live
file-swarm smoke-test --repo . --live
file-swarm auto "Complete every TODO(file-swarm) in this larger 3D web project so npm test passes. Keep each file scoped and return unified diffs only." --repo . --parallel 2 --dry-merge
file-swarm summary --run <run_id> --for-codex
```
