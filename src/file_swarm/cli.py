from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(add_completion=False, help="file-swarm command line interface.")
console = Console()


def _planned(message: str) -> None:
    console.print(f"[planned] {message}", markup=False)


@app.command()
def init() -> None:
    _planned("This command will initialize the file-swarm scaffold and project metadata.")


@app.command()
def preflight() -> None:
    _planned("This command will validate slot configuration, scope, and worker readiness.")


@app.command("codex-contract")
def codex_contract(task: str = typer.Argument("", help="Task description.")) -> None:
    _planned("This command will create hard_constraints.yaml and interface_contract.yaml.")


@app.command()
def plan() -> None:
    _planned("This command will build the task plan for the current repository.")


@app.command()
def dispatch() -> None:
    _planned("This command will dispatch tasks to model workers through available slots.")


@app.command()
def guard() -> None:
    _planned("This command will run Patch Guard against generated patches.")


@app.command()
def merge() -> None:
    _planned("This command will dry-merge guarded patches into a final candidate.")


@app.command()
def auto(
    task: str = typer.Argument("", help="Task description."),
    repo: str = typer.Option(".", "--repo"),
    parallel: int = typer.Option(1, "--parallel"),
    dry_merge: bool = typer.Option(False, "--dry-merge"),
) -> None:
    _planned("Run the full Codex Lite workflow: scan, delegate planning, split tasks, dispatch workers, guard patches, merge, validate, and summarize.")


@app.command()
def summary(for_codex: bool = typer.Option(False, "--for-codex")) -> None:
    _planned("This command will generate a Codex-readable summary of the current run.")


@app.command()
def apply(run: str = typer.Option(..., "--run")) -> None:
    _planned("This command will apply a final approved patch for a recorded run.")
