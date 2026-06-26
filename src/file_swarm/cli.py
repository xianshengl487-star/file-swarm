from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console

from .contract_builder import ensure_contracts, load_contract_dicts, load_contract_texts, write_contracts
from .dispatcher import dispatch_run, guard_run, write_auto_summary
from .patch_apply import apply_patch_text
from .patch_merger import merge_patches
from .preflight_checker import run_preflight, run_smoke_test
from .repo_scanner import scan_repo
from .run_state import RunState
from .slot_registry import SlotRegistry
from .task_planner import build_plan, split_tasks
from .transcript_logger import write_json, write_text
from .validators import render_validation_report, run_validation

app = typer.Typer(add_completion=False, help="file-swarm command line interface.")
console = Console()


def _planned(message: str) -> None:
    console.print(f"[planned] {message}", markup=False)


def _run_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def _ensure_run_state(run_id: str, repo: Path, user_request: str = "") -> RunState:
    state = RunState(run_id=run_id, root=repo, user_request=user_request, repo_root=str(repo))
    state.ensure_dirs()
    state.save()
    return state


def _slots_path(root: Path) -> Path:
    return root / ".swarm" / "config" / "model_slots.yaml"


def _load_registry(root: Path) -> SlotRegistry:
    path = _slots_path(root)
    return SlotRegistry.from_yaml(path) if path.exists() else SlotRegistry()


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
def preflight(
    repo: Path = typer.Option(Path("."), "--repo"),
    live: bool = typer.Option(False, "--live"),
    model: str = typer.Option("", "--model"),
) -> None:
    root = repo.resolve()
    registry_path = _slots_path(root)
    result = run_preflight(
        root,
        registry_path if registry_path.exists() else None,
        live=live,
        requested_model=model or None,
    )
    console.print(result)


@app.command("smoke-test")
def smoke_test(
    repo: Path = typer.Option(Path("."), "--repo"),
    live: bool = typer.Option(False, "--live"),
    model: str = typer.Option("", "--model"),
) -> None:
    root = repo.resolve()
    run_state = _ensure_run_state(_run_id(), root, "smoke-test")
    result = run_smoke_test(
        root,
        _slots_path(root) if _slots_path(root).exists() else None,
        requested_model=model or None,
        live=live,
    )
    write_text(run_state.run_dir / "smoke_test_report.md", result.report_text)
    if result.patch_text:
        write_text(run_state.run_dir / "smoke.patch", result.patch_text)
    write_json(
        run_state.run_dir / "smoke_test_report.json",
        {"status": result.status, "report_text": result.report_text, "patch_generated": bool(result.patch_text)},
    )
    console.print(result.report_text)


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
    hard_constraints, interface_contract = load_contract_dicts(run_state.run_dir)
    plan_text = build_plan(task, scan, hard_constraints, interface_contract)
    write_text(run_state.run_dir / "plan.md", plan_text)
    tasks = split_tasks(scan, task)
    write_json(run_state.run_dir / "file_tasks.json", [asdict(task_item) for task_item in tasks])
    console.print(f"created: {run_state.run_dir / 'plan.md'}")


@app.command()
def dispatch(
    run: str = typer.Option(..., "--run"),
    parallel: int = typer.Option(1, "--parallel"),
    timeout: float = typer.Option(30.0, "--timeout"),
) -> None:
    root = Path.cwd()
    state = RunState.load(root, run)
    registry = _load_registry(root)
    results = dispatch_run(state, registry=registry, parallel=parallel, timeout_seconds=timeout)
    console.print(json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False))


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
    result = merge_patches(state.run_dir)
    console.print(
        json.dumps(
            {
                "merged": result.merged,
                "conflict": result.conflict,
                "final_patch_path": str(result.final_patch_path) if result.final_patch_path else None,
                "merge_report_path": str(result.merge_report_path),
                "reason": result.reason,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


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
    hard_constraints, interface_contract = load_contract_dicts(state.run_dir)
    repo_map = "\n".join(
        [
            "# Repo Map",
            "",
            f"- project_type: {scan.project_type}",
            f"- source_dirs: {', '.join(scan.source_dirs) or 'none'}",
            f"- test_dirs: {', '.join(scan.test_dirs) or 'none'}",
            f"- config_files: {', '.join(scan.config_files) or 'none'}",
        ]
    ) + "\n"
    write_text(state.run_dir / "repo_map.md", repo_map)
    write_text(state.run_dir / "hard_constraints.yaml", (state.run_dir / "hard_constraints.yaml").read_text(encoding="utf-8"))
    write_text(state.run_dir / "interface_contract.yaml", (state.run_dir / "interface_contract.yaml").read_text(encoding="utf-8"))
    plan_text = build_plan(task, scan, hard_constraints, interface_contract)
    write_text(state.run_dir / "plan.md", plan_text)
    tasks = split_tasks(scan, task)
    write_json(state.run_dir / "file_tasks.json", [asdict(task_item) for task_item in tasks])
    results = dispatch_run(state, tasks=tasks, registry=_load_registry(root), parallel=parallel)
    guard_run(state)
    merge_result = merge_patches(state.run_dir)
    validation_result = run_validation(root, apply_mode=False)
    write_text(state.run_dir / "validation_report.md", render_validation_report(validation_result))
    write_auto_summary(state, len(results), merge_result, validation_result)
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
    try:
        subprocess.run(["git", "apply", str(patch_path)], check=True, cwd=root)
    except subprocess.CalledProcessError:
        apply_patch_text(root, patch_path)
    validation_result = run_validation(root, apply_mode=True)
    write_text(state.run_dir / "validation_report.md", render_validation_report(validation_result))
    console.print(f"applied: {patch_path}")
    console.print(render_validation_report(validation_result))
