"""CLI smoke tests (no LLM calls)."""

from typer.testing import CliRunner

from gaffer.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "coach" in result.output or "chat" in result.output


def test_matches_lists_byo_data(byo_dir):
    result = runner.invoke(app, ["matches", "--data-dir", str(byo_dir)])
    assert result.exit_code == 0
    assert "Rovers" in result.output
    assert "1001" in result.output


def test_chat_preflight_blocks_missing_key(monkeypatch, byo_dir):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(
        app, ["chat", "-m", "anthropic:claude-sonnet-5", "--data-dir", str(byo_dir)]
    )
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output
