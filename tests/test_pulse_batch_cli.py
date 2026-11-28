"""Dry-run and CLI safety tests; intentionally no external API requests."""
import json

import pytest

from scripts.collect_pulse_replay_batch import main


def test_help_has_no_unverified_owner_approval_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--run" in help_text
    assert "--owner-approved" not in help_text
    assert "--interval-seconds" in help_text


def test_without_run_creates_plan_only(tmp_path, capsys):
    folder = tmp_path / "replays"
    assert main(["--output", str(folder), "--hours", "3"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["requests_planned"] == 3
    assert plan["stored_windows"] == 0
    assert (folder / "pulse_batch_manifest.json").is_file()
    assert list(folder.glob("replay-at-*.json")) == []


def test_fast_run_rejected_before_network(tmp_path):
    folder = tmp_path / "replays"
    with pytest.raises(SystemExit) as exc:
        main(["--output", str(folder), "--run", "--interval-seconds", "5"])
    assert exc.value.code == 2
    assert not folder.exists()
