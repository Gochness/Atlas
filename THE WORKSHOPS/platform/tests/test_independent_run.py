"""Tests fuer persistenten technischen IndependentRun-Zustand."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import independent_run  # noqa: E402


def _create(runs_dir: Path) -> dict:
    return independent_run.create_run(
        {
            "id": "WI-0042",
            "intent": "Persistenz pruefen",
            "context_refs": ["ART-0001"],
        },
        ["openai", "anthropic"],
        [
            {
                "id": "WS-0007",
                "work_item_id": "WI-0042",
                "participant_id": "earlier",
                "content": "Ausgangsstand",
                "created_at": "2026-07-28T00:00:00Z",
            }
        ],
        runs_dir,
    )


def test_create_and_load_preserves_original_input(tmp_path):
    run = _create(tmp_path)

    loaded = independent_run.load_run(run["run_id"], tmp_path)

    assert loaded["run_id"] == run["run_id"]
    assert loaded["work_item_id"] == "WI-0042"
    assert loaded["mode"] == "independent"
    assert loaded["original_input"] == {
        "intent": "Persistenz pruefen",
        "context_refs": ["ART-0001"],
        "starting_snapshot": [
            {
                "id": "WS-0007",
                "work_item_id": "WI-0042",
                "participant_id": "earlier",
                "content": "Ausgangsstand",
                "created_at": "2026-07-28T00:00:00Z",
            }
        ],
    }
    assert [state["status"] for state in loaded["participant_states"]] == [
        "pending",
        "pending",
    ]
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_and_reload_completed_pending_content(tmp_path):
    run = _create(tmp_path)
    state = independent_run.participant_state(run, "openai")
    state.update({
        "status": "completed_pending",
        "participant_id": "openai:model",
        "content": "Noch nicht publiziert",
    })
    run["status"] = "incomplete"

    independent_run.save_run(run, tmp_path)
    del run
    loaded = independent_run.load_run(
        next(tmp_path.glob("*.json")).stem,
        tmp_path,
    )

    assert loaded["status"] == "incomplete"
    assert loaded["participant_states"][0]["content"] == (
        "Noch nicht publiziert"
    )
    assert loaded["participant_states"][0]["work_step_id"] is None


def test_load_rejects_corrupt_or_structurally_invalid_state(tmp_path):
    run = _create(tmp_path)
    path = tmp_path / f"{run['run_id']}.json"
    path.write_text("{kein json", encoding="utf-8")

    with pytest.raises(ValueError, match="kann nicht gelesen"):
        independent_run.load_run(run["run_id"], tmp_path)

    path.write_text(
        json.dumps({
            **run,
            "participant_states": [
                {
                    **run["participant_states"][0],
                    "status": "completed_pending",
                },
                run["participant_states"][1],
            ],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="besitzt kein Ergebnis"):
        independent_run.load_run(run["run_id"], tmp_path)


def test_load_rejects_path_traversal_as_run_id(tmp_path):
    with pytest.raises(ValueError, match="run_id"):
        independent_run.load_run("../fremd", tmp_path)


def test_load_upgrades_pre_counter_schema(tmp_path):
    run = _create(tmp_path)
    path = tmp_path / f"{run['run_id']}.json"
    legacy = {
        **run,
        "schema_version": independent_run.LEGACY_SCHEMA_VERSION,
        "participant_states": [
            {
                key: value
                for key, value in state.items()
                if key != "attempt_count"
            }
            for state in run["participant_states"]
        ],
    }
    legacy["participant_states"][0].update({
        "status": "failed",
        "error": "frueherer Fehler",
    })
    path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = independent_run.load_run(run["run_id"], tmp_path)

    assert loaded["schema_version"] == independent_run.SCHEMA_VERSION
    assert [
        state["attempt_count"] for state in loaded["participant_states"]
    ] == [1, 0]


def test_find_latest_incomplete_run_is_deterministic(tmp_path):
    older = _create(tmp_path)
    older["status"] = "incomplete"
    older["updated_at"] = "2026-07-28T10:00:00+00:00"
    independent_run.save_run(older, tmp_path)
    newer = _create(tmp_path)
    newer["status"] = "incomplete"
    independent_run.save_run(newer, tmp_path)
    completed = _create(tmp_path)
    completed["status"] = "completed"
    independent_run.save_run(completed, tmp_path)

    found = independent_run.find_latest_incomplete_run(
        "WI-0042",
        tmp_path,
    )

    assert found is not None
    assert found["run_id"] == newer["run_id"]
    assert independent_run.find_latest_incomplete_run(
        "WI-9999",
        tmp_path,
    ) is None
