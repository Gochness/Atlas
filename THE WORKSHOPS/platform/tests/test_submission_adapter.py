"""
Tests fuer submission_adapter.py.

Nutzt ausschliesslich bereits vorhandene, sichere Pruefwege:
- _validate() aus submission_service.py ist rein lesend (kein Git-Zugriff)
  und wird unveraendert wiederverwendet, um zu beweisen, dass die vom
  Adapter serialisierte Datei den echten Validator besteht.
- submit() selbst wird in den Tests per monkeypatch ersetzt, damit kein
  echter Branch/Commit/Push/PR entsteht - der Adapter wird trotzdem
  vollstaendig bis zur Uebergabe an submit() durchlaufen.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import submission_adapter  # noqa: E402
from submission_service import SubmissionResult, _validate  # noqa: E402


def _real_head() -> str:
    return subprocess.run(
        "git rev-parse HEAD", shell=True, text=True, capture_output=True
    ).stdout.strip()


def _structured_test_data() -> dict:
    return {
        "submission": {
            "id": "S-TEST-ADAPTER",
            "type": "artifact",
            "action": "create",
            "target": None,
            "base_commit": _real_head(),
            "submitted_by": "pytest",
            "submitted_at": "2026-07-26T00:00:00Z",
        },
        "candidate": {
            "proposed_ref": "ART-9001",
            "claim": "Testbehauptung.",
            "basis": "Testgrundlage.",
            "counter": "Testgegenversuch.",
            "open": "Testoffene Punkte.",
        },
    }


def test_serialize_submission_round_trips_data():
    data = _structured_test_data()

    path = submission_adapter.serialize_submission(data)
    try:
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded == data
    finally:
        path.unlink(missing_ok=True)


def test_serialize_submission_passes_existing_validator():
    data = _structured_test_data()

    path = submission_adapter.serialize_submission(data)
    try:
        error = _validate(str(path))
        assert error is None
    finally:
        path.unlink(missing_ok=True)


def test_submit_structured_calls_submit_with_serialized_path(monkeypatch):
    captured_path: list[str] = []
    captured_content: list[dict] = []

    def fake_submit(yaml_path: str) -> SubmissionResult:
        captured_path.append(yaml_path)
        with open(yaml_path, encoding="utf-8") as f:
            captured_content.append(yaml.safe_load(f))
        return SubmissionResult(
            success=True,
            submission_id="S-TEST-ADAPTER",
            branch_name="submission/S-TEST-ADAPTER",
            commit_sha="deadbeef",
            pull_request_url="https://example.invalid/pr/0",
        )

    monkeypatch.setattr(submission_adapter, "submit", fake_submit)

    data = _structured_test_data()
    result = submission_adapter.submit_structured(data)

    assert len(captured_path) == 1
    assert captured_content[0] == data
    assert result.success is True
    assert result.submission_id == "S-TEST-ADAPTER"

    # Aufgeraeumt: die temporaere Datei existiert nach dem Aufruf nicht mehr.
    assert not Path(captured_path[0]).exists()


def test_submit_structured_cleans_up_even_if_submit_raises(monkeypatch):
    captured_path: list[str] = []

    def failing_submit(yaml_path: str) -> SubmissionResult:
        captured_path.append(yaml_path)
        raise RuntimeError("simulierter Fehler in submit()")

    monkeypatch.setattr(submission_adapter, "submit", failing_submit)

    with pytest.raises(RuntimeError):
        submission_adapter.submit_structured(_structured_test_data())

    assert len(captured_path) == 1
    assert not Path(captured_path[0]).exists()
