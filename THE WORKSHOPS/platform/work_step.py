"""
Atlas Work Step Tracker v0.1

Verwaltet sichtbare Zwischenstaende laufender Arbeit unter
THE VAULT/work_steps/ als einzelne YAML-Dateien.

Ein Work Step gehoert zu einem bestehenden Work Item und haelt einen
veroeffentlichten Zwischenstand eines Teilnehmers fest.

Befehl:
    python work_step.py publish --work-item WI-XXXX --by participant-id "content"

Format pro Datei:
    id, work_item_id, participant_id, content, created_at

Alle Felder ausser work_item_id, participant_id und content werden
vom System ergaenzt.
"""

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


WORK_ITEMS_DIR = Path("THE VAULT/work_items")
WORK_STEPS_DIR = Path("THE VAULT/work_steps")

WORK_ITEM_REF_RE = re.compile(r"^WI-\d{4}$")
WORK_STEP_REF_RE = re.compile(r"^WS-(\d{4})$")


@dataclass
class WorkStepResult:
    success: bool
    id: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None


def _existing_ids(work_steps_dir: Path) -> list[int]:
    if not work_steps_dir.exists():
        return []

    ids: list[int] = []

    for path in work_steps_dir.glob("WS-*.yaml"):
        match = WORK_STEP_REF_RE.match(path.stem)
        if match:
            ids.append(int(match.group(1)))

    return ids


def _next_id(work_steps_dir: Path) -> str:
    existing = _existing_ids(work_steps_dir)
    number = max(existing) + 1 if existing else 1
    return f"WS-{number:04d}"


def _work_item_exists(work_item_id: str, work_items_dir: Path) -> bool:
    if not WORK_ITEM_REF_RE.match(work_item_id):
        return False

    return (work_items_dir / f"{work_item_id}.yaml").exists()


def _save(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as file:
        yaml.dump(data, file, allow_unicode=True, sort_keys=False)


def publish(
    work_item_id: str,
    participant_id: str,
    content: str,
    work_items_dir: Path = WORK_ITEMS_DIR,
    work_steps_dir: Path = WORK_STEPS_DIR,
) -> WorkStepResult:
    if not work_item_id or not work_item_id.strip():
        return WorkStepResult(
            success=False,
            error="work_item_id darf nicht leer sein",
        )

    if not participant_id or not participant_id.strip():
        return WorkStepResult(
            success=False,
            error="--by darf nicht leer sein",
        )

    if not content or not content.strip():
        return WorkStepResult(
            success=False,
            error="content darf nicht leer sein",
        )

    if not _work_item_exists(work_item_id, work_items_dir):
        return WorkStepResult(
            success=False,
            error=f"Work Item nicht gefunden: {work_item_id}",
        )

    work_steps_dir.mkdir(parents=True, exist_ok=True)

    work_step_id = _next_id(work_steps_dir)

    data = {
        "id": work_step_id,
        "work_item_id": work_item_id,
        "participant_id": participant_id,
        "content": content.strip(),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    path = work_steps_dir / f"{work_step_id}.yaml"
    _save(data, path)

    return WorkStepResult(
        success=True,
        id=work_step_id,
        path=str(path),
    )


def _print_result(result: WorkStepResult) -> None:
    if result.success:
        print(f"OK  {result.id}  {result.path}")
    else:
        print(f"FEHLER: {result.error}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0]

    if command == "publish":
        rest = args[1:]

        if len(rest) < 5 or rest[0] != "--work-item" or rest[2] != "--by":
            print(
                'Verwendung: python work_step.py publish '
                '--work-item WI-XXXX --by participant-id "content"'
            )
            sys.exit(1)

        work_item_id = rest[1]
        participant_id = rest[3]
        content = " ".join(rest[4:]).strip()

        result = publish(
            work_item_id=work_item_id,
            participant_id=participant_id,
            content=content,
        )

        _print_result(result)
        sys.exit(0 if result.success else 1)

    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()
