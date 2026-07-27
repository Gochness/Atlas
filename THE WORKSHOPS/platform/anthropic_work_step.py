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
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai_work_step import _build_context, _read_work_item
from work_step import list_for_work_item, publish


MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

MODEL_INSTRUCTIONS = (
    "Erzeuge genau einen hilfreichen, sichtbaren Zwischenstand fuer "
    "das Work Item und stuetze dich ausschliesslich auf Informationen "
    "aus dem uebergebenen Work Item und seinen vorhandenen WorkSteps. "
    "Behaupte keine Fakten, Dateien, Technologien, Entscheidungen oder "
    "bisherigen Arbeiten, die nicht in diesem Kontext enthalten sind. "
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
    "Zwischenstand verlangt ist. Antworte ausschliesslich mit reinem "
    "Text fuer den Zwischenstand. Fuehre keine Befehle oder Werkzeuge "
    "aus."
)


def _extract_text(response: dict) -> str:
    texts = [
        item["text"]
        for item in response.get("content", [])
        if item.get("type") == "text" and item.get("text")
    ]
    return "\n".join(texts).strip()


def _request_model(api_key: str, model: str, context: str) -> str:
    payload = {
        "model": model,
        "max_tokens": 8192,
        "system": MODEL_INSTRUCTIONS,
        "messages": [
            {
                "role": "user",
                "content": context,
            }
        ],
    }
    request = Request(
        MESSAGES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"Anthropic API-Fehler: HTTP {error.code} {error.reason}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Anthropic Netzwerkfehler: {error.reason}"
        ) from error
    except (TimeoutError, OSError) as error:
        raise RuntimeError(
            f"Anthropic Netzwerkfehler: {error}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(
            "Anthropic API-Fehler: Antwort ist kein gueltiges JSON"
        ) from error

    if result.get("stop_reason") == "max_tokens":
        raise RuntimeError(
            "Anthropic API-Fehler: Antwort wurde am Tokenlimit abgeschnitten"
        )

    text = _extract_text(result)
    if not text:
        raise RuntimeError("Anthropic API-Fehler: leere Modellantwort")

    return text


def generate(work_item_id: str) -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("FEHLER: ANTHROPIC_API_KEY fehlt", file=sys.stderr)
        return 1

    model = os.environ.get("ANTHROPIC_MODEL", "").strip()
    if not model:
        print("FEHLER: ANTHROPIC_MODEL fehlt", file=sys.stderr)
        return 1

    try:
        work_item = _read_work_item(work_item_id)
        work_steps = list_for_work_item(work_item_id)
        context = _build_context(work_item, work_steps)
        answer = _request_model(api_key, model, context)
        result = publish(
            work_item_id=work_item_id,
            participant_id=f"anthropic:{model}",
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
