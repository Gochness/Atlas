"""
Atlas Work Item Tracker v0.1

Verwaltet Work Items unter THE VAULT/work_items/ als einzelne YAML-Dateien.
Ein Work Item haelt fest, wer gerade woran arbeitet, bevor daraus ein
Repository-Ereignis entsteht (vgl. ART-0007: Absicht ist nicht aus dem
Repository rekonstruierbar).

Befehle:
    python work_item.py start --by <id> "<intent>"
    python work_item.py list
    python work_item.py resolve-file <filename>
    python work_item.py set-context-refs WI-XXXX '["path/to/file"]'
    python work_item.py complete WI-XXXX
    python work_item.py abandon WI-XXXX

Format pro Datei:
    id, intent, created_by, created_at, base_commit, status, context_refs

Alle Felder ausser intent und created_by werden vom System ergaenzt.

Statuswerte: open (bei start) -> completed | abandoned.
Es gibt aktuell keinen Befehl, der in_progress setzt; ein Work Item
geht direkt von open zu completed oder abandoned ueber.
"""

import json
import re
import subprocess
import sys
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORK_ITEMS_DIR = Path("THE VAULT/work_items")
REPO_ROOT = Path(__file__).resolve().parents[2]

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


def _is_sensitive_path(relative_path: Path) -> bool:
    parts = {part.casefold() for part in relative_path.parts}
    if ".git" in parts or ".venv" in parts:
        return True
    if any(
        marker in part
        for part in parts
        for marker in ("credential", "secret")
    ):
        return True

    name = relative_path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    if relative_path.suffix.casefold() in {".key", ".pem"}:
        return True
    return False


def read_context_files(
    context_refs: object,
    repo_root: Path = REPO_ROOT,
) -> list[dict]:
    if context_refs is None:
        context_refs = []
    if not isinstance(context_refs, list):
        raise ValueError("context_refs muss eine Liste sein")

    root = repo_root.resolve()
    context_files = []
    seen: set[str] = set()

    for value in context_refs:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("context_ref muss ein nicht leerer Pfad sein")

        reference = Path(value.strip())
        if reference.is_absolute():
            raise ValueError(f"Absolute context_ref ist nicht erlaubt: {value}")

        try:
            path = (root / reference).resolve(strict=True)
            relative_path = path.relative_to(root)
        except FileNotFoundError as error:
            raise ValueError(f"context_ref nicht gefunden: {value}") from error
        except (OSError, ValueError) as error:
            raise ValueError(
                f"context_ref liegt ausserhalb des Atlas-Repositories: {value}"
            ) from error

        if _is_sensitive_path(relative_path):
            raise ValueError(f"Gesperrte context_ref: {value}")
        if not path.is_file():
            raise ValueError(f"context_ref ist keine Datei: {value}")

        canonical_ref = relative_path.as_posix()
        if canonical_ref in seen:
            continue

        try:
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise ValueError(
                f"context_ref ist keine lesbare UTF-8-Textdatei: {value}"
            ) from error
        if "\x00" in content:
            raise ValueError(
                f"context_ref ist keine lesbare UTF-8-Textdatei: {value}"
            )

        seen.add(canonical_ref)
        context_files.append({"path": canonical_ref, "content": content})

    return context_files


def validate_context_refs(
    context_refs: object,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    return [item["path"] for item in read_context_files(context_refs, repo_root)]


def resolve_repository_files(
    filename: str,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Dateiname darf nicht leer sein")

    filename = filename.strip()
    candidate_name = Path(filename)
    if (
        candidate_name.name != filename
        or filename in {".", ".."}
        or any(marker in filename for marker in ("*", "?", "[", "]"))
    ):
        raise ValueError("Nur ein exakter Dateiname ohne Pfad oder Wildcards ist erlaubt")

    root = repo_root.resolve()
    matches: list[str] = []

    for candidate in root.rglob("*"):
        if candidate.name.casefold() != filename.casefold():
            continue

        try:
            resolved = candidate.resolve(strict=True)
            relative_path = resolved.relative_to(root)
        except (FileNotFoundError, OSError, ValueError):
            continue

        if _is_sensitive_path(relative_path) or not resolved.is_file():
            continue

        matches.append(relative_path.as_posix())

    return sorted(set(matches), key=str.casefold)


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
        "context_refs": [],
    }
    path = _path_for(wi_id, work_items_dir)
    _save(data, path)
    return WorkItemResult(success=True, id=wi_id, path=str(path), status=STATUS_OPEN)


def list_work_items(work_items_dir: Path = WORK_ITEMS_DIR) -> list[dict]:
    if not work_items_dir.exists():
        return []

    work_items = []
    for path in sorted(work_items_dir.glob("WI-*.yaml")):
        with open(path, encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            normalized = dict(data)
            normalized.setdefault("context_refs", [])
            work_items.append(normalized)
    return work_items


def set_context_refs(
    wi_id: str,
    context_refs: object,
    work_items_dir: Path = WORK_ITEMS_DIR,
    repo_root: Path = REPO_ROOT,
) -> WorkItemResult:
    data = _load(wi_id, work_items_dir)
    if data is None:
        return WorkItemResult(success=False, id=wi_id, error=f"Work Item nicht gefunden: {wi_id}")

    current = data.get("status")
    if current != STATUS_OPEN:
        return WorkItemResult(
            success=False,
            id=wi_id,
            status=current,
            error=f"Work Item {wi_id} ist nicht offen (status={current})",
        )

    try:
        validated_refs = validate_context_refs(context_refs, repo_root)
    except ValueError as error:
        return WorkItemResult(success=False, id=wi_id, status=current, error=str(error))

    data["context_refs"] = validated_refs
    path = _path_for(wi_id, work_items_dir)
    _save(data, path)
    return WorkItemResult(success=True, id=wi_id, path=str(path), status=current)


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

    elif cmd == "list":
        if len(args) != 1:
            print("Verwendung: python work_item.py list")
            sys.exit(1)
        print(json.dumps(list_work_items(), ensure_ascii=False))
        sys.exit(0)

    elif cmd == "resolve-file":
        if len(args) != 2:
            print("Verwendung: python work_item.py resolve-file <filename>")
            sys.exit(1)
        try:
            matches = resolve_repository_files(args[1])
        except ValueError as error:
            print(f"FEHLER: {error}")
            sys.exit(1)
        print(json.dumps(matches, ensure_ascii=False))
        sys.exit(0)

    elif cmd == "set-context-refs":
        if len(args) != 3:
            print(
                "Verwendung: python work_item.py set-context-refs "
                "WI-XXXX '[\"path/to/file\"]'"
            )
            sys.exit(1)
        try:
            context_refs = json.loads(args[2])
        except json.JSONDecodeError:
            print("FEHLER: context_refs ist kein gueltiges JSON")
            sys.exit(1)
        result = set_context_refs(args[1], context_refs)
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
