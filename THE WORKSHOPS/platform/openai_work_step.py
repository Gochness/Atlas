"""
Erzeugt genau einen OpenAI-WorkStep fuer ein bestehendes Work Item.

Verwendung:
    python openai_work_step.py generate --work-item WI-XXXX

Erforderliche Umgebungsvariablen:
    OPENAI_API_KEY
    OPENAI_MODEL
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

import atlas_search
from work_item import REPO_ROOT, read_context_files
from work_step import list_for_work_item, publish


WORK_ITEMS_DIR = Path("THE VAULT/work_items")
RESPONSES_URL = "https://api.openai.com/v1/responses"
REGULAR_REQUEST_TIMEOUT_SECONDS = 100
COMPLETION_REQUEST_TIMEOUT_SECONDS = 100
UNBOUNDED_DIAGNOSTIC_ENV = "ATLAS_OPENAI_UNBOUNDED_DIAGNOSTIC"
UNBOUNDED_DIAGNOSTIC_REQUEST_TIMEOUT_SECONDS = 100


def _read_work_item(work_item_id: str) -> dict:
    path = WORK_ITEMS_DIR / f"{work_item_id}.yaml"
    if not path.exists():
        raise ValueError(f"Work Item nicht gefunden: {work_item_id}")

    with open(path, encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict) or data.get("id") != work_item_id:
        raise ValueError(f"Ungueltiges Work Item: {work_item_id}")

    data.setdefault("context_refs", [])
    return data


def _build_context(
    work_item: dict,
    work_steps: list[dict],
    repo_root: Path = REPO_ROOT,
    additional_task: str | None = None,
) -> str:
    context = {
        "work_item": {
            "id": work_item.get("id"),
            "intent": work_item.get("intent"),
        },
        "atlas_knowledge_index": atlas_search.format_knowledge_index(
            atlas_search.build_knowledge_index(repo_root)
        ),
        "existing_work_steps": [
            {
                "id": step.get("id"),
                "participant_id": step.get("participant_id"),
                "content": step.get("content"),
                "created_at": step.get("created_at"),
            }
            for step in work_steps
        ],
        "context_files": read_context_files(
            work_item.get("context_refs", []),
            repo_root,
        ),
    }
    if additional_task:
        context["additional_task"] = additional_task
    return json.dumps(context, ensure_ascii=False)


def _extract_text(response: dict) -> str:
    texts: list[str] = []

    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])

    return "\n".join(texts).strip()


_INSTRUCTIONS = (
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
    "Pruefe waehrend der Untersuchung nach jedem wesentlichen "
    "Erkenntnisgewinn, ob die vorhandene Evidenz bereits ausreicht, "
    "um den Auftrag belastbar zu beantworten. Pruefe dabei, welche "
    "Teile des Auftrags bereits durch relevante Evidenz abgedeckt "
    "sind, welche Teile tatsaechlich noch zusaetzliche Information "
    "benoetigen und ob ein weiterer Werkzeugaufruf voraussichtlich "
    "eine fuer das Ergebnis relevante Informationsluecke schliesst. "
    "Wenn die vorhandene Evidenz fuer eine belastbare Antwort "
    "ausreicht, beende die Recherche, fordere keine weiteren "
    "Werkzeuge an und synthetisiere das Ergebnis. Eine vollstaendige "
    "Sichtung des Atlas-Wissensraums ist nicht erforderlich. Lies "
    "weitere Quellen nicht allein deshalb, weil sie vorhanden oder "
    "moeglicherweise relevant sind. Zusaetzliche Verifikation ist "
    "legitim, wenn sie fuer die Belastbarkeit einer wesentlichen "
    "Aussage erforderlich ist. Fehlende oder nicht ausreichend "
    "belegbare Informationen darfst und sollst du ausdruecklich als "
    "Informationsluecke benennen, statt den gesamten Wissensraum nach "
    "moeglicher zusaetzlicher Evidenz abzusuchen. Diese Pruefung setzt "
    "keine bestimmte Rundenzahl und kein Ziel moeglichst weniger "
    "Werkzeugaufrufe; notwendige Recherche und notwendige Pruefung von "
    "Primaerquellen setzt du fort. Ergebnisqualitaet hat Vorrang vor "
    "Geschwindigkeit. "
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

_COMPLETION_PHASE_INSTRUCTION = (
    " Das regulaere Werkzeugbudget ist jetzt ausgeschoepft. Verarbeite "
    "die bereits erhaltenen Werkzeugergebnisse und antworte ausschliesslich "
    "mit dem fachlichen Zwischenstand. Fordere keine weiteren Werkzeuge an."
)

_COMPLETION_PHASE_TOOL_REQUEST_ERROR = (
    "Untersuchung technisch abgebrochen: Die Sicherheitsgrenze des "
    "regulaeren Werkzeugbudgets von "
    f"{atlas_search.MAX_INVESTIGATION_STEPS} Werkzeug-Runden war "
    "ausgeschoepft und das Modell hat auch in der Abschlussphase weitere "
    "Werkzeugarbeit angefordert."
)


def _tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "name": atlas_search.SEARCH_TOOL_NAME,
            "description": atlas_search.SEARCH_TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "type": "function",
            "name": atlas_search.READ_TOOL_NAME,
            "description": atlas_search.READ_TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    ]


def _extract_function_calls(result: dict) -> list[dict]:
    return [
        item for item in result.get("output", [])
        if item.get("type") == "function_call"
    ]


def _call_responses_api(
    api_key: str,
    payload: dict,
    timeout_seconds: int = REGULAR_REQUEST_TIMEOUT_SECONDS,
    trace: atlas_search.InvestigationTrace | None = None,
    request_number: int = 1,
    phase: str = "regular",
) -> dict:
    request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        RESPONSES_URL,
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response_opened = False
    started = time.monotonic()
    if trace:
        trace.record_provider_request(
            "provider_request_started",
            provider="openai",
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
                provider="openai",
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
            f"OpenAI API-Fehler: HTTP {error.code} {error.reason}"
        ) from error
    except URLError as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"OpenAI Netzwerkfehler: {error.reason}"
        ) from error
    except (TimeoutError, OSError) as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            f"OpenAI Netzwerkfehler: {error}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        _record_request_failure(
            trace, request_number, phase, timeout_seconds, request_data,
            response_opened, started, error,
        )
        raise RuntimeError(
            "OpenAI API-Fehler: Antwort ist kein gueltiges JSON"
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
            provider="openai",
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
    unbounded_diagnostic: bool = False,
) -> str:
    # Untersuchungszyklus V1: Mehrschrittprozess ueber die OpenAI
    # Responses API (previous_response_id verkettet die Runden). Jede
    # Runde ohne function_call beendet die Untersuchung (Modell
    # entscheidet fachlich selbst). atlas_search.MAX_INVESTIGATION_STEPS
    # ist eine rein technische Sicherheitsgrenze - siehe Auftrag
    # "SICHERHEITSGRENZE".
    payload = {
        "model": model,
        "instructions": _INSTRUCTIONS,
        "input": context,
        "tools": _tool_definitions(),
    }
    used_sources: list[dict] = []
    seen_source_paths: set[str] = set()
    regular_request_timeout_seconds = (
        UNBOUNDED_DIAGNOSTIC_REQUEST_TIMEOUT_SECONDS
        if unbounded_diagnostic
        else REGULAR_REQUEST_TIMEOUT_SECONDS
    )

    step = 0
    request_number = 0
    while (
        unbounded_diagnostic
        or step < atlas_search.MAX_INVESTIGATION_STEPS
    ):
        request_number += 1
        result = _call_responses_api(
            api_key,
            payload,
            timeout_seconds=regular_request_timeout_seconds,
            trace=trace,
            request_number=request_number,
            phase="regular",
        )
        function_calls = _extract_function_calls(result)

        if not function_calls:
            text = _extract_text(result)
            if not text:
                raise RuntimeError("OpenAI API-Fehler: leere Modellantwort")
            return text + atlas_search.format_used_sources(used_sources)

        follow_up_input = []
        for call in function_calls:
            try:
                arguments = json.loads(call.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_result = atlas_search.execute_tool(call.get("name"), arguments)
            if trace:
                trace.record(
                    step + 1,
                    call.get("name"),
                    arguments,
                    tool_result,
                )
            if call.get("name") == atlas_search.READ_TOOL_NAME and "error" not in tool_result:
                if tool_result["path"] not in seen_source_paths:
                    seen_source_paths.add(tool_result["path"])
                    used_sources.append(
                        {"path": tool_result["path"], "kind": tool_result["kind"]}
                    )
            follow_up_input.append({
                "type": "function_call_output",
                "call_id": call.get("call_id"),
                "output": json.dumps(tool_result, ensure_ascii=False),
            })

        payload = {
            "model": model,
            "previous_response_id": result.get("id"),
            "input": follow_up_input,
            "tools": _tool_definitions(),
        }
        step += 1

    if trace:
        trace.record_event(
            "completion_phase_started",
            regular_tool_rounds=atlas_search.MAX_INVESTIGATION_STEPS,
        )
    payload["instructions"] = _INSTRUCTIONS + _COMPLETION_PHASE_INSTRUCTION
    request_number += 1
    result = _call_responses_api(
        api_key,
        payload,
        timeout_seconds=COMPLETION_REQUEST_TIMEOUT_SECONDS,
        trace=trace,
        request_number=request_number,
        phase="completion",
    )
    function_calls = _extract_function_calls(result)
    if function_calls:
        if trace:
            trace.record_event(
                "completion_phase_tool_request_rejected",
                requested_tool_count=len(function_calls),
                requested_tools=[call.get("name") for call in function_calls],
            )
        raise RuntimeError(_COMPLETION_PHASE_TOOL_REQUEST_ERROR)

    text = _extract_text(result)
    if not text:
        raise RuntimeError("OpenAI API-Fehler: leere Modellantwort")
    if trace:
        trace.record_event("completion_phase_completed", outcome="terminal")
    return text + atlas_search.format_used_sources(used_sources)


def generate_content(
    work_item_id: str,
    work_steps_snapshot: list[dict] | None = None,
    additional_task: str | None = None,
) -> tuple[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY fehlt")

    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not model:
        raise ValueError("OPENAI_MODEL fehlt")

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
    participant_id = f"openai:{model}"
    trace = atlas_search.InvestigationTrace(work_item_id, participant_id)
    unbounded_diagnostic = (
        os.environ.get(UNBOUNDED_DIAGNOSTIC_ENV, "").strip() == "1"
    )
    answer = _request_model(
        api_key,
        model,
        context,
        trace,
        unbounded_diagnostic,
    )
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
        description="Erzeugt einen OpenAI-WorkStep."
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
