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
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from anthropic_work_step import MODEL_INSTRUCTIONS
from openai_work_step import _build_context, _read_work_item
from work_step import list_for_work_item, publish


GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)


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


def _request_model(api_key: str, model: str, context: str) -> str:
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": MODEL_INSTRUCTIONS,
                }
            ],
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": context,
                    }
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 8192,
        },
    }
    url = GENERATE_CONTENT_URL.format(model=quote(model, safe=""))
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"Gemini API-Fehler: HTTP {error.code} {error.reason}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Gemini Netzwerkfehler: {error.reason}"
        ) from error
    except (TimeoutError, OSError) as error:
        raise RuntimeError(
            f"Gemini Netzwerkfehler: {error}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(
            "Gemini API-Fehler: Antwort ist kein gueltiges JSON"
        ) from error

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
    if finish_reason and finish_reason != "STOP":
        raise RuntimeError(
            f"Gemini API-Fehler: Modellantwort beendet ({finish_reason})"
        )

    text = _extract_text(result)
    if not text:
        raise RuntimeError("Gemini API-Fehler: leere Modellantwort")

    return text


def generate(work_item_id: str) -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("FEHLER: GEMINI_API_KEY fehlt", file=sys.stderr)
        return 1

    model = os.environ.get("GEMINI_MODEL", "").strip()
    if not model:
        print("FEHLER: GEMINI_MODEL fehlt", file=sys.stderr)
        return 1

    try:
        work_item = _read_work_item(work_item_id)
        work_steps = list_for_work_item(work_item_id)
        context = _build_context(work_item, work_steps)
        answer = _request_model(api_key, model, context)
        result = publish(
            work_item_id=work_item_id,
            participant_id=f"gemini:{model}",
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
