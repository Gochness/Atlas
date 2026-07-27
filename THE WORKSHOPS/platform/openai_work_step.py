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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from work_item import REPO_ROOT, read_context_files
from work_step import list_for_work_item, publish


WORK_ITEMS_DIR = Path("THE VAULT/work_items")
RESPONSES_URL = "https://api.openai.com/v1/responses"


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
) -> str:
    context = {
        "work_item": {
            "id": work_item.get("id"),
            "intent": work_item.get("intent"),
        },
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


def _request_model(api_key: str, model: str, context: str) -> str:
    payload = {
        "model": model,
        "instructions": (
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
        ),
        "input": context,
    }
    request = Request(
        RESPONSES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"OpenAI API-Fehler: HTTP {error.code} {error.reason}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"OpenAI Netzwerkfehler: {error.reason}"
        ) from error
    except (TimeoutError, OSError) as error:
        raise RuntimeError(
            f"OpenAI Netzwerkfehler: {error}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(
            "OpenAI API-Fehler: Antwort ist kein gueltiges JSON"
        ) from error

    text = _extract_text(result)
    if not text:
        raise RuntimeError("OpenAI API-Fehler: leere Modellantwort")

    return text


def generate(work_item_id: str) -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("FEHLER: OPENAI_API_KEY fehlt", file=sys.stderr)
        return 1

    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not model:
        print("FEHLER: OPENAI_MODEL fehlt", file=sys.stderr)
        return 1

    try:
        work_item = _read_work_item(work_item_id)
        work_steps = list_for_work_item(work_item_id)
        context = _build_context(work_item, work_steps)
        answer = _request_model(api_key, model, context)
        result = publish(
            work_item_id=work_item_id,
            participant_id=f"openai:{model}",
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
