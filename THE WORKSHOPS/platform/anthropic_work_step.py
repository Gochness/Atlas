"""
Erzeugt genau einen Anthropic-WorkStep fuer ein bestehendes Work Item.

Verwendung:
    python anthropic_work_step.py generate --work-item WI-XXXX

Erforderliche Umgebungsvariablen:
    ANTHROPIC_API_KEY
    ANTHROPIC_MODEL
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import atlas_search
from openai_work_step import _build_context, _read_work_item
from work_step import list_for_work_item, publish


MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 100
MAX_HTTP_ERROR_BODY_BYTES = 16 * 1024
MAX_HTTP_ERROR_MESSAGE_CHARS = 2000
MAX_PROVIDER_REQUEST_ID_CHARS = 200

MODEL_INSTRUCTIONS = (
    "Erzeuge genau einen hilfreichen, sichtbaren Zwischenstand fuer "
    "das Work Item und stuetze dich ausschliesslich auf Informationen "
    "aus dem uebergebenen Work Item und seinen vorhandenen WorkSteps. "
    "Wenn der Kontext ein Feld additional_task enthaelt, bearbeite diesen "
    "zusaetzlichen Phasenauftrag zusammen mit dem urspruenglichen Auftrag. "
    "Behaupte keine Fakten, Dateien, Technologien, Entscheidungen oder "
    "bisherigen Arbeiten, die nicht in diesem Kontext enthalten sind. "
    "Dir stehen zwei Werkzeuge zur Verfuegung, um den Atlas-internen "
    "Wissensraum selbst zu untersuchen: search_atlas_knowledge "
    "(Stichwortsuche) und read_atlas_source (vollstaendigen Inhalt "
    "einer gefundenen Quelle lesen) - beide ausschliesslich "
    "Atlas-intern, kein Internet, keine sonstigen externen Quellen. "
    "Was du per read_atlas_source tatsaechlich liest, zaehlt "
    "zusaetzlich zum uebergebenen Kontext als zulaessige Grundlage. "
    "Du entscheidest selbst, wonach du suchst, was du liest und wie "
    "oft - niemand waehlt dir Quellen vor, und du darfst mehrfach "
    "suchen und lesen, auch aufbauend auf dem bereits Gelesenen. Du "
    "entscheidest fachlich selbst, wann deine Untersuchung ausreicht. "
    "Fehlt eine fuer die Aufgabe notwendige Information trotz Suche "
    "im zugaenglichen Wissensraum, stelle das in deiner Antwort "
    "ausdruecklich als Informationsluecke fest, statt sie zu "
    "erfinden oder zu uebergehen. "
    "Wenn mehrere bereits bekannte Werkzeugaktionen voneinander "
    "unabhaengig sind, kannst du sie in derselben Antwort anfordern. "
    "Arbeite weiterhin seriell, wenn eine Aktion vom Ergebnis einer "
    "vorherigen Aktion abhaengt; lies keine Quellen nur vorsorglich. "
    "Fruehere WorkSteps sind Beitraege und Aussagen anderer Teilnehmer, "
    "keine automatisch bestaetigten Tatsachen. Behandle ihre Existenz "
    "als Tatsache, ihren Inhalt aber nicht automatisch als wahr. Du "
    "darfst Behauptungen daraus referenzieren, musst sie jedoch "
    "erkennbar dem jeweiligen Teilnehmer zuschreiben. Fehlt im "
    "bereitgestellten Kontext eine unabhaengige Grundlage, behandle die "
    "Behauptung als unbestaetigt. Eine Behauptung wird nicht dadurch "
    "bestaetigt, dass sie in mehreren spaeteren WorkSteps wiederholt "
    "wird. Benenne Widersprueche, fehlende Belege und Unsicherheit "
    "ausdruecklich. Ergaenze keine neuen Fakten oder technischen "
    "Details. Unbestaetigte fruehere Vorschlaege duerfen sichtbar "
    "referenziert und geprueft werden, aber nicht automatisch die "
    "Agenda, naechsten Arbeitsschritte oder notwendigen Klaerungen "
    "bestimmen. Leite naechste Schritte nur aus belegtem Kontext oder "
    "der expliziten aktuellen Aufgabe ab. Wenn dafuer keine "
    "ausreichende Grundlage vorhanden ist, sage klar, dass sich aus "
    "dem vorhandenen Kontext kein belastbarer naechster Schritt "
    "ableiten laesst. Werte keine unbestaetigte Behauptung durch "
    "Umformulierung in eine Aufgabe, offene Frage oder notwendige "
    "Klaerung auf. "
    "Repository-Kontextdateien belegen, was in diesen Dateien steht; "
    "ihr Inhalt ist nicht automatisch sachlich wahr oder aktuell. "
    "Kennzeichne Vermutungen ausdruecklich als Vermutung. Wenn der "
    "Kontext nicht ausreicht, sage das klar, statt Details zu erfinden. "
    "Triff keine neuen Implementierungsentscheidungen, wenn nur ein "
    "Zwischenstand verlangt ist. Nutze ausschliesslich die beiden "
    "bereitgestellten Werkzeuge (search_atlas_knowledge, "
    "read_atlas_source) fuer deine Untersuchung, keine anderen "
    "Befehle oder Werkzeuge. Sobald deine Untersuchung fachlich "
    "abgeschlossen ist, antworte abschliessend mit reinem Text fuer "
    "den Zwischenstand, ohne weiteren Werkzeugaufruf."
)

COMPLETION_PHASE_INSTRUCTION = (
    " Das regulaere Werkzeugbudget ist jetzt ausgeschoepft. Verarbeite "
    "die bereits erhaltenen Werkzeugergebnisse und antworte ausschliesslich "
    "mit dem fachlichen Zwischenstand. Fordere keine weiteren Werkzeuge an."
)

COMPLETION_PHASE_TOOL_REQUEST_ERROR = (
    "Untersuchung technisch abgebrochen: Die Sicherheitsgrenze des "
    "regulaeren Werkzeugbudgets von "
    f"{atlas_search.MAX_INVESTIGATION_STEPS} Werkzeug-Runden war "
    "ausgeschoepft und das Modell hat auch in der Abschlussphase weitere "
    "Werkzeugarbeit angefordert."
)


def _extract_text(response: dict) -> str:
    texts = [
        item["text"]
        for item in response.get("content", [])
        if item.get("type") == "text" and item.get("text")
    ]
    return "\n".join(texts).strip()


def _tool_definitions() -> list[dict]:
    return [
        {
            "name": atlas_search.SEARCH_TOOL_NAME,
            "description": atlas_search.SEARCH_TOOL_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": atlas_search.READ_TOOL_NAME,
            "description": atlas_search.READ_TOOL_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    ]


def _call_messages_api(
    api_key: str,
    payload: dict,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    trace: atlas_search.InvestigationTrace | None = None,
    request_number: int = 1,
    phase: str = "regular",
) -> dict:
    request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        MESSAGES_URL,
        data=request_data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response_opened = False
    started = time.monotonic()
    if trace:
        trace.record_provider_request(
            "provider_request_started",
            provider="anthropic",
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
                provider="anthropic",
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
        http_diagnostics = _anthropic_http_diagnostics(error)
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error, **http_diagnostics,
        )
        raise RuntimeError(
            f"Anthropic API-Fehler: HTTP {error.code} {error.reason}"
        ) from error
    except URLError as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"Anthropic Netzwerkfehler: {error.reason}"
        ) from error
    except (TimeoutError, OSError) as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"Anthropic Netzwerkfehler: {error}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            "Anthropic API-Fehler: Antwort ist kein gueltiges JSON"
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
    **diagnostics,
) -> None:
    if trace:
        trace.record_provider_request(
            "provider_request_failed",
            provider="anthropic",
            request_number=request_number,
            phase=phase,
            timeout_seconds=timeout_seconds,
            payload_bytes=len(request_data),
            response_opened=response_opened,
            success=False,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            exception_type=type(error).__name__,
            error=str(error),
            **diagnostics,
        )


def _safe_error_message(value) -> str | None:
    if not isinstance(value, str):
        return None
    message = "".join(
        character if character >= " " else " "
        for character in value
    ).strip()
    message = re.sub(
        r"(?i)\b(authorization|x-api-key|api[_ -]?key)\b"
        r"(\s*[:=]\s*)(\S+)",
        r"\1\2[REDACTED]",
        message,
    )
    return message[:MAX_HTTP_ERROR_MESSAGE_CHARS] or None


def _anthropic_http_diagnostics(error: HTTPError) -> dict:
    diagnostics = {"http_status": error.code}

    headers = error.headers
    if headers:
        request_id = headers.get("request-id") or headers.get("x-request-id")
        if isinstance(request_id, str):
            request_id = request_id.strip()[:MAX_PROVIDER_REQUEST_ID_CHARS]
            if request_id:
                diagnostics["provider_request_id"] = request_id

    try:
        raw_body = error.read(MAX_HTTP_ERROR_BODY_BYTES + 1)
    except (OSError, ValueError):
        return diagnostics
    if not isinstance(raw_body, bytes):
        return diagnostics

    body_truncated = len(raw_body) > MAX_HTTP_ERROR_BODY_BYTES
    if body_truncated:
        raw_body = raw_body[:MAX_HTTP_ERROR_BODY_BYTES]
        diagnostics["error_body_truncated"] = True

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return diagnostics
    if not isinstance(body, dict):
        return diagnostics

    safe_body = {}
    top_level_type = _safe_error_message(body.get("type"))
    if top_level_type:
        safe_body["type"] = top_level_type
    error_details = body.get("error")
    if isinstance(error_details, dict):
        safe_error = {}
        error_type = _safe_error_message(error_details.get("type"))
        error_message = _safe_error_message(error_details.get("message"))
        if error_type:
            safe_error["type"] = error_type
        if error_message:
            safe_error["message"] = error_message
        if safe_error:
            safe_body["error"] = safe_error
    if safe_body:
        diagnostics["error_body"] = safe_body
    return diagnostics


def _request_model(
    api_key: str,
    model: str,
    context: str,
    trace: atlas_search.InvestigationTrace | None = None,
) -> str:
    # Untersuchungszyklus V1: Mehrschrittprozess ueber die Anthropic
    # Messages API (tool_use/tool_result-Bloecke, volle messages-Historie
    # je Runde). Eine Runde ohne tool_use-Block beendet die Untersuchung
    # (Modell entscheidet fachlich selbst). atlas_search.MAX_INVESTIGATION_STEPS
    # ist eine rein technische Sicherheitsgrenze - siehe Auftrag
    # "SICHERHEITSGRENZE".
    messages: list[dict] = [{"role": "user", "content": context}]
    used_sources: list[dict] = []
    seen_source_paths: set[str] = set()
    request_number = 0

    for _step in range(atlas_search.MAX_INVESTIGATION_STEPS):
        payload = {
            "model": model,
            "max_tokens": 8192,
            "system": MODEL_INSTRUCTIONS,
            "messages": messages,
            "tools": _tool_definitions(),
        }
        request_number += 1
        result = _call_messages_api(
            api_key,
            payload,
            trace=trace,
            request_number=request_number,
            phase="regular",
        )

        if result.get("stop_reason") == "max_tokens":
            raise RuntimeError(
                "Anthropic API-Fehler: Antwort wurde am Tokenlimit abgeschnitten"
            )

        content_blocks = result.get("content", [])
        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

        if not tool_use_blocks:
            text = _extract_text(result)
            if not text:
                raise RuntimeError("Anthropic API-Fehler: leere Modellantwort")
            return text + atlas_search.format_used_sources(used_sources)

        messages.append({"role": "assistant", "content": content_blocks})

        tool_result_blocks = []
        for block in tool_use_blocks:
            tool_result = atlas_search.execute_tool(
                block.get("name"), block.get("input") or {}
            )
            if trace:
                trace.record(
                    _step + 1,
                    block.get("name"),
                    block.get("input") or {},
                    tool_result,
                )
            if block.get("name") == atlas_search.READ_TOOL_NAME and "error" not in tool_result:
                if tool_result["path"] not in seen_source_paths:
                    seen_source_paths.add(tool_result["path"])
                    used_sources.append(
                        {"path": tool_result["path"], "kind": tool_result["kind"]}
                    )
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block.get("id"),
                "content": json.dumps(tool_result, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_result_blocks})

    if trace:
        trace.record_event(
            "completion_phase_started",
            regular_tool_rounds=atlas_search.MAX_INVESTIGATION_STEPS,
        )
    payload = {
        "model": model,
        "max_tokens": 8192,
        "system": MODEL_INSTRUCTIONS + COMPLETION_PHASE_INSTRUCTION,
        "messages": messages,
        "tools": _tool_definitions(),
    }
    request_number += 1
    result = _call_messages_api(
        api_key,
        payload,
        trace=trace,
        request_number=request_number,
        phase="completion",
    )
    if result.get("stop_reason") == "max_tokens":
        raise RuntimeError(
            "Anthropic API-Fehler: Antwort wurde am Tokenlimit abgeschnitten"
        )
    content_blocks = result.get("content", [])
    tool_use_blocks = [
        block for block in content_blocks if block.get("type") == "tool_use"
    ]
    if tool_use_blocks:
        if trace:
            trace.record_event(
                "completion_phase_tool_request_rejected",
                requested_tool_count=len(tool_use_blocks),
                requested_tools=[block.get("name") for block in tool_use_blocks],
            )
        raise RuntimeError(COMPLETION_PHASE_TOOL_REQUEST_ERROR)

    text = _extract_text(result)
    if not text:
        raise RuntimeError("Anthropic API-Fehler: leere Modellantwort")
    if trace:
        trace.record_event("completion_phase_completed", outcome="terminal")
    return text + atlas_search.format_used_sources(used_sources)


def generate_content(
    work_item_id: str,
    work_steps_snapshot: list[dict] | None = None,
    additional_task: str | None = None,
) -> tuple[str, str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY fehlt")

    model = os.environ.get("ANTHROPIC_MODEL", "").strip()
    if not model:
        raise ValueError("ANTHROPIC_MODEL fehlt")

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
    participant_id = f"anthropic:{model}"
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
        description="Erzeugt einen Anthropic-WorkStep."
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
