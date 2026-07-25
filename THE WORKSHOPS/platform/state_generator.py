"""
Atlas State Generator v0.1

Erzeugt THE NORTH STAR/PROJECT_STATE.md deterministisch aus dem Repository.
Kein manuelles Pflegen mehr. Aufruf: python state_generator.py

Quellen:
    - THE WORKSHOPS/platform/submissions/     Submissions und Status
    - THE LIBRARY/artifacts/                  Materialisierte Artefakte
    - THE VAULT/WARP/                         Letzter WARP-Eintrag
    - THE VAULT/work_items/                   Work Items (Absicht, ART-0007)
    - git log                                 Letzte Commits
    - gh pr list                              Offene PRs (optional)

Grundlage: ART-0006 – PROJECT_STATE.md ist eine erzeugte Projektion,
keine primaere Quelle der Wahrheit.

Work Items (ART-0007): Absicht ist nicht aus Repository-Ereignissen
ableitbar. work_item.py kennt aktuell die Statuswerte open, completed
und abandoned - keinen expliziten Uebergang zu in_progress. "Aktive
Work Items (status: in_progress)" und die daraus abgeleiteten
Teilnehmer sind daher mit dem heutigen Befehlsumfang immer leer; die
Kategorie ist bewusst literal gegen den Statuswert geprueft, nicht als
Alias fuer open behandelt.
"""

import subprocess
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

SUBMISSIONS_DIR  = Path("THE WORKSHOPS/platform/submissions")
ARTIFACTS_DIR    = Path("THE LIBRARY/artifacts")
WARP_DIR         = Path("THE VAULT/WARP")
WORK_ITEMS_DIR   = Path("THE VAULT/work_items")
OUTPUT           = Path("THE NORTH STAR/PROJECT_STATE.md")

WI_STATUS_OPEN       = "open"
WI_STATUS_IN_PROGRESS = "in_progress"
WI_STATUS_CLOSED     = {"completed", "abandoned"}


def _run(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return r.stdout.strip()


def _head_sha() -> str:
    return _run("git rev-parse HEAD")


def _last_commits(n: int = 10) -> list[str]:
    r = subprocess.run(
        ["git", "log", "--oneline", f"-{n}"],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    return r.stdout.strip().splitlines() if r.stdout.strip() else []


def _open_prs() -> list[str]:
    r = subprocess.run(
        ["gh", "pr", "list", "--state", "open",
         "--json", "number,title",
         "--jq", ".[].title"],
        text=True, capture_output=True, encoding="utf-8"
    )
    return r.stdout.strip().splitlines() if r.stdout.strip() else []


def _load_submissions() -> list[dict]:
    if not SUBMISSIONS_DIR.exists():
        return []
    submissions = []
    for f in sorted(SUBMISSIONS_DIR.glob("*.yaml")):
        if "example" in f.name:
            continue
        try:
            with open(f, encoding="utf-8-sig") as fh:
                data = yaml.safe_load(fh)
            sub  = data.get("submission", {})
            cand = data.get("candidate", {})
            submissions.append({
                "id":     sub.get("id", f.stem),
                "ref":    cand.get("proposed_ref", "?"),
                "type":   sub.get("type", "?"),
                "action": sub.get("action", "?"),
            })
        except Exception:
            pass
    return submissions


def _load_artifacts() -> list[dict]:
    if not ARTIFACTS_DIR.exists():
        return []
    artifacts = []
    for f in sorted(ARTIFACTS_DIR.glob("*.md")):
        artifacts.append({"ref": f.stem, "file": f.name})
    return artifacts


def _materialized_refs() -> set[str]:
    return {a["ref"] for a in _load_artifacts()}


def _latest_warp() -> str:
    if not WARP_DIR.exists():
        return "(kein WARP-Eintrag gefunden)"
    entries = sorted(WARP_DIR.glob("WARP-*.md"), reverse=True)
    if not entries:
        return "(kein WARP-Eintrag gefunden)"
    return entries[0].name


def _merged_submission_ids() -> set[str]:
    r = subprocess.run(
        ["gh", "pr", "list", "--state", "merged",
         "--json", "title",
         "--jq", ".[].title"],
        text=True, capture_output=True, encoding="utf-8"
    )
    ids = set()
    for line in r.stdout.splitlines():
        if "[" in line and "]" in line:
            sid = line[line.index("[")+1:line.index("]")]
            ids.add(sid)
    return ids


def _submission_status(sid: str, ref: str, materialized: set[str], merged: set[str]) -> str:
    if ref in materialized:
        return "materialisiert"
    if sid in merged:
        return "gemergt (nicht materialisiert)"
    return "eingereicht"


def _load_work_items(work_items_dir: Path = WORK_ITEMS_DIR) -> list[dict]:
    if not work_items_dir.exists():
        return []
    items = []
    for f in sorted(work_items_dir.glob("WI-*.yaml")):
        try:
            with open(f, encoding="utf-8-sig") as fh:
                data = yaml.safe_load(fh)
            if data:
                items.append(data)
        except Exception:
            pass
    return items


def _work_item_sections(work_items: list[dict]) -> list[str]:
    """
    Baut die Markdown-Abschnitte fuer Work Items.
    Reine Funktion (keine Dateizugriffe) - direkt testbar mit synthetischen Daten.
    """
    open_items   = [w for w in work_items if w.get("status") == WI_STATUS_OPEN]
    active_items = [w for w in work_items if w.get("status") == WI_STATUS_IN_PROGRESS]
    closed_items = [w for w in work_items if w.get("status") in WI_STATUS_CLOSED]
    participants = sorted({w["created_by"] for w in active_items if w.get("created_by")})

    def _row(w: dict) -> str:
        return f"- {w.get('id', '?')}  [{w.get('status', '?')}]  {w.get('created_by', '?')}: {w.get('intent', '')}"

    lines = ["", "## Work Items – Offen", ""]
    lines += [_row(w) for w in open_items] if open_items else ["(keine offenen Work Items)"]

    lines += ["", "## Work Items – Aktiv (status: in_progress)", ""]
    lines += [_row(w) for w in active_items] if active_items else ["(keine aktiven Work Items)"]

    lines += ["", "## Work Items – Abgeschlossen", ""]
    lines += [_row(w) for w in closed_items] if closed_items else ["(keine abgeschlossenen Work Items)"]

    lines += ["", "## Aktuelle Teilnehmer", ""]
    lines += [f"- {p}" for p in participants] if participants else ["(keine aktiven Teilnehmer)"]

    lines += ["", "## Activity Stream", ""]
    events = sorted(work_items, key=lambda w: w.get("created_at", ""), reverse=True)
    if events:
        for w in events:
            lines.append(
                f"- {w.get('created_at', '?')}  {w.get('id', '?')}  [{w.get('status', '?')}]  "
                f"{w.get('created_by', '?')}: {w.get('intent', '')}"
            )
    else:
        lines.append("(keine Work-Item-Ereignisse)")

    return lines


def generate() -> str:
    now        = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    head       = _head_sha()
    commits    = _last_commits(10)
    open_prs   = _open_prs()
    submissions = _load_submissions()
    artifacts  = _load_artifacts()
    materialized = _materialized_refs()
    merged     = _merged_submission_ids()
    latest_warp = _latest_warp()
    work_items = _load_work_items()

    lines = [
        "# PROJECT_STATE",
        "",
        f"> Automatisch erzeugt durch state_generator.py – {now}",
        f"> HEAD: {head}",
        f"> Quelle: ART-0006 – PROJECT_STATE ist eine Projektion, keine primaere Quelle",
        "",
        "---",
        "",
        "## Platform Status",
        "",
        f"Letzter WARP: {latest_warp}",
        "",
        "## Submissions",
        "",
    ]

    if submissions:
        for s in submissions:
            status = _submission_status(s["id"], s["ref"], materialized, merged)
            lines.append(f"- {s['id']}  →  {s['ref']}  [{status}]")
    else:
        lines.append("(keine Submissions gefunden)")

    lines += [
        "",
        "## Materialisierte Artefakte",
        "",
    ]

    if artifacts:
        for a in artifacts:
            lines.append(f"- {a['ref']}")
    else:
        lines.append("(keine Artefakte gefunden)")

    lines += [
        "",
        "## Offene Pull Requests",
        "",
    ]

    if open_prs:
        for pr in open_prs:
            lines.append(f"- {pr}")
    else:
        lines.append("(keine offenen PRs)")

    lines += [
        "",
        "## Letzte Commits",
        "",
    ]

    for c in commits:
        lines.append(f"- {c}")

    lines += _work_item_sections(work_items)

    lines += ["", "---", ""]

    return "\n".join(lines)


def main():
    print("Atlas State Generator v0.1")
    print(f"HEAD: {_head_sha()}")
    content = generate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Geschrieben: {OUTPUT}")
    print()
    sys.stdout.buffer.write(content[:800].encode("utf-8"))


if __name__ == "__main__":
    main()
