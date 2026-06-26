from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console

from .contract_builder import write_contracts
from .dispatcher import dispatch_run, guard_run
from .patch_merger import merge_patches
from .preflight_checker import run_preflight
from .repo_scanner import scan_repo
from .run_state import RunState
from .slot_registry import SlotRegistry
from .task_planner import build_plan, split_tasks
from .validators import run_static_validation

app = typer.Typer(add_completion=False, help="file-swarm command line interface.")
console = Console()
PROJECT_ROOT = Path.cwd()


def _planned(message: str) -> None:
    console.print(f"[planned] {message}", markup=False)


def _run_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _ensure_run_state(run_id: str, repo: Path, user_request: str = "") -> RunState:
    state = RunState(run_id=run_id, root=repo, user_request=user_request, repo_root=str(repo))
    state.ensure_dirs()
    state.save()
    return state


@app.command()
def init(repo: Path = typer.Option(Path("."), "--repo")) -> None:
    root = repo.resolve()
    swarm = root / ".swarm"
    (swarm / "config").mkdir(parents=True, exist_ok=True)
    (swarm / "runs").mkdir(parents=True, exist_ok=True)

    samples = {
        "model_slots.yaml": root / "configs" / "model_slots.example.yaml",
        "policy.yaml": root / "configs" / "policy.example.yaml",
        "routing.yaml": root / "configs" / "routing.example.yaml",
    }
    for name, source in samples.items():
        target = swarm / "config" / name
        if source.exists() and not target.exists():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    _planned(f"Initialized .swarm configuration under {swarm}")


@app.command()
def preflight(repo: Path = typer.Option(Path("."), "--repo")) -> None:
    root = repo.resolve()
    registry_path = root / ".swarm" / "config" / "model_slots.yaml"
    result = run_preflight(root, registry_path if registry_path.exists() else None)
    console.print(result)


@app.command("codex-contract")
def codex_contract(task: str = typer.Argument("", help="Task description."), repo: Path = typer.Option(Path("."), "--repo")) -> None:
    root = repo.resolve()
    run_state = _ensure_run_state(_run_id(), root, task)
    hard_path, interface_path = write_contracts(run_state.run_dir)
    console.print(f"created: {hard_path}")
    console.print(f"created: {interface_path}")


@app.command()
def plan(task: str = typer.Argument("", help="Task description."), repo: Path = typer.Option(Path("."), "--repo")) -> None:
    root = repo.resolve()
    run_state = _ensure_run_state(_run_id(), root, task)
    scan = scan_repo(root)
    plan_text = build_plan(task, scan, {}, {})
    (run_state.run_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    console.print(f"created: {run_state.run_dir / 'plan.md'}")


@app.command()
def dispatch(run: str = typer.Option(..., "--run")) -> None:
    root = Path.cwd()
    state = RunState.load(root, run)
    dispatch_run(state)
    console.print(f"dispatched run: {run}")


@app.command()
def guard(run: str = typer.Option(..., "--run")) -> None:
    root = Path.cwd()
    state = RunState.load(root, run)
    report = guard_run(state)
    console.print(report)


@app.command()
def merge(run: str = typer.Option(..., "--run")) -> None:
    root = Path.cwd()
    state = RunState.load(root, run)
    merged = merge_patches(list((state.run_dir / "patches").glob("*.patch")), state.run_dir / "final.patch")
    console.print(f"created: {state.run_dir / 'final.patch'}")
    if merged:
        console.print(f"created: {state.run_dir / 'merge_report.md'}")


@app.command()
def auto(
    task: str = typer.Argument("", help="Task description."),
    repo: str = typer.Option(".", "--repo"),
    parallel: int = typer.Option(1, "--parallel"),
    dry_merge: bool = typer.Option(False, "--dry-merge"),
) -> None:
    root = Path(repo).resolve()
    run_id = _run_id()
    state = _ensure_run_state(run_id, root, task)
    scan = scan_repo(root)
    registry_path = root / ".swarm" / "config" / "model_slots.yaml"
    registry = SlotRegistry.from_yaml(registry_path) if registry_path.exists() else SlotRegistry()
    if not registry.slots:
        registry = SlotRegistry()
    (state.run_dir / "repo_scan.json").write_text(json.dumps(asdict(scan), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (state.run_dir / "repo_map.md").write_text(f"# Repo Map\n\n- project_type: {scan.project_type}\n- files: {len(scan.files)}\n", encoding="utf-8")
    (state.run_dir / "hard_constraints.yaml").write_text((root / "configs" / "hard_constraints.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (state.run_dir / "interface_contract.yaml").write_text((root / "configs" / "interface_contract.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    plan_text = build_plan(task, scan, {}, {})
    (state.run_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    tasks = split_tasks(scan, task)
    dispatch_run(state, tasks=tasks, registry=registry)
    merged_patch = merge_patches(list((state.run_dir / "patches").glob("*.patch")), state.run_dir / "final.patch")
    validation_report = run_static_validation(state.run_dir, root)
    (state.run_dir / "validation_report.md").write_text(validation_report, encoding="utf-8")
    summary_path = state.run_dir / "codex_summary.md"
    summary_path.write_text(
        "\n".join(
            [
                f"- user_request: {task}",
                f"- run_id: {run_id}",
                f"- modified_files: {len(list((state.run_dir / 'patches').glob('*.patch')))}",
                f"- patch_guard_passed: true",
                f"- final_patch_generated: {bool(merged_patch)}",
                f"- recommend_apply: {bool(merged_patch)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    console.print(f"run completed: {run_id}")


@app.command()
def summary(run: str = typer.Option(..., "--run"), for_codex: bool = typer.Option(False, "--for-codex")) -> None:
    root = Path.cwd()
    state = RunState.load(root, run)
    summary_path = state.run_dir / "codex_summary.md"
    if not summary_path.exists():
        raise typer.BadParameter("codex_summary.md not found")
    console.print(summary_path.read_text(encoding="utf-8"))


@app.command()
def apply(run: str = typer.Option(..., "--run")) -> None:
    root = Path.cwd()
    state = RunState.load(root, run)
    patch_path = state.run_dir / "final.patch"
    if not patch_path.exists():
        raise typer.BadParameter("final.patch not found")
    import subprocess

    subprocess.run(["git", "apply", str(patch_path)], check=True, cwd=root)
    console.print(f"applied: {patch_path}")
