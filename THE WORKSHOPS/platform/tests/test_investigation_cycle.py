"""Tests fuer den internen Untersuchungszyklus V1 (Mehrschrittprozess mit
Werkzeugaufrufen) ueber alle drei Modell-Adapter hinweg. Prueft: ein
Werkzeugaufruf gefolgt von einer abschliessenden Textantwort, sowie den
technischen Sicherheitsabbruch bei Erreichen von MAX_INVESTIGATION_STEPS.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atlas_search  # noqa: E402
import anthropic_work_step  # noqa: E402
import gemini_work_step  # noqa: E402
import openai_work_step  # noqa: E402
import work_step  # noqa: E402


def _response(payload: dict) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# OpenAI (Responses API)
# ---------------------------------------------------------------------------

def test_openai_investigation_completes_after_one_search_round(tmp_path, monkeypatch):
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    (tmp_path / "THE NORTH STAR" / "DOC.md").write_text(
        "Enthaelt Fundament-Beleg-42", encoding="utf-8"
    )
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)

    first = _response({
        "id": "resp_1",
        "output": [{
            "type": "function_call",
            "name": atlas_search.READ_TOOL_NAME,
            "call_id": "call_1",
            "arguments": json.dumps({"path": "THE NORTH STAR/DOC.md"}),
        }],
    })
    second = _response({
        "id": "resp_2",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": "Abschliessende Antwort"}],
        }],
    })
    responses = [first, second]
    timeouts = []

    def fake_urlopen(request, timeout):
        timeouts.append(timeout)
        return responses.pop(0)

    with patch.object(openai_work_step, "urlopen", fake_urlopen):
        text = openai_work_step._request_model("key", "model", "context")

    assert text.startswith("Abschliessende Antwort")
    assert "THE NORTH STAR/DOC.md" in text
    assert "dokumentation" in text
    assert timeouts == [
        openai_work_step.REGULAR_REQUEST_TIMEOUT_SECONDS,
        openai_work_step.REGULAR_REQUEST_TIMEOUT_SECONDS,
    ]


def test_openai_search_only_round_lists_no_used_source(tmp_path, monkeypatch):
    """Ein reiner Suchtreffer (kein read_atlas_source) darf NICHT als
    verwendete Grundlage erscheinen - siehe Auftrag "Suchtreffer allein
    sind nicht automatisch verwendete Grundlagen"."""
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    (tmp_path / "THE NORTH STAR" / "DOC.md").write_text(
        "Enthaelt Fundament-Beleg-42", encoding="utf-8"
    )
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)

    first = _response({
        "id": "resp_1",
        "output": [{
            "type": "function_call",
            "name": atlas_search.SEARCH_TOOL_NAME,
            "call_id": "call_1",
            "arguments": json.dumps({"query": "Fundament-Beleg-42"}),
        }],
    })
    second = _response({
        "id": "resp_2",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": "Antwort nach reiner Suche"}],
        }],
    })
    responses = [first, second]

    def fake_urlopen(request, timeout):
        return responses.pop(0)

    with patch.object(openai_work_step, "urlopen", fake_urlopen):
        text = openai_work_step._request_model("key", "model", "context")

    assert text == "Antwort nach reiner Suche"
    assert "Technisch nachgewiesen" not in text


def test_openai_investigation_aborts_at_safety_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    call_count = {"n": 0}
    timeouts = []
    trace = atlas_search.InvestigationTrace(
        "WI-TEST",
        "openai:test-model",
        tmp_path / "traces",
    )

    def fake_urlopen(request, timeout):
        call_count["n"] += 1
        timeouts.append(timeout)
        return _response({
            "id": f"resp_{call_count['n']}",
            "output": [{
                "type": "function_call",
                "name": atlas_search.SEARCH_TOOL_NAME,
                "call_id": f"call_{call_count['n']}",
                "arguments": json.dumps({"query": "irrelevant"}),
            }],
        })

    with patch.object(openai_work_step, "urlopen", fake_urlopen):
        try:
            openai_work_step._request_model(
                "key",
                "model",
                "context",
                trace,
            )
            assert False, "haette RuntimeError ausloesen muessen"
        except RuntimeError as error:
            assert "Sicherheitsgrenze" in str(error)
            assert "technisch abgebrochen" in str(error)

    assert call_count["n"] == atlas_search.MAX_INVESTIGATION_STEPS + 1
    assert timeouts == [
        *[
            openai_work_step.REGULAR_REQUEST_TIMEOUT_SECONDS
            for _ in range(atlas_search.MAX_INVESTIGATION_STEPS)
        ],
        openai_work_step.COMPLETION_REQUEST_TIMEOUT_SECONDS,
    ]
    entries = [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]
    tool_entries = [entry for entry in entries if "tool" in entry]
    assert len(tool_entries) == atlas_search.MAX_INVESTIGATION_STEPS
    assert [entry["round"] for entry in tool_entries] == list(
        range(1, atlas_search.MAX_INVESTIGATION_STEPS + 1)
    )
    assert all(entry["participant"] == "openai:test-model" for entry in entries)
    assert all(entry["tool"] == atlas_search.SEARCH_TOOL_NAME for entry in tool_entries)
    assert all(entry["query"] == "irrelevant" for entry in tool_entries)
    assert all(entry["result_count"] == 0 for entry in tool_entries)
    assert all(entry["success"] is True for entry in tool_entries)
    cycle_events = [
        entry for entry in entries
        if entry.get("event", "").startswith("completion_phase_")
    ]
    assert cycle_events[-2]["event"] == "completion_phase_started"
    assert cycle_events[-1]["event"] == "completion_phase_tool_request_rejected"


def test_openai_unbounded_diagnostic_continues_past_budget_and_completes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    trace = atlas_search.InvestigationTrace(
        "WI-DIAGNOSTIC",
        "openai:test-model",
        tmp_path / "traces",
    )
    tool_rounds = atlas_search.MAX_INVESTIGATION_STEPS + 3
    responses = [
        _response({
            "id": f"resp_{round_number}",
            "output": [{
                "type": "function_call",
                "name": atlas_search.SEARCH_TOOL_NAME,
                "call_id": f"call_{round_number}",
                "arguments": json.dumps({"query": f"Runde {round_number}"}),
            }],
        })
        for round_number in range(1, tool_rounds + 1)
    ]
    responses.append(_response({
        "id": "terminal",
        "output": [{
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": "Freiwilliger fachlicher Abschluss",
            }],
        }],
    }))
    timeouts = []

    def fake_urlopen(request, timeout):
        timeouts.append(timeout)
        return responses.pop(0)

    with patch.object(openai_work_step, "urlopen", fake_urlopen):
        text = openai_work_step._request_model(
            "key",
            "model",
            "context",
            trace,
            unbounded_diagnostic=True,
        )

    assert text == "Freiwilliger fachlicher Abschluss"
    assert len(timeouts) == tool_rounds + 1
    assert all(
        timeout
        == openai_work_step.UNBOUNDED_DIAGNOSTIC_REQUEST_TIMEOUT_SECONDS
        for timeout in timeouts
    )
    entries = [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]
    tool_entries = [entry for entry in entries if "tool" in entry]
    assert len(tool_entries) == tool_rounds
    assert [entry["round"] for entry in tool_entries] == list(
        range(1, tool_rounds + 1)
    )
    assert not any(
        entry.get("event") == "completion_phase_started"
        for entry in entries
    )


def test_openai_generate_does_not_publish_on_safety_abort(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        openai_work_step,
        "_read_work_item",
        lambda _id: {"id": "WI-0001", "intent": "Test", "context_refs": []},
    )
    monkeypatch.setattr(openai_work_step, "list_for_work_item", lambda _id: [])

    def raise_abort(*_args):
        raise RuntimeError("Untersuchung technisch abgebrochen: Sicherheitsgrenze ...")

    monkeypatch.setattr(openai_work_step, "_request_model", raise_abort)

    published = {"called": False}

    def fail_if_published(**_kwargs):
        published["called"] = True
        raise AssertionError("publish darf beim Sicherheitsabbruch nicht aufgerufen werden")

    monkeypatch.setattr(openai_work_step, "publish", fail_if_published)

    assert openai_work_step.generate("WI-0001") == 1
    assert published["called"] is False


def test_openai_unbounded_diagnostic_publishes_after_terminal_answer(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv(openai_work_step.UNBOUNDED_DIAGNOSTIC_ENV, "1")
    monkeypatch.setattr(
        openai_work_step,
        "_read_work_item",
        lambda _id: {"id": "WI-0001", "intent": "Test", "context_refs": []},
    )
    monkeypatch.setattr(openai_work_step, "list_for_work_item", lambda _id: [])
    monkeypatch.setattr(
        openai_work_step,
        "_build_context",
        lambda *_args, **_kwargs: "context",
    )
    request_arguments = {}

    def terminal_answer(*args):
        request_arguments["unbounded_diagnostic"] = args[4]
        return "Freiwilliger fachlicher Abschluss"

    monkeypatch.setattr(openai_work_step, "_request_model", terminal_answer)
    published = {}

    def record_publish(**kwargs):
        published.update(kwargs)
        return type(
            "Result",
            (),
            {"success": True, "id": "WS-TEST", "path": "work_step.yaml"},
        )()

    monkeypatch.setattr(openai_work_step, "publish", record_publish)

    assert openai_work_step.generate("WI-0001") == 0
    assert request_arguments["unbounded_diagnostic"] is True
    assert published["participant_id"] == "openai:test-model"
    assert published["content"] == "Freiwilliger fachlicher Abschluss"


# ---------------------------------------------------------------------------
# Anthropic (Messages API)
# ---------------------------------------------------------------------------

def test_anthropic_investigation_completes_after_one_read_round(tmp_path, monkeypatch):
    (tmp_path / "THE VAULT" / "WARP").mkdir(parents=True)
    (tmp_path / "THE VAULT" / "WARP" / "WARP-TEST.md").write_text(
        "Historieninhalt", encoding="utf-8"
    )
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)

    first = _response({
        "content": [{
            "type": "tool_use",
            "id": "tool_1",
            "name": atlas_search.READ_TOOL_NAME,
            "input": {"path": "THE VAULT/WARP/WARP-TEST.md"},
        }],
        "stop_reason": "tool_use",
    })
    second = _response({
        "content": [{"type": "text", "text": "Fertige Antwort"}],
        "stop_reason": "end_turn",
    })
    responses = [first, second]

    def fake_urlopen(request, timeout):
        return responses.pop(0)

    with patch.object(anthropic_work_step, "urlopen", fake_urlopen):
        text = anthropic_work_step._request_model("key", "model", "context")

    assert text.startswith("Fertige Antwort")
    assert "THE VAULT/WARP/WARP-TEST.md" in text
    assert "warp_historie" in text


def test_anthropic_investigation_aborts_at_safety_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    call_count = {"n": 0}

    def fake_urlopen(request, timeout):
        call_count["n"] += 1
        return _response({
            "content": [{
                "type": "tool_use",
                "id": f"tool_{call_count['n']}",
                "name": atlas_search.SEARCH_TOOL_NAME,
                "input": {"query": "irrelevant"},
            }],
            "stop_reason": "tool_use",
        })

    with patch.object(anthropic_work_step, "urlopen", fake_urlopen):
        try:
            anthropic_work_step._request_model("key", "model", "context")
            assert False, "haette RuntimeError ausloesen muessen"
        except RuntimeError as error:
            assert "Sicherheitsgrenze" in str(error)

    assert call_count["n"] == atlas_search.MAX_INVESTIGATION_STEPS + 1


# ---------------------------------------------------------------------------
# Gemini (generateContent)
# ---------------------------------------------------------------------------

def test_gemini_investigation_completes_after_one_search_round(tmp_path, monkeypatch):
    (tmp_path / "THE LIBRARY").mkdir(parents=True)
    (tmp_path / "THE LIBRARY" / "Constitution.md").write_text(
        "Enthaelt Verfassungsbegriff", encoding="utf-8"
    )
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)

    first = _response({
        "candidates": [{
            "content": {"parts": [{
                "functionCall": {
                    "name": atlas_search.READ_TOOL_NAME,
                    "args": {"path": "THE LIBRARY/Constitution.md"},
                },
            }]},
            "finishReason": "STOP",
        }],
    })
    second = _response({
        "candidates": [{
            "content": {"parts": [{"text": "Gemini-Abschlussantwort"}]},
            "finishReason": "STOP",
        }],
    })
    responses = [first, second]

    def fake_urlopen(request, timeout):
        return responses.pop(0)

    with patch.object(gemini_work_step, "urlopen", fake_urlopen):
        text = gemini_work_step._request_model("key", "model", "context")

    assert text.startswith("Gemini-Abschlussantwort")
    assert "THE LIBRARY/Constitution.md" in text
    assert "kanonisches_wissen" in text


def test_gemini_investigation_aborts_at_safety_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    call_count = {"n": 0}

    def fake_urlopen(request, timeout):
        call_count["n"] += 1
        return _response({
            "candidates": [{
                "content": {"parts": [{
                    "functionCall": {
                        "name": atlas_search.SEARCH_TOOL_NAME,
                        "args": {"query": "irrelevant"},
                    },
                }]},
                "finishReason": "STOP",
            }],
        })

    with patch.object(gemini_work_step, "urlopen", fake_urlopen):
        try:
            gemini_work_step._request_model("key", "model", "context")
            assert False, "haette RuntimeError ausloesen muessen"
        except RuntimeError as error:
            assert "Sicherheitsgrenze" in str(error)

    assert call_count["n"] == atlas_search.MAX_INVESTIGATION_STEPS + 1


def test_read_tool_error_does_not_count_as_used_source(tmp_path, monkeypatch):
    """Ein fehlgeschlagener read-Aufruf (Quelle ausserhalb des
    Wissensraums) darf nicht als verwendete Grundlage erscheinen."""
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)

    first = _response({
        "id": "resp_1",
        "output": [{
            "type": "function_call",
            "name": atlas_search.READ_TOOL_NAME,
            "call_id": "call_1",
            "arguments": json.dumps({"path": "nicht/vorhanden.md"}),
        }],
    })
    second = _response({
        "id": "resp_2",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": "Antwort ohne Quelle"}],
        }],
    })
    responses = [first, second]

    def fake_urlopen(request, timeout):
        return responses.pop(0)

    with patch.object(openai_work_step, "urlopen", fake_urlopen):
        text = openai_work_step._request_model("key", "model", "context")

    assert text == "Antwort ohne Quelle"
    assert "Technisch nachgewiesen" not in text


def test_trace_records_read_error_without_file_content(tmp_path):
    trace = atlas_search.InvestigationTrace(
        "WI-TEST",
        "gemini:test-model",
        tmp_path / "traces",
    )
    result = {
        "error": "Quelle nicht gefunden: nicht/vorhanden.md",
    }

    trace.record(
        3,
        atlas_search.READ_TOOL_NAME,
        {"path": "nicht/vorhanden.md"},
        result,
    )

    entry = json.loads(trace.path.read_text(encoding="utf-8"))
    assert entry["work_item_id"] == "WI-TEST"
    assert entry["participant"] == "gemini:test-model"
    assert entry["round"] == 3
    assert entry["tool"] == atlas_search.READ_TOOL_NAME
    assert entry["path"] == "nicht/vorhanden.md"
    assert entry["success"] is False
    assert entry["error"] == result["error"]
    assert "content" not in entry


# ---------------------------------------------------------------------------
# Providerneutrale Mehrfachaufrufe und Abschlussphase
# ---------------------------------------------------------------------------

PROVIDERS = ("openai", "anthropic", "gemini")


def _provider_module(provider):
    return {
        "openai": openai_work_step,
        "anthropic": anthropic_work_step,
        "gemini": gemini_work_step,
    }[provider]


def _provider_tool_response(provider, number, paths):
    if provider == "openai":
        return {
            "id": f"resp_{number}",
            "output": [
                {
                    "type": "function_call",
                    "name": atlas_search.READ_TOOL_NAME,
                    "call_id": f"call_{number}_{index}",
                    "arguments": json.dumps({"path": path}),
                }
                for index, path in enumerate(paths)
            ],
        }
    if provider == "anthropic":
        return {
            "content": [
                {
                    "type": "tool_use",
                    "id": f"tool_{number}_{index}",
                    "name": atlas_search.READ_TOOL_NAME,
                    "input": {"path": path},
                }
                for index, path in enumerate(paths)
            ],
            "stop_reason": "tool_use",
        }
    return {
        "candidates": [{
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": atlas_search.READ_TOOL_NAME,
                            "args": {"path": path},
                        }
                    }
                    for path in paths
                ]
            },
            "finishReason": "STOP",
        }]
    }


def _provider_terminal_response(provider, text="Fachlicher Abschluss"):
    if provider == "openai":
        return {
            "id": "terminal",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }],
        }
    if provider == "anthropic":
        return {
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
        }
    return {
        "candidates": [{
            "content": {"parts": [{"text": text}]},
            "finishReason": "STOP",
        }]
    }


def _install_provider_responses(monkeypatch, provider, responses, payloads):
    module = _provider_module(provider)
    call_name = {
        "openai": "_call_responses_api",
        "anthropic": "_call_messages_api",
        "gemini": "_call_generate_content",
    }[provider]
    remaining = list(responses)

    def fake_call(*args, **_kwargs):
        payloads.append(json.loads(json.dumps(args[-1])))
        return remaining.pop(0)

    monkeypatch.setattr(module, call_name, fake_call)


def _request_provider(provider, trace=None):
    return _provider_module(provider)._request_model(
        "key", "model", "context", trace
    )


def _last_tool_result_count(provider, payload):
    if provider == "openai":
        return len([
            item for item in payload["input"]
            if item.get("type") == "function_call_output"
        ])
    if provider == "anthropic":
        return len([
            item for item in payload["messages"][-1]["content"]
            if item.get("type") == "tool_result"
        ])
    return len([
        item for item in payload["contents"][-1]["parts"]
        if "functionResponse" in item
    ])


@pytest.mark.parametrize("provider", PROVIDERS)
def test_multiple_tool_calls_share_one_round_and_return_all_results(
    provider, tmp_path, monkeypatch
):
    source_dir = tmp_path / "THE NORTH STAR"
    source_dir.mkdir(parents=True)
    paths = ["THE NORTH STAR/A.md", "THE NORTH STAR/B.md"]
    for path in paths:
        (tmp_path / path).write_text(f"Inhalt {path}", encoding="utf-8")
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    trace = atlas_search.InvestigationTrace(
        "WI-MULTI", f"{provider}:model", tmp_path / "traces"
    )
    payloads = []
    _install_provider_responses(
        monkeypatch,
        provider,
        [
            _provider_tool_response(provider, 1, paths),
            _provider_terminal_response(provider),
        ],
        payloads,
    )

    text = _request_provider(provider, trace)

    assert text.startswith("Fachlicher Abschluss")
    assert all(path in text for path in paths)
    assert len(payloads) == 2
    assert _last_tool_result_count(provider, payloads[1]) == 2
    entries = [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(entries) == 2
    assert [entry["round"] for entry in entries] == [1, 1]
    assert [entry["path"] for entry in entries] == paths


@pytest.mark.parametrize("provider", PROVIDERS)
def test_terminal_answer_before_tool_budget_is_exhausted(
    provider, tmp_path, monkeypatch
):
    path = "THE NORTH STAR/A.md"
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    (tmp_path / path).write_text("Inhalt", encoding="utf-8")
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    payloads = []
    responses = [
        _provider_tool_response(provider, number, [path])
        for number in range(1, 8)
    ]
    responses.append(_provider_terminal_response(provider))
    _install_provider_responses(monkeypatch, provider, responses, payloads)

    text = _request_provider(provider)

    assert text.startswith("Fachlicher Abschluss")
    assert len(payloads) == 8


@pytest.mark.parametrize("provider", PROVIDERS)
def test_final_budget_round_results_reach_completion_phase(
    provider, tmp_path, monkeypatch
):
    path = "THE NORTH STAR/A.md"
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    (tmp_path / path).write_text("Inhalt letzte Budgetrunde", encoding="utf-8")
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    trace = atlas_search.InvestigationTrace(
        "WI-COMPLETE", f"{provider}:model", tmp_path / "traces"
    )
    payloads = []
    responses = [
        _provider_tool_response(provider, number, [path])
        for number in range(1, atlas_search.MAX_INVESTIGATION_STEPS + 1)
    ]
    responses.append(_provider_terminal_response(provider))
    _install_provider_responses(monkeypatch, provider, responses, payloads)

    text = _request_provider(provider, trace)

    assert text.startswith("Fachlicher Abschluss")
    assert len(payloads) == atlas_search.MAX_INVESTIGATION_STEPS + 1
    assert _last_tool_result_count(provider, payloads[-1]) == 1
    entries = [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]
    assert entries[-2]["event"] == "completion_phase_started"
    assert entries[-1]["event"] == "completion_phase_completed"
    assert entries[-1]["outcome"] == "terminal"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_completion_phase_rejects_tools_without_executing_them(
    provider, tmp_path, monkeypatch
):
    path = "THE NORTH STAR/A.md"
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    (tmp_path / path).write_text("Inhalt", encoding="utf-8")
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    trace = atlas_search.InvestigationTrace(
        "WI-REJECT", f"{provider}:model", tmp_path / "traces"
    )
    payloads = []
    responses = [
        _provider_tool_response(provider, number, [path])
        for number in range(1, atlas_search.MAX_INVESTIGATION_STEPS + 2)
    ]
    _install_provider_responses(monkeypatch, provider, responses, payloads)
    original_execute_tool = atlas_search.execute_tool
    executed = []

    def recording_execute_tool(name, arguments, repo_root=None):
        executed.append((name, arguments))
        return original_execute_tool(name, arguments, repo_root)

    monkeypatch.setattr(atlas_search, "execute_tool", recording_execute_tool)

    with pytest.raises(RuntimeError, match="Abschlussphase weitere Werkzeugarbeit"):
        _request_provider(provider, trace)

    assert len(payloads) == atlas_search.MAX_INVESTIGATION_STEPS + 1
    assert len(executed) == atlas_search.MAX_INVESTIGATION_STEPS
    entries = [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]
    assert entries[-2]["event"] == "completion_phase_started"
    assert entries[-1]["event"] == "completion_phase_tool_request_rejected"
    assert entries[-1]["requested_tool_count"] == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_multiple_final_budget_round_results_reach_completion_together(
    provider, tmp_path, monkeypatch
):
    paths = ["THE NORTH STAR/A.md", "THE NORTH STAR/B.md"]
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    for path in paths:
        (tmp_path / path).write_text(f"Inhalt {path}", encoding="utf-8")
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    payloads = []
    responses = [
        _provider_tool_response(provider, number, [paths[0]])
        for number in range(1, atlas_search.MAX_INVESTIGATION_STEPS)
    ]
    responses.extend([
        _provider_tool_response(
            provider,
            atlas_search.MAX_INVESTIGATION_STEPS,
            paths,
        ),
        _provider_terminal_response(provider),
    ])
    _install_provider_responses(monkeypatch, provider, responses, payloads)

    text = _request_provider(provider)

    assert text.startswith("Fachlicher Abschluss")
    assert len(payloads) == atlas_search.MAX_INVESTIGATION_STEPS + 1
    assert _last_tool_result_count(provider, payloads[-1]) == 2


def test_tool_budget_is_current_pragmatic_operating_value():
    assert atlas_search.MAX_INVESTIGATION_STEPS == 20


def test_all_provider_instructions_allow_only_independent_bundling():
    for instructions in (
        openai_work_step._INSTRUCTIONS,
        anthropic_work_step.MODEL_INSTRUCTIONS,
    ):
        assert "voneinander unabhaengig" in instructions
        assert "in derselben Antwort anfordern" in instructions
        assert "weiterhin seriell" in instructions
        assert "keine Quellen nur vorsorglich" in instructions
    assert gemini_work_step.MODEL_INSTRUCTIONS == anthropic_work_step.MODEL_INSTRUCTIONS


def test_openai_instruction_requires_continuous_research_sufficiency_check():
    instructions = openai_work_step._INSTRUCTIONS

    assert "nach jedem wesentlichen Erkenntnisgewinn" in instructions
    assert "vorhandene Evidenz bereits ausreicht" in instructions
    assert "welche Teile des Auftrags bereits" in instructions
    assert "relevante Informationsluecke schliesst" in instructions
    assert "fordere keine weiteren Werkzeuge an" in instructions
    assert "synthetisiere das Ergebnis" in instructions
    assert "vollstaendige Sichtung des Atlas-Wissensraums ist nicht erforderlich" in (
        instructions
    )
    assert "Informationsluecke benennen" in instructions
    assert "notwendige Recherche" in instructions
    assert "Primaerquellen setzt du fort" in instructions


@pytest.mark.parametrize("provider", PROVIDERS)
def test_completion_phase_abort_does_not_publish_work_step(
    provider, monkeypatch
):
    module = _provider_module(provider)
    env_prefix = {
        "openai": "OPENAI",
        "anthropic": "ANTHROPIC",
        "gemini": "GEMINI",
    }[provider]
    monkeypatch.setenv(f"{env_prefix}_API_KEY", "test-key")
    monkeypatch.setenv(f"{env_prefix}_MODEL", "test-model")
    monkeypatch.setattr(
        module,
        "_read_work_item",
        lambda _id: {"id": "WI-0001", "intent": "Test", "context_refs": []},
    )
    monkeypatch.setattr(module, "list_for_work_item", lambda _id: [])
    monkeypatch.setattr(module, "_build_context", lambda *_args, **_kwargs: "context")
    monkeypatch.setattr(
        module,
        "_request_model",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError(
                "Untersuchung technisch abgebrochen: Sicherheitsgrenze; "
                "Abschlussphase weitere Werkzeugarbeit"
            )
        ),
    )
    published = {"called": False}

    def fail_if_published(**_kwargs):
        published["called"] = True
        raise AssertionError("publish darf beim Sicherheitsabbruch nicht laufen")

    monkeypatch.setattr(module, "publish", fail_if_published)

    assert module.generate("WI-0001") == 1
    assert published["called"] is False


@pytest.mark.parametrize("provider", PROVIDERS)
def test_generate_content_returns_answer_without_publishing(
    provider, monkeypatch
):
    module = _provider_module(provider)
    env_prefix = {
        "openai": "OPENAI",
        "anthropic": "ANTHROPIC",
        "gemini": "GEMINI",
    }[provider]
    monkeypatch.setenv(f"{env_prefix}_API_KEY", "test-key")
    monkeypatch.setenv(f"{env_prefix}_MODEL", "test-model")
    monkeypatch.setattr(
        module,
        "_read_work_item",
        lambda _id: {"id": "WI-0001", "intent": "Test", "context_refs": []},
    )
    monkeypatch.setattr(module, "list_for_work_item", lambda _id: [])
    monkeypatch.setattr(module, "_build_context", lambda *_args, **_kwargs: "context")
    monkeypatch.setattr(
        module,
        "_request_model",
        lambda *_args: "Fachliches Ergebnis",
    )
    published = {"called": False}

    def fail_if_published(**_kwargs):
        published["called"] = True
        raise AssertionError("generate_content darf nicht publizieren")

    monkeypatch.setattr(module, "publish", fail_if_published)

    participant_id, content = module.generate_content("WI-0001")

    assert participant_id == f"{provider}:test-model"
    assert content == "Fachliches Ergebnis"
    assert published["called"] is False


@pytest.mark.parametrize("provider", PROVIDERS)
def test_existing_generate_still_publishes_immediately(provider, monkeypatch):
    module = _provider_module(provider)
    monkeypatch.setattr(
        module,
        "generate_content",
        lambda *_args, **_kwargs: (
            f"{provider}:test-model",
            "Fachliches Ergebnis",
        ),
    )
    published = []

    def publish(**kwargs):
        published.append(kwargs)
        return work_step.WorkStepResult(
            success=True,
            id="WS-9999",
            path="THE VAULT/work_steps/WS-9999.yaml",
        )

    monkeypatch.setattr(module, "publish", publish)

    assert module.generate("WI-0001") == 0
    assert published == [{
        "work_item_id": "WI-0001",
        "participant_id": f"{provider}:test-model",
        "content": "Fachliches Ergebnis",
    }]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_generate_content_propagates_technical_failure(provider, monkeypatch):
    module = _provider_module(provider)
    env_prefix = {
        "openai": "OPENAI",
        "anthropic": "ANTHROPIC",
        "gemini": "GEMINI",
    }[provider]
    monkeypatch.setenv(f"{env_prefix}_API_KEY", "test-key")
    monkeypatch.setenv(f"{env_prefix}_MODEL", "test-model")
    monkeypatch.setattr(
        module,
        "_read_work_item",
        lambda _id: {"id": "WI-0001", "intent": "Test", "context_refs": []},
    )
    monkeypatch.setattr(module, "list_for_work_item", lambda _id: [])
    monkeypatch.setattr(module, "_build_context", lambda *_args, **_kwargs: "context")
    monkeypatch.setattr(
        module,
        "_request_model",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("Providerfehler")),
    )

    with pytest.raises(RuntimeError, match="Providerfehler"):
        module.generate_content("WI-0001")
