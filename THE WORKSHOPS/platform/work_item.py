"""
Atlas Work Item Tracker v0.1

Verwaltet Work Items unter THE VAULT/work_items/ als einzelne YAML-Dateien.
Ein Work Item haelt fest, wer gerade woran arbeitet, bevor daraus ein
Repository-Ereignis entsteht (vgl. ART-0007: Absicht ist nicht aus dem
Repository rekonstruierbar).

Befehle:
    python work_item.py start --by <id> "<intent>"
    python work_item.py complete WI-XXXX
    python work_item.py abandon WI-XXXX

Format pro Datei:
    id, intent, created_by, created_at, base_commit, status

Alle Felder ausser intent und created_by werden vom System ergaenzt.

Statuswerte: open (bei start) -> completed | abandoned.
Es gibt aktuell keinen Befehl, der in_progress setzt; ein Work Item
geht direkt von open zu completed oder abandoned ueber.
"""

import re
import subprocess
import sys
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORK_ITEMS_DIR = Path("THE VAULT/work_items")

WI_REF_RE = re.compile(r"^WI-(\d{4})$")

STATUS_OPEN      = "open"
STATUS_COMPLETED = "completed"
STATUS_ABANDONED = "abandoned"
TERMINAL_STATUSES = {STATUS_COMPLETED, STATUS_ABANDONED}


@dataclass
class WorkItemResult:
    success: bool
    id:      Optional[str] = None
    path:    Optional[str] = None
    status:  Optional[str] = None
    error:   Optional[str] = None


def _head_sha() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    return r.stdout.strip()


def _existing_ids(work_items_dir: Path) -> list[int]:
    if not work_items_dir.exists():
        return []
    ids = []
    for f in work_items_dir.glob("WI-*.yaml"):
        m = WI_REF_RE.match(f.stem)
        if m:
            ids.append(int(m.group(1)))
    return ids


def _next_id(work_items_dir: Path) -> str:
    existing = _existing_ids(work_items_dir)
    n = max(existing) + 1 if existing else 1
    return f"WI-{n:04d}"


def _path_for(wi_id: str, work_items_dir: Path) -> Path:
    return work_items_dir / f"{wi_id}.yaml"


def _load(wi_id: str, work_items_dir: Path) -> Optional[dict]:
    path = _path_for(wi_id, work_items_dir)
    if not path.exists():
        return None
    with open(path, encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def _save(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Kernfunktionen
# ---------------------------------------------------------------------------

def start(intent: str, created_by: str, work_items_dir: Path = WORK_ITEMS_DIR) -> WorkItemResult:
    if not intent or not intent.strip():
        return WorkItemResult(success=False, error="intent darf nicht leer sein")
    if not created_by or not created_by.strip():
        return WorkItemResult(success=False, error="--by darf nicht leer sein")

    work_items_dir.mkdir(parents=True, exist_ok=True)
    wi_id = _next_id(work_items_dir)
    data = {
        "id":          wi_id,
        "intent":      intent,
        "created_by":  created_by,
        "created_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_commit": _head_sha(),
        "status":      STATUS_OPEN,
    }
    path = _path_for(wi_id, work_items_dir)
    _save(data, path)
    return WorkItemResult(success=True, id=wi_id, path=str(path), status=STATUS_OPEN)


def _transition(wi_id: str, new_status: str, work_items_dir: Path) -> WorkItemResult:
    data = _load(wi_id, work_items_dir)
    if data is None:
        return WorkItemResult(success=False, id=wi_id, error=f"Work Item nicht gefunden: {wi_id}")

    current = data.get("status")
    if current in TERMINAL_STATUSES:
        return WorkItemResult(
            success=False, id=wi_id, status=current,
            error=f"Work Item {wi_id} ist bereits abgeschlossen (status={current}) – keine erneute Statusaenderung moeglich",
        )

    data["status"] = new_status
    path = _path_for(wi_id, work_items_dir)
    _save(data, path)
    return WorkItemResult(success=True, id=wi_id, path=str(path), status=new_status)


def complete(wi_id: str, work_items_dir: Path = WORK_ITEMS_DIR) -> WorkItemResult:
    return _transition(wi_id, STATUS_COMPLETED, work_items_dir)


def abandon(wi_id: str, work_items_dir: Path = WORK_ITEMS_DIR) -> WorkItemResult:
    return _transition(wi_id, STATUS_ABANDONED, work_items_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_result(result: WorkItemResult) -> None:
    if result.success:
        print(f"OK  {result.id}  {result.status}  {result.path}")
    else:
        print(f"FEHLER: {result.error}")


def main():
    # Windows-Konsolen nutzen sonst cp1252 und brechen bei Sonderzeichen
    # wie "–" in Fehlermeldungen (gleiche Bugklasse wie in state_generator.py).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    if cmd == "start":
        rest = args[1:]
        if len(rest) < 3 or rest[0] != "--by":
            print('Verwendung: python work_item.py start --by <id> "<intent>"')
            sys.exit(1)
        created_by = rest[1]
        intent = " ".join(rest[2:]).strip()
        result = start(intent, created_by)
        _print_result(result)
        sys.exit(0 if result.success else 1)

    elif cmd == "complete":
        if len(args) != 2:
            print("Verwendung: python work_item.py complete WI-XXXX")
            sys.exit(1)
        result = complete(args[1])
        _print_result(result)
        sys.exit(0 if result.success else 1)

    elif cmd == "abandon":
        if len(args) != 2:
            print("Verwendung: python work_item.py abandon WI-XXXX")
            sys.exit(1)
        result = abandon(args[1])
        _print_result(result)
        sys.exit(0 if result.success else 1)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
