"""
Tests fuer submit_structured.py (CLI-Wrapper).

submit_structured() aus submission_adapter.py wird per monkeypatch
ersetzt - kein echter Aufruf von submission_service.submit(), also kein
Branch, kein Push, kein PR. Geprueft wird ausschliesslich das Verhalten
des CLI-Wrappers selbst: JSON-Parsing, unveraenderte Weitergabe der
Daten, Ausgabeformat im bestehenden Stil (vgl. submit.py).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import submit_structured  # noqa: E402
from submission_service import SubmissionResult  # noqa: E402


def _structured_test_data() -> dict:
    return {
        "submission": {
            "id": "S-TEST-CLI",
            "type": "artifact",
            "action": "create",
            "target": None,
            "base_commit": "0123456",
            "submitted_by": "pytest",
            "submitted_at": "2026-07-26T00:00:00Z",
        },
        "candidate": {
            "proposed_ref": "ART-9002",
            "claim": "Testbehauptung.",
            "basis": "Testgrundlage.",
            "counter": "Testgegenversuch.",
            "open": "Testoffene Punkte.",
        },
    }


def test_valid_json_is_parsed_and_passed_unchanged(monkeypatch, capsys):
    captured_data: list[dict] = []

    def fake_submit_structured(data: dict) -> SubmissionResult:
        captured_data.append(data)
        return SubmissionResult(
            success=True,
            submission_id="S-TEST-CLI",
            pull_request_url="https://example.invalid/pr/0",
        )

    monkeypatch.setattr(submit_structured, "submit_structured", fake_submit_structured)

    data = _structured_test_data()
    import json as json_module

    monkeypatch.setattr(sys, "argv", ["submit_structured.py", json_module.dumps(data)])

    submit_structured.main()

    assert captured_data == [data]

    out = capsys.readouterr().out
    assert out.strip() == "OK  S-TEST-CLI  https://example.invalid/pr/0"


def test_failure_result_reports_error_and_exits_nonzero(monkeypatch, capsys):
    def fake_submit_structured(_data: dict) -> SubmissionResult:
        return SubmissionResult(success=False, error="Validierung fehlgeschlagen.")

    monkeypatch.setattr(submit_structured, "submit_structured", fake_submit_structured)
    monkeypatch.setattr(
        sys, "argv", ["submit_structured.py", '{"submission": {}, "candidate": {}}']
    )

    with pytest.raises(SystemExit) as exc_info:
        submit_structured.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert out.strip() == "FEHLER: Validierung fehlgeschlagen."


def test_invalid_json_reports_error_without_calling_submit_structured(monkeypatch, capsys):
    called = False

    def fake_submit_structured(_data: dict) -> SubmissionResult:
        nonlocal called
        called = True
        return SubmissionResult(success=True)

    monkeypatch.setattr(submit_structured, "submit_structured", fake_submit_structured)
    monkeypatch.setattr(sys, "argv", ["submit_structured.py", "{nicht valides json"])

    with pytest.raises(SystemExit) as exc_info:
        submit_structured.main()

    assert exc_info.value.code == 1
    assert called is False
    out = capsys.readouterr().out
    assert out.startswith("FEHLER: Eingabe ist kein gueltiges JSON")


def test_missing_argument_reports_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["submit_structured.py"])

    with pytest.raises(SystemExit) as exc_info:
        submit_structured.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Verwendung:" in out
