"""
Erzeugt genau einen Gemini-WorkStep fuer ein bestehendes Work Item.

Verwendung:
    python gemini_work_step.py generate --work-item WI-XXXX

Erforderliche Umgebungsvariablen:
    GEMINI_API_KEY
    GEMINI_MODEL
"""

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import atlas_search
from anthropic_work_step import (
    COMPLETION_PHASE_INSTRUCTION,
    COMPLETION_PHASE_TOOL_REQUEST_ERROR,
    MODEL_INSTRUCTIONS,
)
from openai_work_step import _build_context, _read_work_item
from work_step import list_for_work_item, publish


GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
REQUEST_TIMEOUT_SECONDS = 100


def _extract_text(response: dict) -> str:
    candidates = response.get("candidates", [])
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [
        part["text"]
        for part in parts
        if part.get("text") and not part.get("thought", False)
    ]
    return "\n".join(texts).strip()


def _tool_definitions() -> list[dict]:
    return [{
        "functionDeclarations": [
            {
                "name": atlas_search.SEARCH_TOOL_NAME,
                "description": atlas_search.SEARCH_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": atlas_search.READ_TOOL_NAME,
                "description": atlas_search.READ_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        ],
    }]


def _call_generate_content(
    api_key: str,
    model: str,
    payload: dict,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    trace: atlas_search.InvestigationTrace | None = None,
    request_number: int = 1,
    phase: str = "regular",
) -> dict:
    url = GENERATE_CONTENT_URL.format(model=quote(model, safe=""))
    request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=request_data,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response_opened = False
    started = time.monotonic()
    if trace:
        trace.record_provider_request(
            "provider_request_started",
            provider="gemini",
            request_number=request_number,
            phase=phase,
            timeout_seconds=timeout_seconds,
            payload_bytes=len(request_data),
            response_opened=False,
        )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_opened = True
            result = json.load(response)
        if trace:
            trace.record_provider_request(
                "provider_request_completed",
                provider="gemini",
                request_number=request_number,
                phase=phase,
                timeout_seconds=timeout_seconds,
                payload_bytes=len(request_data),
                response_opened=response_opened,
                success=True,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
        return result
    except HTTPError as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"Gemini API-Fehler: HTTP {error.code} {error.reason}"
        ) from error
    except URLError as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"Gemini Netzwerkfehler: {error.reason}"
        ) from error
    except (TimeoutError, OSError) as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"Gemini Netzwerkfehler: {error}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            "Gemini API-Fehler: Antwort ist kein gueltiges JSON"
        ) from error


def _record_request_failure(
    trace: atlas_search.InvestigationTrace | None,
    request_number: int,
    phase: str,
    timeout_seconds: int,
    request_data: bytes,
    response_opened: bool,
    started: float,
    error: Exception,
) -> None:
    if trace:
        trace.record_provider_request(
            "provider_request_failed",
            provider="gemini",
            request_number=request_number,
            phase=phase,
            timeout_seconds=timeout_seconds,
            payload_bytes=len(request_data),
            response_opened=response_opened,
            success=False,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            exception_type=type(error).__name__,
            error=str(error),
        )


def _request_model(
    api_key: str,
    model: str,
    context: str,
    trace: atlas_search.InvestigationTrace | None = None,
) -> str:
    # Untersuchungszyklus V1: Mehrschrittprozess ueber die Gemini
    # generateContent-API (functionCall/functionResponse-Parts, volle
    # contents-Historie je Runde). Eine Runde ohne functionCall-Part
    # beendet die Untersuchung (Modell entscheidet fachlich selbst).
    # atlas_search.MAX_INVESTIGATION_STEPS ist eine rein technische
    # Sicherheitsgrenze - siehe Auftrag "SICHERHEITSGRENZE".
    contents: list[dict] = [{"role": "user", "parts": [{"text": context}]}]
    used_sources: list[dict] = []
    seen_source_paths: set[str] = set()
    request_number = 0

    for _step in range(atlas_search.MAX_INVESTIGATION_STEPS):
        payload = {
            "system_instruction": {"parts": [{"text": MODEL_INSTRUCTIONS}]},
            "contents": contents,
            "tools": _tool_definitions(),
            "generationConfig": {"maxOutputTokens": 8192},
        }
        request_number += 1
        result = _call_generate_content(
            api_key,
            model,
            payload,
            trace=trace,
            request_number=request_number,
            phase="regular",
        )

        candidates = result.get("candidates", [])
        if not candidates:
            block_reason = result.get("promptFeedback", {}).get("blockReason")
            if block_reason:
                raise RuntimeError(
                    f"Gemini API-Fehler: Anfrage wurde blockiert ({block_reason})"
                )
            raise RuntimeError("Gemini API-Fehler: leere Modellantwort")

        finish_reason = candidates[0].get("finishReason")
        if finish_reason == "MAX_TOKENS":
            raise RuntimeError(
                "Gemini API-Fehler: Antwort wurde am Tokenlimit abgeschnitten"
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        function_calls = [part["functionCall"] for part in parts if "functionCall" in part]

        if not function_calls:
            if finish_reason and finish_reason != "STOP":
                raise RuntimeError(
                    f"Gemini API-Fehler: Modellantwort beendet ({finish_reason})"
                )
            text = _extract_text(result)
            if not text:
                raise RuntimeError("Gemini API-Fehler: leere Modellantwort")
            return text + atlas_search.format_used_sources(used_sources)

        contents.append({"role": "model", "parts": parts})

        response_parts = []
        for call in function_calls:
            name = call.get("name")
            args = call.get("args") or {}
            tool_result = atlas_search.execute_tool(name, args)
            if trace:
                trace.record(_step + 1, name, args, tool_result)
            if name == atlas_search.READ_TOOL_NAME and "error" not in tool_result:
                if tool_result["path"] not in seen_source_paths:
                    seen_source_paths.add(tool_result["path"])
                    used_sources.append(
                        {"path": tool_result["path"], "kind": tool_result["kind"]}
                    )
            response_parts.append({
                "functionResponse": {"name": name, "response": tool_result},
            })
        contents.append({"role": "function", "parts": response_parts})

    if trace:
        trace.record_event(
            "completion_phase_started",
            regular_tool_rounds=atlas_search.MAX_INVESTIGATION_STEPS,
        )
    payload = {
        "system_instruction": {
            "parts": [{"text": MODEL_INSTRUCTIONS + COMPLETION_PHASE_INSTRUCTION}]
        },
        "contents": contents,
        "tools": _tool_definitions(),
        "generationConfig": {"maxOutputTokens": 8192},
    }
    request_number += 1
    result = _call_generate_content(
        api_key,
        model,
        payload,
        trace=trace,
        request_number=request_number,
        phase="completion",
    )
    candidates = result.get("candidates", [])
    if not candidates:
        block_reason = result.get("promptFeedback", {}).get("blockReason")
        if block_reason:
            raise RuntimeError(
                f"Gemini API-Fehler: Anfrage wurde blockiert ({block_reason})"
            )
        raise RuntimeError("Gemini API-Fehler: leere Modellantwort")

    finish_reason = candidates[0].get("finishReason")
    if finish_reason == "MAX_TOKENS":
        raise RuntimeError(
            "Gemini API-Fehler: Antwort wurde am Tokenlimit abgeschnitten"
        )
    parts = candidates[0].get("content", {}).get("parts", [])
    function_calls = [
        part["functionCall"] for part in parts if "functionCall" in part
    ]
    if function_calls:
        if trace:
            trace.record_event(
                "completion_phase_tool_request_rejected",
                requested_tool_count=len(function_calls),
                requested_tools=[call.get("name") for call in function_calls],
            )
        raise RuntimeError(COMPLETION_PHASE_TOOL_REQUEST_ERROR)
    if finish_reason and finish_reason != "STOP":
        raise RuntimeError(
            f"Gemini API-Fehler: Modellantwort beendet ({finish_reason})"
        )
    text = _extract_text(result)
    if not text:
        raise RuntimeError("Gemini API-Fehler: leere Modellantwort")
    if trace:
        trace.record_event("completion_phase_completed", outcome="terminal")
    return text + atlas_search.format_used_sources(used_sources)


def generate_content(
    work_item_id: str,
    work_steps_snapshot: list[dict] | None = None,
    additional_task: str | None = None,
) -> tuple[str, str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY fehlt")

    model = os.environ.get("GEMINI_MODEL", "").strip()
    if not model:
        raise ValueError("GEMINI_MODEL fehlt")

    work_item = _read_work_item(work_item_id)
    work_steps = (
        list_for_work_item(work_item_id)
        if work_steps_snapshot is None
        else work_steps_snapshot
    )
    context = _build_context(
        work_item,
        work_steps,
        additional_task=additional_task,
    )
    participant_id = f"gemini:{model}"
    trace = atlas_search.InvestigationTrace(work_item_id, participant_id)
    answer = _request_model(api_key, model, context, trace)
    return participant_id, answer


def generate(
    work_item_id: str,
    work_steps_snapshot: list[dict] | None = None,
    additional_task: str | None = None,
) -> int:
    try:
        participant_id, answer = generate_content(
            work_item_id,
            work_steps_snapshot=work_steps_snapshot,
            additional_task=additional_task,
        )
        result = publish(
            work_item_id=work_item_id,
            participant_id=participant_id,
            content=answer,
        )
    except (ValueError, RuntimeError) as error:
        print(f"FEHLER: {error}", file=sys.stderr)
        return 1

    if not result.success:
        print(f"FEHLER: {result.error}", file=sys.stderr)
        return 1

    print(f"OK  {result.id}  {result.path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Erzeugt einen Gemini-WorkStep."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--work-item", required=True)
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_args()
    if args.command == "generate":
        sys.exit(generate(args.work_item))


if __name__ == "__main__":
    main()
