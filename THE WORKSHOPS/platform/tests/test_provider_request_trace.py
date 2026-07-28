import io
import json
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atlas_search  # noqa: E402
import anthropic_work_step  # noqa: E402
import gemini_work_step  # noqa: E402
import openai_work_step  # noqa: E402


PROVIDERS = ("openai", "anthropic", "gemini")


def _module(provider):
    return {
        "openai": openai_work_step,
        "anthropic": anthropic_work_step,
        "gemini": gemini_work_step,
    }[provider]


def _call_http(
    provider,
    payload,
    trace,
    *,
    request_number=4,
    phase="regular",
    timeout_seconds=17,
):
    module = _module(provider)
    kwargs = {
        "timeout_seconds": timeout_seconds,
        "trace": trace,
        "request_number": request_number,
        "phase": phase,
    }
    if provider == "openai":
        return module._call_responses_api("secret-key", payload, **kwargs)
    if provider == "anthropic":
        return module._call_messages_api("secret-key", payload, **kwargs)
    return module._call_generate_content(
        "secret-key", "test-model", payload, **kwargs
    )


def _events(trace):
    return [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]


def test_provider_request_timeout_configuration_is_uniform():
    assert openai_work_step.REGULAR_REQUEST_TIMEOUT_SECONDS == 100
    assert openai_work_step.COMPLETION_REQUEST_TIMEOUT_SECONDS == 100
    assert (
        openai_work_step.UNBOUNDED_DIAGNOSTIC_REQUEST_TIMEOUT_SECONDS
        == 100
    )
    assert anthropic_work_step.REQUEST_TIMEOUT_SECONDS == 100
    assert gemini_work_step.REQUEST_TIMEOUT_SECONDS == 100


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("phase", ("regular", "completion"))
def test_default_provider_request_timeout_is_reported_in_trace(
    provider, phase, tmp_path
):
    module = _module(provider)
    trace = atlas_search.InvestigationTrace(
        "WI-TIMEOUT", f"{provider}:test-model", tmp_path / "traces"
    )
    kwargs = {
        "trace": trace,
        "request_number": 1,
        "phase": phase,
    }
    with patch.object(module, "urlopen", return_value=io.BytesIO(b"{}")):
        if provider == "openai":
            result = module._call_responses_api("secret-key", {}, **kwargs)
        elif provider == "anthropic":
            result = module._call_messages_api("secret-key", {}, **kwargs)
        else:
            result = module._call_generate_content(
                "secret-key", "test-model", {}, **kwargs
            )

    assert result == {}
    started, completed = _events(trace)
    assert started["timeout_seconds"] == 100
    assert completed["timeout_seconds"] == 100
    assert started["phase"] == phase
    assert completed["phase"] == phase


@pytest.mark.parametrize("provider", PROVIDERS)
def test_successful_provider_request_records_common_metadata(
    provider, tmp_path
):
    trace = atlas_search.InvestigationTrace(
        "WI-REQUEST", f"{provider}:test-model", tmp_path / "traces"
    )
    payload = {"private_marker": "REQUEST-CONTENT-MUST-NOT-BE-TRACED"}
    response = io.BytesIO(b"{}")

    with patch.object(_module(provider), "urlopen", return_value=response):
        assert _call_http(provider, payload, trace) == {}

    started, completed = _events(trace)
    expected_bytes = len(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    assert started["event"] == "provider_request_started"
    assert completed["event"] == "provider_request_completed"
    for entry in (started, completed):
        assert entry["provider"] == provider
        assert entry["request_number"] == 4
        assert entry["phase"] == "regular"
        assert entry["timeout_seconds"] == 17
        assert entry["payload_bytes"] == expected_bytes
        assert "REQUEST-CONTENT-MUST-NOT-BE-TRACED" not in str(entry)
        assert "secret-key" not in str(entry)
        assert "Authorization" not in str(entry)
    assert started["response_opened"] is False
    assert completed["response_opened"] is True
    assert completed["success"] is True
    assert completed["duration_ms"] >= 0


class _FailingResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args, **_kwargs):
        raise TimeoutError("simulated read timeout")


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(
    ("response_opened", "urlopen_effect"),
    [
        (False, TimeoutError("simulated connect timeout")),
        (True, _FailingResponse()),
    ],
)
def test_failed_provider_request_records_exception_and_open_state(
    provider, response_opened, urlopen_effect, tmp_path
):
    trace = atlas_search.InvestigationTrace(
        "WI-FAIL", f"{provider}:test-model", tmp_path / "traces"
    )
    payload = {"private_marker": "DO-NOT-TRACE"}
    patch_kwargs = (
        {"return_value": urlopen_effect}
        if response_opened
        else {"side_effect": urlopen_effect}
    )

    with patch.object(_module(provider), "urlopen", **patch_kwargs):
        with pytest.raises(RuntimeError, match="Netzwerkfehler"):
            _call_http(
                provider,
                payload,
                trace,
                request_number=7,
                phase="completion",
                timeout_seconds=23,
            )

    started, failed = _events(trace)
    assert started["event"] == "provider_request_started"
    assert failed["event"] == "provider_request_failed"
    assert failed["provider"] == provider
    assert failed["request_number"] == 7
    assert failed["phase"] == "completion"
    assert failed["timeout_seconds"] == 23
    assert failed["response_opened"] is response_opened
    assert failed["success"] is False
    assert failed["duration_ms"] >= 0
    assert failed["exception_type"] == "TimeoutError"
    assert "simulated" in failed["error"]
    assert "DO-NOT-TRACE" not in str(failed)


def test_anthropic_http_error_records_only_safe_bounded_diagnostics(tmp_path):
    trace = atlas_search.InvestigationTrace(
        "WI-HTTP", "anthropic:test-model", tmp_path / "traces"
    )
    body = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Invalid request parameter",
            "private_detail": "ATLAS-CONTENT-MUST-NOT-BE-TRACED",
        },
        "request": {"messages": "REQUEST-MUST-NOT-BE-TRACED"},
    }
    http_error = HTTPError(
        anthropic_work_step.MESSAGES_URL,
        400,
        "Bad Request",
        {
            "request-id": "req_safe_123",
            "x-api-key": "HEADER-SECRET-MUST-NOT-BE-TRACED",
        },
        io.BytesIO(json.dumps(body).encode("utf-8")),
    )

    with patch.object(
        anthropic_work_step, "urlopen", side_effect=http_error
    ):
        with pytest.raises(RuntimeError, match="HTTP 400 Bad Request"):
            _call_http(
                "anthropic",
                {"private_marker": "PAYLOAD-MUST-NOT-BE-TRACED"},
                trace,
            )

    _started, failed = _events(trace)
    assert failed["http_status"] == 400
    assert failed["provider_request_id"] == "req_safe_123"
    assert failed["error_body"] == {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Invalid request parameter",
        },
    }
    serialized = json.dumps(failed)
    for secret in (
        "ATLAS-CONTENT-MUST-NOT-BE-TRACED",
        "REQUEST-MUST-NOT-BE-TRACED",
        "HEADER-SECRET-MUST-NOT-BE-TRACED",
        "PAYLOAD-MUST-NOT-BE-TRACED",
        "secret-key",
    ):
        assert secret not in serialized


def test_anthropic_http_error_bounds_body_and_redacts_credentials(tmp_path):
    trace = atlas_search.InvestigationTrace(
        "WI-HTTP-LIMIT", "anthropic:test-model", tmp_path / "traces"
    )
    message = "x-api-key: super-secret " + (
        "x" * anthropic_work_step.MAX_HTTP_ERROR_BODY_BYTES
    )
    body = json.dumps({
        "type": "error",
        "error": {"type": "invalid_request_error", "message": message},
    }).encode("utf-8")
    http_error = HTTPError(
        anthropic_work_step.MESSAGES_URL,
        400,
        "Bad Request",
        {},
        io.BytesIO(body),
    )

    with patch.object(
        anthropic_work_step, "urlopen", side_effect=http_error
    ):
        with pytest.raises(RuntimeError, match="HTTP 400 Bad Request"):
            _call_http("anthropic", {}, trace)

    _started, failed = _events(trace)
    assert failed["http_status"] == 400
    assert failed["error_body_truncated"] is True
    assert "error_body" not in failed
    assert "super-secret" not in json.dumps(failed)


def _tool_response(provider):
    paths = ["THE NORTH STAR/A.md", "THE NORTH STAR/B.md"]
    if provider == "openai":
        return {
            "id": "response-1",
            "output": [
                {
                    "type": "function_call",
                    "name": atlas_search.READ_TOOL_NAME,
                    "call_id": f"call-{index}",
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
                    "id": f"tool-{index}",
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


def _terminal_response(provider):
    if provider == "openai":
        return {
            "id": "terminal",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "Fertig"}],
            }],
        }
    if provider == "anthropic":
        return {
            "content": [{"type": "text", "text": "Fertig"}],
            "stop_reason": "end_turn",
        }
    return {
        "candidates": [{
            "content": {"parts": [{"text": "Fertig"}]},
            "finishReason": "STOP",
        }]
    }


@pytest.mark.parametrize("provider", PROVIDERS)
def test_request_numbers_count_provider_calls_not_tool_calls(
    provider, tmp_path, monkeypatch
):
    (tmp_path / "THE NORTH STAR").mkdir(parents=True)
    for name in ("A.md", "B.md"):
        (tmp_path / "THE NORTH STAR" / name).write_text(
            name, encoding="utf-8"
        )
    monkeypatch.setattr(atlas_search, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(atlas_search, "MAX_INVESTIGATION_STEPS", 1)
    module = _module(provider)
    call_name = {
        "openai": "_call_responses_api",
        "anthropic": "_call_messages_api",
        "gemini": "_call_generate_content",
    }[provider]
    responses = [_tool_response(provider), _terminal_response(provider)]
    calls = []

    def fake_call(*_args, **kwargs):
        calls.append({
            "request_number": kwargs["request_number"],
            "phase": kwargs["phase"],
        })
        return responses.pop(0)

    monkeypatch.setattr(module, call_name, fake_call)

    assert module._request_model("key", "model", "context").startswith("Fertig")
    assert calls == [
        {"request_number": 1, "phase": "regular"},
        {"request_number": 2, "phase": "completion"},
    ]
