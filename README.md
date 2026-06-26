# file-swarm

Codex-controlled OpenAI-compatible file-level coding swarm.

`file-swarm` is a lightweight orchestration scaffold for delegating code work to OpenAI-compatible model workers while keeping Codex in a final-supervisor role.

## 中文简介

`file-swarm` 是一个面向 OpenAI-compatible 模型的轻量级文件级并行编程调度系统。
它的目标不是让 Codex 直接大规模改文件，而是让 Codex 负责规则、契约和最终验收，让下游模型负责生成补丁，再由本地调度器统一审查、合并和应用。

### 中文定位

- Codex 负责生成严格约束和接口契约。
- `file-swarm` 负责扫描仓库、拆分任务、调度模型、守护补丁、合并结果和生成报告。
- 下游 Worker 默认只返回 `unified diff patch`，不直接写文件。
- 最终是否应用补丁，由 `file-swarm` 和 Codex 共同控制。

### 中文核心概念

- `Codex Lite Master`：最终监督者，只负责契约、报告和最终决策。
- `Model Slot`：一个 `base_url + api_key_env` 组成的模型接入槽位。
- `Model Worker`：绑定任务、槽位和模型的执行单元。
- `Stateless Patch Worker`：默认 Worker 类型，只输出补丁，不直接改仓库。

### 中文工作流

1. 扫描仓库，生成仓库地图。
2. 生成 `hard_constraints.yaml` 和 `interface_contract.yaml`。
3. 拆分任务并调度 Worker。
4. Worker 返回 patch。
5. Patch 经过 Patch Guard。
6. 合并 patch，生成 `final.patch`。
7. 执行验证，生成 `codex_summary.md`。

### 中文命令示例

```bash
file-swarm init
file-swarm preflight
file-swarm codex-contract "实现登录模块"
file-swarm plan "实现登录模块"
file-swarm dispatch --run <run_id>
file-swarm guard --run <run_id>
file-swarm merge --run <run_id>
file-swarm auto "实现登录模块" --repo . --parallel 4 --dry-merge
file-swarm summary --run <run_id> --for-codex
file-swarm apply --run <run_id>
```

## Project Goal

The project focuses on a small, disciplined parallel coding workflow:

- Codex generates hard constraints and interface contracts.
- File-swarm orchestrates planning, dispatch, guard checks, merging, validation, and summary.
- Model workers only return unified diff patches by default.
- Final application decisions stay under Codex control.

## Why Codex Does Less Work

`file-swarm` is designed so Codex does not directly modify repository files in the normal workflow.
Instead, downstream models produce unified diff patches, and the orchestrator decides whether a patch can be applied.

## Core Roles

### Codex Lite Master

The final supervisor that produces:

- `hard_constraints.yaml`
- `interface_contract.yaml`
- the final supervision decision

### Model Slot

A model slot is a single `base_url + api_key_env` configuration for one OpenAI-compatible provider endpoint.

### Model Worker

A worker is a runtime task executor bound to:

- a task
- a slot
- a model

### Stateless Patch Worker

The default worker type.
It does not directly write files and instead returns unified diff patches.

## OpenAI-compatible Model Support

The project is designed to work with any OpenAI-compatible Chat Completions API, including:

- DeepSeek
- GLM
- Qwen
- Kimi
- MiniMax
- Claude
- Gemini
- OpenAI-compatible proxies
- LiteLLM
- vLLM
- Ollama

Support is interface-first: this repository ships the contract and scaffolding, not real model calls.

## Core Workflow

```mermaid
flowchart LR
  A[Codex Lite Master] --> B[hard_constraints.yaml]
  A --> C[interface_contract.yaml]
  B --> D[file-swarm Orchestrator]
  C --> D
  D --> E[Model Slot Registry]
  E --> F[OpenAI-Compatible Model Workers]
  F --> G[Patch Guard]
  G --> H[Patch Merger]
  H --> I[Validator]
  I --> J[Codex Final Supervisor]
```

## Safety Mechanisms

- visible transcripts
- slot preflight checks
- patch guard enforcement
- scope-limited file assignment
- secret redaction
- dry-merge default behavior

## Communication Visibility

All important orchestration steps are written to disk in transcript files so the workflow stays inspectable.

## Patch Guard

Patch Guard is the gatekeeper that checks:

- scope
- file assignment
- file creation rules
- secret redaction
- dependency restrictions

Only guarded patches can move toward merge and application.

## MVP Roadmap

1. Scaffold repository and CLI commands.
2. Add configuration samples and contract data models.
3. Implement slot registry and lease management.
4. Add patch guard and patch merger.
5. Add validation and summary reporting.
6. Grow toward real multi-worker orchestration.

## Installation

```bash
pip install -e .
```

## Configuration

The repository uses environment-variable-based keys.

Create the following environment variables locally:

- `MIMO_API_KEY_01`
- `NVIDIA_API_KEY_01`
- `NVIDIA_API_KEY_02`
- `NVIDIA_API_KEY_03`
- `NVIDIA_API_KEY_04`
- `NVIDIA_API_KEY_05`
- `NVIDIA_API_KEY_06`

You can use `.env.example` as a checklist, but do not commit real key values.

The local slot registry lives at `.swarm/config/model_slots.yaml`.
It now points to:

- a Mimo slot at `https://token-plan-cn.xiaomimimo.com/v1`
- NVIDIA-compatible slots at `https://integrate.api.nvidia.com/v1`

If you want to activate them in PowerShell for the current session, set the variables manually in your shell before running `file-swarm preflight` or `file-swarm auto`.

## CLI

```bash
file-swarm init
file-swarm preflight
file-swarm codex-contract
file-swarm plan
file-swarm dispatch
file-swarm guard
file-swarm merge
file-swarm auto
file-swarm summary
file-swarm apply
```

Example workflow:

```bash
file-swarm init
file-swarm preflight
file-swarm codex-contract "实现登录模块"
file-swarm auto "实现登录模块" --repo . --parallel 8 --dry-merge
file-swarm summary --for-codex
file-swarm apply --run <run_id>
```

## Command Output Philosophy

Each command prints a clear planned-state message first, because this repository currently exposes the scaffold before the full orchestration engine.

## License

MIT
