"""
Duenner CLI-Wrapper um submission_adapter.submit_structured().

Nimmt bereits vollstaendig strukturierte Submission-Daten als einzelnes
JSON-Argument entgegen, wandelt sie in ein Python-Dict um und uebergibt
sie unveraendert an submit_structured() - das serialisiert sie seinerseits
in eine temporaere YAML-Datei und ruft den bestehenden
submission_service.submit()-Pfad auf (siehe submission_adapter.py).

Verwendung:
    python submit_structured.py '<json>'

Erwartetes JSON-Format (siehe validator.py):
    {"submission": {...}, "candidate": {...}}

Keine eigene Submission-Logik, keine Erzeugung oder Interpretation von
base_commit - dieser Wrapper reicht nur durch.
"""

import json
import sys

from submission_adapter import submit_structured


def main():
    # Windows-Konsolen nutzen sonst cp1252 und brechen bei Sonderzeichen
    # in Fehlermeldungen oder Submission-Inhalten (gleiche Bugklasse wie
    # in work_item.py/work_step.py).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    if len(args) != 1:
        print("Verwendung: python submit_structured.py '<json>'")
        sys.exit(1)

    try:
        data = json.loads(args[0])
    except json.JSONDecodeError as error:
        print(f"FEHLER: Eingabe ist kein gueltiges JSON: {error}")
        sys.exit(1)

    result = submit_structured(data)
    if result.success:
        print(f"OK  {result.submission_id}  {result.pull_request_url}")
    else:
        print(f"FEHLER: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
