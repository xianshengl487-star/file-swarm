from typer.testing import CliRunner

from file_swarm.cli import app


def test_cli_init_prints_planned_message() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "[planned]" in result.output
