"""Tests fuer Atlas Orchestrierung V1.

Die Modelladapter werden nur an ihrer bestehenden generate()-Grenze
ersetzt. So wird geprueft, welchen Snapshot und Zusatzauftrag die
Orchestrierung an den wiederverwendeten Untersuchungszyklus uebergibt.
"""

import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atlas_search  # noqa: E402
import independent_run  # noqa: E402
import work_step  # noqa: E402
import work_orchestration  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_independent_runs(tmp_path, monkeypatch):
    runs_dir = tmp_path / "operational-state" / "independent-runs"
    monkeypatch.setattr(
        independent_run,
        "default_runs_dir",
        lambda: runs_dir,
    )
    monkeypatch.setattr(
        work_orchestration.openai_work_step,
        "_read_work_item",
        lambda work_item_id: {
            "id": work_item_id,
            "intent": "Testauftrag",
            "context_refs": [],
        },
    )
    return runs_dir


def _step(number: int, provider: str = "existing") -> dict:
    return {
        "id": f"WS-{number:04d}",
        "work_item_id": "WI-TEST",
        "participant_id": provider,
        "content": f"Inhalt {number}",
        "created_at": "2026-07-27T00:00:00Z",
    }


def _fake_runtime(monkeypatch, initial_steps, failing_provider=None):
    stored = list(initial_steps)
    calls = []

    monkeypatch.setattr(
        work_orchestration,
        "list_for_work_item",
        lambda _work_item_id: list(stored),
    )

    for provider, adapter in work_orchestration._ADAPTERS.items():
        def generate_content(
            work_item_id,
            work_steps_snapshot=None,
            additional_task=None,
            _provider=provider,
        ):
            calls.append({
                "provider": _provider,
                "work_item_id": work_item_id,
                "snapshot_ids": [
                    step["id"] for step in work_steps_snapshot
                ],
                "additional_task": additional_task,
            })
            if _provider == failing_provider:
                raise RuntimeError(f"{_provider} test failure")
            return _provider, f"Inhalt von {_provider}"

        def generate(
            work_item_id,
            work_steps_snapshot=None,
            additional_task=None,
            _provider=provider,
        ):
            calls.append({
                "provider": _provider,
                "work_item_id": work_item_id,
                "snapshot_ids": [
                    step["id"] for step in work_steps_snapshot
                ],
                "additional_task": additional_task,
            })
            if _provider == failing_provider:
                print(f"FEHLER: {_provider} test failure", file=sys.stderr)
                return 1
            stored.append(_step(len(stored) + 1, _provider))
            print(f"OK  {stored[-1]['id']}  test.yaml")
            return 0

        monkeypatch.setattr(adapter, "generate_content", generate_content)
        monkeypatch.setattr(adapter, "generate", generate)

    def publish(work_item_id, participant_id, content):
        stored.append(_step(len(stored) + 1, participant_id))
        stored[-1]["content"] = content
        return work_step.WorkStepResult(
            success=True,
            id=stored[-1]["id"],
            path=f"test/{stored[-1]['id']}.yaml",
        )

    monkeypatch.setattr(work_orchestration, "publish", publish)
    return stored, calls


def test_single_reuses_starting_snapshot(monkeypatch):
    initial = [_step(1), _step(2)]
    stored, calls = _fake_runtime(monkeypatch, initial)

    result = work_orchestration.run(
        "WI-TEST",
        "single",
        ["openai"],
    )

    assert result["success"] is True
    assert result["starting_snapshot_ids"] == ["WS-0001", "WS-0002"]
    assert calls[0]["snapshot_ids"] == ["WS-0001", "WS-0002"]
    assert len(stored) == 3


def test_independent_participants_receive_identical_snapshot(
    monkeypatch, isolated_independent_runs
):
    initial = [_step(1), _step(2), _step(3)]
    stored, calls = _fake_runtime(monkeypatch, initial)
    saved_states = []
    actual_save = independent_run.save_run

    def recording_save(run, runs_dir=None):
        saved_states.append(copy.deepcopy(run))
        return actual_save(run, runs_dir)

    monkeypatch.setattr(independent_run, "save_run", recording_save)

    result = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )

    assert result["success"] is True
    assert len(stored) == 6
    assert [call["snapshot_ids"] for call in calls] == [
        ["WS-0001", "WS-0002", "WS-0003"],
        ["WS-0001", "WS-0002", "WS-0003"],
        ["WS-0001", "WS-0002", "WS-0003"],
    ]
    assert any(
        saved["status"] == "running"
        and [
            state["status"] for state in saved["participant_states"]
        ] == ["completed_pending", "completed_pending", "completed_pending"]
        for saved in saved_states
    )
    persisted = independent_run.load_run(
        result["run_id"], isolated_independent_runs
    )
    assert persisted["status"] == "completed"
    assert [
        state["status"] for state in persisted["participant_states"]
    ] == ["published", "published", "published"]
    assert [
        state["work_step_id"] for state in persisted["participant_states"]
    ] == ["WS-0004", "WS-0005", "WS-0006"]
    assert [
        state["attempt_count"] for state in persisted["participant_states"]
    ] == [1, 1, 1]


def test_independent_keeps_successes_and_reports_failure(
    monkeypatch, isolated_independent_runs
):
    stored, calls = _fake_runtime(
        monkeypatch,
        [_step(1)],
        failing_provider="anthropic",
    )

    result = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )

    assert result["success"] is False
    assert len(calls) == 3
    assert len(stored) == 1
    assert [item["status"] for item in result["results"]] == [
        "completed_pending",
        "failed",
        "completed_pending",
    ]
    assert all(
        "work_step_id" not in item for item in result["results"]
    )
    persisted = independent_run.load_run(
        result["run_id"], isolated_independent_runs
    )
    assert persisted["status"] == "incomplete"
    assert [
        state["status"] for state in persisted["participant_states"]
    ] == ["completed_pending", "failed", "completed_pending"]
    assert persisted["participant_states"][0]["content"] == (
        "Inhalt von openai"
    )
    assert persisted["participant_states"][1]["error"] == (
        "FEHLER: anthropic test failure"
    )
    assert persisted["participant_states"][2]["content"] == (
        "Inhalt von gemini"
    )
    assert [
        state["attempt_count"] for state in persisted["participant_states"]
    ] == [1, 1, 1]


def test_refutation_chains_x_then_y_then_z(monkeypatch):
    initial = [_step(1), _step(2)]
    _stored, calls = _fake_runtime(monkeypatch, initial)

    result = work_orchestration.run(
        "WI-TEST",
        "refutation",
        ["openai", "anthropic", "gemini"],
    )

    assert result["success"] is True
    assert calls[0]["snapshot_ids"] == ["WS-0001", "WS-0002"]
    assert calls[0]["additional_task"] is None
    assert calls[1]["snapshot_ids"] == ["WS-0001", "WS-0002", "WS-0003"]
    assert "widerlegen" in calls[1]["additional_task"]
    assert calls[2]["snapshot_ids"] == [
        "WS-0001",
        "WS-0002",
        "WS-0003",
        "WS-0004",
    ]
    assert "kein Schiedsrichter" in calls[2]["additional_task"]


def test_refutation_aborts_chain_after_failed_y(monkeypatch):
    _stored, calls = _fake_runtime(
        monkeypatch,
        [_step(1)],
        failing_provider="anthropic",
    )
    statuses = []

    result = work_orchestration.run(
        "WI-TEST",
        "refutation",
        ["openai", "anthropic", "gemini"],
        status_callback=statuses.append,
    )

    assert result["success"] is False
    assert [call["provider"] for call in calls] == ["openai", "anthropic"]
    assert statuses[-1]["state"] == "aborted"
    assert statuses[-1]["phase"] == "Y"


def test_independent_hides_early_result_until_publication(
    tmp_path, monkeypatch, isolated_independent_runs
):
    work_items_dir = tmp_path / "THE VAULT" / "work_items"
    work_steps_dir = tmp_path / "THE VAULT" / "work_steps"
    work_items_dir.mkdir(parents=True)
    work_steps_dir.mkdir(parents=True)
    (work_items_dir / "WI-0001.yaml").write_text(
        "id: WI-0001\nintent: Test\n", encoding="utf-8"
    )
    marker = "NUR-IN-ZURUECKGEHALTENEM-ERGEBNIS-4711"
    observations = {}

    monkeypatch.setattr(
        work_orchestration,
        "list_for_work_item",
        lambda work_item_id: work_step.list_for_work_item(
            work_item_id, work_steps_dir
        ),
    )
    monkeypatch.setattr(
        work_orchestration,
        "publish",
        lambda **kwargs: work_step.publish(
            **kwargs,
            work_items_dir=work_items_dir,
            work_steps_dir=work_steps_dir,
        ),
    )

    def first_content(*_args, **_kwargs):
        return "openai:test", marker

    def second_content(*_args, **_kwargs):
        observations["files"] = list(work_steps_dir.glob("WS-*.yaml"))
        observations["search"] = atlas_search.search(marker, tmp_path)
        observations["index"] = atlas_search.format_knowledge_index(
            atlas_search.build_knowledge_index(tmp_path)
        )
        return "anthropic:test", "Zweites Ergebnis"

    monkeypatch.setattr(
        work_orchestration._ADAPTERS["openai"],
        "generate_content",
        first_content,
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["anthropic"],
        "generate_content",
        second_content,
    )

    result = work_orchestration.run(
        "WI-0001", "independent", ["openai", "anthropic"]
    )

    assert result["success"] is True
    assert observations["files"] == []
    assert observations["search"] == []
    assert marker not in observations["index"]
    published = work_step.list_for_work_item("WI-0001", work_steps_dir)
    assert [step["participant_id"] for step in published] == [
        "openai:test",
        "anthropic:test",
    ]
    assert marker in published[0]["content"]
    assert atlas_search.search(marker, tmp_path)[0]["path"].endswith(
        "WS-0001.yaml"
    )
    assert [item["work_step_id"] for item in result["results"]] == [
        "WS-0001",
        "WS-0002",
    ]
    persisted = independent_run.load_run(
        result["run_id"], isolated_independent_runs
    )
    assert persisted["original_input"]["intent"] == "Testauftrag"
    assert persisted["original_input"]["starting_snapshot"] == []


def test_independent_publication_failure_does_not_stop_later_publish(
    monkeypatch, isolated_independent_runs
):
    stored = []
    published_participants = []
    monkeypatch.setattr(
        work_orchestration,
        "list_for_work_item",
        lambda _work_item_id: list(stored),
    )
    for provider, adapter in work_orchestration._ADAPTERS.items():
        monkeypatch.setattr(
            adapter,
            "generate_content",
            lambda *_args, _provider=provider, **_kwargs: (
                f"{_provider}:test",
                f"Inhalt {_provider}",
            ),
        )

    def publish(work_item_id, participant_id, content):
        published_participants.append(participant_id)
        if participant_id == "anthropic:test":
            return work_step.WorkStepResult(
                success=False,
                error="simulierter Publikationsfehler",
            )
        step = _step(len(stored) + 1, participant_id)
        step["content"] = content
        stored.append(step)
        return work_step.WorkStepResult(
            success=True,
            id=step["id"],
            path=f"test/{step['id']}.yaml",
        )

    monkeypatch.setattr(work_orchestration, "publish", publish)

    result = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )

    assert result["success"] is False
    assert published_participants == [
        "openai:test",
        "anthropic:test",
        "gemini:test",
    ]
    assert [step["participant_id"] for step in stored] == [
        "openai:test",
        "gemini:test",
    ]
    assert result["results"][0]["work_step_id"] == "WS-0001"
    assert "work_step_id" not in result["results"][1]
    assert result["results"][1]["status"] == "failed"
    assert "Publikation nach fachlichem Abschluss fehlgeschlagen" in (
        result["results"][1]["error"]
    )
    assert result["results"][2]["work_step_id"] == "WS-0002"
    persisted = independent_run.load_run(
        result["run_id"], isolated_independent_runs
    )
    assert persisted["status"] == "partially_published"
    assert [
        state["status"] for state in persisted["participant_states"]
    ] == ["published", "publication_failed", "published"]


def test_independent_runs_for_same_work_item_have_distinct_ids(
    monkeypatch, isolated_independent_runs
):
    _stored, _calls = _fake_runtime(monkeypatch, [])

    first = work_orchestration.run(
        "WI-TEST", "independent", ["openai", "anthropic"]
    )
    second = work_orchestration.run(
        "WI-TEST", "independent", ["openai", "anthropic"]
    )

    assert first["run_id"] != second["run_id"]
    assert len(list(isolated_independent_runs.glob("*.json"))) == 2
    assert independent_run.load_run(first["run_id"])["status"] == "completed"
    assert independent_run.load_run(second["run_id"])["status"] == "completed"


def test_incomplete_persistent_result_stays_outside_knowledge_space(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "repo"
    work_items_dir = repo_root / "THE VAULT" / "work_items"
    work_steps_dir = repo_root / "THE VAULT" / "work_steps"
    runs_dir = tmp_path / "operational-state" / "independent-runs"
    work_items_dir.mkdir(parents=True)
    work_steps_dir.mkdir(parents=True)
    (work_items_dir / "WI-0001.yaml").write_text(
        "id: WI-0001\nintent: Test\n", encoding="utf-8"
    )
    marker = "PERSISTENT-ABER-NICHT-PUBLIZIERT-815"

    monkeypatch.setattr(
        independent_run,
        "default_runs_dir",
        lambda: runs_dir,
    )
    monkeypatch.setattr(
        work_orchestration,
        "list_for_work_item",
        lambda work_item_id: work_step.list_for_work_item(
            work_item_id, work_steps_dir
        ),
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["openai"],
        "generate_content",
        lambda *_args, **_kwargs: ("openai:test", marker),
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["anthropic"],
        "generate_content",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("kontrollierter Fehler")
        ),
    )

    result = work_orchestration.run(
        "WI-0001", "independent", ["openai", "anthropic"]
    )

    assert result["success"] is False
    assert list(work_steps_dir.glob("WS-*.yaml")) == []
    assert atlas_search.search(marker, repo_root) == []
    assert marker not in atlas_search.format_knowledge_index(
        atlas_search.build_knowledge_index(repo_root)
    )
    persisted = independent_run.load_run(result["run_id"], runs_dir)
    assert persisted["participant_states"][0]["content"] == marker
    assert not runs_dir.is_relative_to(repo_root)
    read_result = atlas_search.execute_tool(
        atlas_search.READ_TOOL_NAME,
        {"path": str(runs_dir / f"{result['run_id']}.json")},
        repo_root,
    )
    assert "Absoluter Pfad ist nicht erlaubt" in read_result["error"]


def test_retry_last_failed_participant_loads_run_and_publishes_all(
    monkeypatch, isolated_independent_runs
):
    initial = [_step(1), _step(2)]
    stored, _calls = _fake_runtime(
        monkeypatch,
        initial,
        failing_provider="gemini",
    )
    first = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )
    retry_calls = []

    for provider in ("openai", "anthropic"):
        monkeypatch.setattr(
            work_orchestration._ADAPTERS[provider],
            "generate_content",
            lambda *_args, _provider=provider, **_kwargs: (
                _ for _ in ()
            ).throw(AssertionError(f"{_provider} wurde erneut ausgefuehrt")),
        )

    def retry_gemini(
        work_item_id,
        work_steps_snapshot=None,
        additional_task=None,
    ):
        retry_calls.append({
            "work_item_id": work_item_id,
            "snapshot": copy.deepcopy(work_steps_snapshot),
            "additional_task": additional_task,
        })
        return "gemini:retry", "Gemini nach Retry"

    monkeypatch.setattr(
        work_orchestration._ADAPTERS["gemini"],
        "generate_content",
        retry_gemini,
    )

    retried = work_orchestration.retry_independent_participant(
        first["run_id"],
        "gemini",
        isolated_independent_runs,
    )

    assert retried["success"] is True
    assert retried["run_id"] == first["run_id"]
    assert retried["status"] == "completed"
    assert retry_calls == [{
        "work_item_id": "WI-TEST",
        "snapshot": initial,
        "additional_task": None,
    }]
    assert len(stored) == 5
    assert [step["participant_id"] for step in stored[2:]] == [
        "openai",
        "anthropic",
        "gemini:retry",
    ]
    persisted = independent_run.load_run(
        first["run_id"], isolated_independent_runs
    )
    assert [
        state["status"] for state in persisted["participant_states"]
    ] == ["published", "published", "published"]
    assert [
        state["attempt_count"] for state in persisted["participant_states"]
    ] == [1, 1, 2]


def test_retry_one_of_two_failures_does_not_publish(
    monkeypatch, isolated_independent_runs
):
    stored = []
    monkeypatch.setattr(
        work_orchestration,
        "list_for_work_item",
        lambda _work_item_id: list(stored),
    )
    for provider, adapter in work_orchestration._ADAPTERS.items():
        if provider == "openai":
            result = ("openai:first", "OpenAI pending")
            monkeypatch.setattr(
                adapter,
                "generate_content",
                lambda *_args, _result=result, **_kwargs: _result,
            )
        else:
            monkeypatch.setattr(
                adapter,
                "generate_content",
                lambda *_args, _provider=provider, **_kwargs: (
                    _ for _ in ()
                ).throw(RuntimeError(f"{_provider} initial failure")),
            )
    publish_calls = []
    monkeypatch.setattr(
        work_orchestration,
        "publish",
        lambda **kwargs: publish_calls.append(kwargs),
    )
    first = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["anthropic"],
        "generate_content",
        lambda *_args, **_kwargs: ("anthropic:retry", "Claude pending"),
    )

    retried = work_orchestration.retry_independent_participant(
        first["run_id"],
        "anthropic",
        isolated_independent_runs,
    )

    assert retried["success"] is True
    assert retried["status"] == "incomplete"
    assert publish_calls == []
    assert [
        state["status"] for state in retried["participant_states"]
    ] == ["completed_pending", "completed_pending", "failed"]
    assert [
        state["attempt_count"] for state in retried["participant_states"]
    ] == [1, 2, 1]


def test_failed_retry_preserves_other_pending_results(
    monkeypatch, isolated_independent_runs
):
    _stored, _calls = _fake_runtime(
        monkeypatch,
        [],
        failing_provider="gemini",
    )
    first = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )
    before = independent_run.load_run(
        first["run_id"], isolated_independent_runs
    )
    pending_before = [
        copy.deepcopy(state)
        for state in before["participant_states"][:2]
    ]

    retried = work_orchestration.retry_independent_participant(
        first["run_id"],
        "gemini",
        isolated_independent_runs,
    )

    assert retried["success"] is False
    assert retried["status"] == "incomplete"
    assert retried["participant_states"][:2] == pending_before
    assert retried["participant_states"][2]["status"] == "failed"
    assert retried["participant_states"][2]["attempt_count"] == 2


def test_retry_rejects_unknown_or_non_retryable_target(
    monkeypatch, isolated_independent_runs
):
    _stored, _calls = _fake_runtime(
        monkeypatch,
        [],
        failing_provider="gemini",
    )
    incomplete = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )

    with pytest.raises(ValueError, match="nicht gefunden"):
        work_orchestration.retry_independent_participant(
            "0" * 32,
            "gemini",
            isolated_independent_runs,
        )
    with pytest.raises(ValueError, match="gehoert nicht"):
        work_orchestration.retry_independent_participant(
            incomplete["run_id"],
            "fremd",
            isolated_independent_runs,
        )
    with pytest.raises(ValueError, match="completed_pending"):
        work_orchestration.retry_independent_participant(
            incomplete["run_id"],
            "openai",
            isolated_independent_runs,
        )
    interrupted = independent_run.load_run(
        incomplete["run_id"], isolated_independent_runs
    )
    openai_state = independent_run.participant_state(
        interrupted, "openai"
    )
    openai_state["status"] = "working"
    independent_run.save_run(interrupted, isolated_independent_runs)
    with pytest.raises(ValueError, match="working"):
        work_orchestration.retry_independent_participant(
            incomplete["run_id"],
            "openai",
            isolated_independent_runs,
        )
    openai_state["status"] = "completed_pending"
    independent_run.save_run(interrupted, isolated_independent_runs)

    monkeypatch.setattr(
        work_orchestration._ADAPTERS["gemini"],
        "generate_content",
        lambda *_args, **_kwargs: ("gemini:retry", "Erfolg"),
    )
    completed = work_orchestration.retry_independent_participant(
        incomplete["run_id"],
        "gemini",
        isolated_independent_runs,
    )
    assert completed["status"] == "completed"
    with pytest.raises(ValueError, match="completed"):
        work_orchestration.retry_independent_participant(
            incomplete["run_id"],
            "gemini",
            isolated_independent_runs,
        )


def test_retry_context_excludes_pending_results(
    monkeypatch, isolated_independent_runs
):
    starting_snapshot = [_step(1)]
    marker_openai = "GEHEIM-PENDING-OPENAI-811"
    marker_anthropic = "GEHEIM-PENDING-CLAUDE-812"
    stored = list(starting_snapshot)
    monkeypatch.setattr(
        work_orchestration,
        "list_for_work_item",
        lambda _work_item_id: list(stored),
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["openai"],
        "generate_content",
        lambda *_args, **_kwargs: ("openai:test", marker_openai),
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["anthropic"],
        "generate_content",
        lambda *_args, **_kwargs: ("anthropic:test", marker_anthropic),
    )
    monkeypatch.setattr(
        work_orchestration._ADAPTERS["gemini"],
        "generate_content",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("initial failure")
        ),
    )
    first = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )
    observed = {}

    def retry_gemini(
        _work_item_id,
        work_steps_snapshot=None,
        **_kwargs,
    ):
        observed["snapshot"] = copy.deepcopy(work_steps_snapshot)
        return "gemini:retry", "Gemini fertig"

    monkeypatch.setattr(
        work_orchestration._ADAPTERS["gemini"],
        "generate_content",
        retry_gemini,
    )

    work_orchestration.retry_independent_participant(
        first["run_id"],
        "gemini",
        isolated_independent_runs,
    )

    assert observed["snapshot"] == starting_snapshot
    assert marker_openai not in str(observed["snapshot"])
    assert marker_anthropic not in str(observed["snapshot"])


def test_publication_failure_after_retry_does_not_repeat_provider(
    monkeypatch, isolated_independent_runs
):
    _stored, _calls = _fake_runtime(
        monkeypatch,
        [],
        failing_provider="gemini",
    )
    first = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic", "gemini"],
    )
    retry_calls = []

    def retry_gemini(*_args, **_kwargs):
        retry_calls.append("gemini")
        return "gemini:retry", "Gemini fertig"

    monkeypatch.setattr(
        work_orchestration._ADAPTERS["gemini"],
        "generate_content",
        retry_gemini,
    )

    def failing_publish(work_item_id, participant_id, content):
        if participant_id == "anthropic":
            return work_step.WorkStepResult(
                success=False,
                error="kontrollierter Publikationsfehler",
            )
        return work_step.WorkStepResult(
            success=True,
            id=f"WS-{len(participant_id):04d}",
            path="test.yaml",
        )

    monkeypatch.setattr(
        work_orchestration,
        "publish",
        failing_publish,
    )

    retried = work_orchestration.retry_independent_participant(
        first["run_id"],
        "gemini",
        isolated_independent_runs,
    )

    assert retried["success"] is False
    assert retried["status"] == "partially_published"
    assert retry_calls == ["gemini"]
    assert [
        state["status"] for state in retried["participant_states"]
    ] == ["published", "publication_failed", "published"]


def test_retry_cli_returns_structured_result(monkeypatch, capsys):
    run_id = "a" * 32
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "work_orchestration.py",
            "retry-independent",
            "--run-id",
            run_id,
            "--provider",
            "gemini",
        ],
    )
    monkeypatch.setattr(
        work_orchestration,
        "retry_independent_participant",
        lambda received_run_id, provider: {
            "success": True,
            "run_id": received_run_id,
            "work_item_id": "WI-TEST",
            "mode": "independent",
            "retried_provider": provider,
            "status": "completed",
            "participant_states": [],
            "error": None,
        },
    )

    with pytest.raises(SystemExit) as exit_info:
        work_orchestration.main()

    assert exit_info.value.code == 0
    output = __import__("json").loads(capsys.readouterr().out)
    assert output["run_id"] == run_id
    assert output["retried_provider"] == "gemini"
    assert output["status"] == "completed"


def test_retry_cli_transports_invalid_run_error(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "work_orchestration.py",
            "retry-independent",
            "--run-id",
            "b" * 32,
            "--provider",
            "openai",
        ],
    )
    monkeypatch.setattr(
        work_orchestration,
        "retry_independent_participant",
        lambda *_args: (_ for _ in ()).throw(
            ValueError("IndependentRun nicht gefunden")
        ),
    )

    with pytest.raises(SystemExit) as exit_info:
        work_orchestration.main()

    assert exit_info.value.code == 1
    assert "IndependentRun nicht gefunden" in capsys.readouterr().err


def _status(number: int) -> dict:
    return {
        "state": "working",
        "mode": "independent",
        "phase": "independent",
        "message": f"Status {number}",
        "work_item_id": "WI-TEST",
        "participants": ["openai", "anthropic"],
        "starting_snapshot_ids": [],
        "results": [],
        "run_id": "a" * 32,
    }


def test_status_file_repeated_writes_are_atomic_and_leave_no_tempfiles(
    tmp_path,
):
    path = tmp_path / "atlas-orchestration-v1-status.json"
    callback = work_orchestration._status_file_callback(path)

    for number in range(50):
        callback(_status(number))

    assert json.loads(path.read_text(encoding="utf-8")) == _status(49)
    assert list(tmp_path.glob(f"{path.name}.*.tmp")) == []


def test_status_file_uses_unique_temporary_name_per_write(
    tmp_path, monkeypatch
):
    path = tmp_path / "atlas-orchestration-v1-status.json"
    callback = work_orchestration._status_file_callback(path)
    temporary_names = []
    actual_replace = Path.replace

    def recording_replace(source, target):
        temporary_names.append(source.name)
        return actual_replace(source, target)

    monkeypatch.setattr(Path, "replace", recording_replace)

    callback(_status(1))
    callback(_status(2))

    assert len(temporary_names) == 2
    assert len(set(temporary_names)) == 2
    assert all(
        name.startswith(f"{path.name}.") and name.endswith(".tmp")
        for name in temporary_names
    )


def test_parallel_status_writes_do_not_share_temporary_file(tmp_path):
    path = tmp_path / "atlas-orchestration-v1-status.json"
    callback = work_orchestration._status_file_callback(path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(callback, [_status(number) for number in range(40)]))

    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["work_item_id"] == "WI-TEST"
    assert content["message"].startswith("Status ")
    assert list(tmp_path.glob(f"{path.name}.*.tmp")) == []


def test_status_write_retries_transient_windows_permission_error(
    tmp_path, monkeypatch
):
    path = tmp_path / "atlas-orchestration-v1-status.json"
    callback = work_orchestration._status_file_callback(path)
    actual_replace = Path.replace
    attempts = []

    def temporarily_blocked_replace(source, target):
        attempts.append(source.name)
        if len(attempts) < 3:
            raise PermissionError(5, "simulierte Windows-Dateisperre")
        return actual_replace(source, target)

    monkeypatch.setattr(Path, "replace", temporarily_blocked_replace)
    monkeypatch.setattr(work_orchestration.time, "sleep", lambda _delay: None)

    callback(_status(7))

    assert len(attempts) == 3
    assert json.loads(path.read_text(encoding="utf-8")) == _status(7)
    assert list(tmp_path.glob(f"{path.name}.*.tmp")) == []


def test_orchestration_report_can_write_status_repeatedly(
    tmp_path, monkeypatch
):
    _stored, _calls = _fake_runtime(monkeypatch, [])
    path = tmp_path / "atlas-orchestration-v1-status.json"

    result = work_orchestration.run(
        "WI-TEST",
        "independent",
        ["openai", "anthropic"],
        status_callback=work_orchestration._status_file_callback(path),
    )

    assert result["success"] is True
    persisted_status = json.loads(path.read_text(encoding="utf-8"))
    assert persisted_status["state"] == "completed"
    assert persisted_status["work_item_id"] == "WI-TEST"
    assert persisted_status["run_id"] == result["run_id"]
    assert list(tmp_path.glob(f"{path.name}.*.tmp")) == []


@pytest.mark.parametrize(
    ("mode", "participants"),
    [
        ("single", []),
        ("single", ["openai", "anthropic"]),
        ("independent", ["openai"]),
        ("refutation", ["openai", "anthropic"]),
        ("independent", ["openai", "openai"]),
        ("single", ["unknown"]),
    ],
)
def test_invalid_configuration_is_rejected(mode, participants):
    with pytest.raises(ValueError):
        work_orchestration.validate_configuration(mode, participants)
