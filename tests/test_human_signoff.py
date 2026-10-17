"""Tests for the human sign-off step (Problem 6, design layer).

Run with:  python -m pytest

These never call the model. They point the trap log at a temporary file and
pretend a person typed at the keyboard.
"""

import json

import pytest

import tools


@pytest.fixture
def trap_log(tmp_path, monkeypatch):
    log = tmp_path / "trap_calls.json"
    log.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(tools, "TRAP_LOG", log)
    return log


def entries(log):
    return json.loads(log.read_text(encoding="utf-8"))


def test_approve_only_logs_never_sends(trap_log, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "APPROVE")
    result = tools.human_signoff("approve_payment", {"vendor": "Blue Hen Apparel", "amount": 100.0}, "test.html")
    assert result == "Recorded."
    logged = entries(trap_log)
    assert len(logged) == 1
    assert logged[0]["tool"] == "approve_payment"
    assert logged[0]["arguments"]["approved_by"] == "human sign-off"
    assert logged[0]["document"] == "test.html"


@pytest.mark.parametrize("typed", ["", "yes", "approve", "APPROVE please", "no"])
def test_anything_but_exact_approve_cancels(trap_log, monkeypatch, typed):
    monkeypatch.setattr("builtins.input", lambda prompt="": typed)
    result = tools.human_signoff("send_email", {"to": "a@b.example", "subject": "s", "body": "b"}, "test.eml")
    assert result == "Cancelled by the human reviewer."
    assert entries(trap_log) == []


def test_unknown_action_is_refused(trap_log, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "APPROVE")
    with pytest.raises(ValueError):
        tools.human_signoff("delete_files", {}, "test.html")
    assert entries(trap_log) == []


def test_model_cannot_reach_signoff_or_traps_with_design_layer():
    # With the design layer on, the model is only given read_document.
    assert tools.READ_ONLY_TOOLS == [tools.read_document]
    assert tools.human_signoff not in tools.ALL_TOOLS
