"""
Atlas Materialization Service v0.2

Neu in v0.2:
    - Judgment-Artefakte (type=judgment) werden als JUDG-XXXX.md materialisiert
    - target kann eine Liste oder ein einzelner Wert sein
    - Artefakt-Datei wird durch Urteil nicht veraendert

Architekturvorgaben (MATERIALIZATION_GEMINI_REVIEW_001):
    B1 – Versionsbindung:   base_commit muss Vorfahre von HEAD sein.
    B2 – Persistenter Uebergang:
                            Pending-Eintrag unter THE VAULT/materialization_pending/
                            bleibt bis nach erfolgreichem Commit bestehen.
    B3 – Atomare Materialisierung:
                            Alle Dateien eines Vorgangs in einem einzigen Commit.
                            Schlaegt der Commit fehl, vollstaendiges Rollback.
"""

import os
import re
import subprocess
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SUBMISSIONS_DIR = Path("THE WORKSHOPS/platform/submissions")
ARTIFACTS_DIR   = Path("THE LIBRARY/artifacts")
PENDING_DIR     = Path("THE VAULT/materialization_pending")

ART_REF_RE  = re.compile(r"^ART-\d{4}$")
JUDG_REF_RE = re.compile(r"^JUDG-\d{4}$")


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class MaterializationResult:
    success:       bool
    submission_id: Optional[str] = None
    artifact_ref:  Optional[str] = None
    artifact_path: Optional[str] = None
    commit_sha:    Optional[str] = None
    error:         Optional[str] = None


@dataclass
class PendingEntry:
    submission_id: str
    proposed_ref:  str
    base_commit:   str
    initiated_at:  str
    artifact_path: str


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, text=True, capture_output=True)


def _head_sha() -> str:
    return _run("git rev-parse HEAD").stdout.strip()


def _commit_reachable(commit: str) -> bool:
    r = _run(f"git merge-base --is-ancestor {commit} HEAD")
    return r.returncode == 0


def _load_submission(sid: str) -> Optional[dict]:
    path = SUBMISSIONS_DIR / f"{sid}.yaml"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pending_path(sid: str) -> Path:
    return PENDING_DIR / f"{sid}.yaml"


def _write_pending(entry: PendingEntry) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    with open(_pending_path(entry.submission_id), "w", encoding="utf-8") as f:
        yaml.dump({
            "submission_id": entry.submission_id,
            "proposed_ref":  entry.proposed_ref,
            "base_commit":   entry.base_commit,
            "initiated_at":  entry.initiated_at,
            "artifact_path": entry.artifact_path,
        }, f, allow_unicode=True)


def _delete_pending(sid: str) -> None:
    p = _pending_path(sid)
    if p.exists():
        p.unlink()


def _normalize_target(target) -> list[str]:
    """target kann str, list oder None sein."""
    if target is None:
        return []
    if isinstance(target, list):
        return [str(t).strip() for t in target]
    return [str(target).strip()]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Inhalts-Generatoren
# ---------------------------------------------------------------------------

def _artifact_content(data: dict, sid: str) -> str:
    cand = data["candidate"]
    sub  = data["submission"]
    lines = [
        f"# {cand['proposed_ref']}",
        "",
        f"**Materialisiert aus:** {sid}  ",
        f"**Basis-Commit:** {sub['base_commit']}  ",
        f"**Materialisiert am:** {_today()}",
        "",
        "---",
        "",
        "## Behauptung",
        "",
        str(cand["claim"]).strip(),
        "",
        "## Beobachtungsbasis",
        "",
        str(cand["basis"]).strip(),
        "",
        "## Gegenversuche",
        "",
        str(cand["counter"]).strip(),
        "",
        "## Offene Punkte",
        "",
        str(cand["open"]).strip(),
    ]
    return "\n".join(lines) + "\n"


def _judgment_content(data: dict, sid: str) -> str:
    cand    = data["candidate"]
    sub     = data["submission"]
    targets = _normalize_target(sub.get("target"))
    target_str = ", ".join(targets) if targets else "(kein Ziel angegeben)"
    lines = [
        f"# {cand['proposed_ref']}",
        "",
        f"**Materialisiert aus:** {sid}  ",
        f"**Basis-Commit:** {sub['base_commit']}  ",
        f"**Materialisiert am:** {_today()}",
        f"**Ziel:** {target_str}",
        "",
        "---",
        "",
        "## Behauptung",
        "",
        str(cand["claim"]).strip(),
        "",
        "## Beobachtungsbasis",
        "",
        str(cand["basis"]).strip(),
        "",
        "## Gegenversuche",
        "",
        str(cand["counter"]).strip(),
        "",
        "## Offene Punkte",
        "",
        str(cand["open"]).strip(),
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Kern: Materialisierung
# ---------------------------------------------------------------------------

def _do_materialize(
    sid: str,
    ref: str,
    content: str,
    base_commit: str,
) -> MaterializationResult:
    """
    Gemeinsamer Materialisierungskern fuer artifact und judgment.
    B1, B2 und B3 sind hier implementiert.
    """

    # B1 – Versionsbindung
    head = _head_sha()
    if not _commit_reachable(base_commit):
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=(
                f"Versionsbindung verletzt: base_commit {base_commit} ist kein "
                f"Vorfahre des aktuellen HEAD {head}."
            ),
        )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS_DIR / f"{ref}.md"

    if artifact_path.exists():
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"Artefakt existiert bereits: {artifact_path}",
        )

    # B2 – Pending anlegen
    pending = PendingEntry(
        submission_id=sid,
        proposed_ref=ref,
        base_commit=base_commit,
        initiated_at=datetime.now(timezone.utc).isoformat(),
        artifact_path=str(artifact_path),
    )
    _write_pending(pending)

    # Datei schreiben
    try:
        artifact_path.write_text(content, encoding="utf-8")
    except OSError as e:
        _delete_pending(sid)
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"Datei konnte nicht geschrieben werden: {e}",
        )

    # B3 – Atomarer Commit
    pending_file = _pending_path(sid)
    r_add = _run(f'git add "{artifact_path}" "{pending_file}"')
    if r_add.returncode != 0:
        artifact_path.unlink(missing_ok=True)
        _delete_pending(sid)
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"git add fehlgeschlagen: {r_add.stderr}",
        )

    r_commit = _run(f'git commit -m "[{sid}] Materialize {ref}"')
    if r_commit.returncode != 0:
        _run("git reset HEAD")
        artifact_path.unlink(missing_ok=True)
        _delete_pending(sid)
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"git commit fehlgeschlagen: {r_commit.stderr}",
        )

    sha = _head_sha()

    # B2 abschliessen – Pending loeschen
    _delete_pending(sid)
    if not _pending_path(sid).exists():
        _run(f'git add "{pending_file}"')
        _run(f'git commit -m "[{sid}] Clear materialization pending"')

    return MaterializationResult(
        success=True,
        submission_id=sid,
        artifact_ref=ref,
        artifact_path=str(artifact_path),
        commit_sha=_head_sha(),
    )


def materialize(submission_id: str) -> MaterializationResult:
    data = _load_submission(submission_id)
    if data is None:
        return MaterializationResult(
            success=False,
            submission_id=submission_id,
            error=f"Submission nicht gefunden: {submission_id}",
        )

    sub  = data["submission"]
    cand = data["candidate"]
    sid  = sub["id"]
    ref  = cand["proposed_ref"]
    typ  = sub["type"]
    act  = sub["action"]

    if act != "create":
        return MaterializationResult(
            success=False,
            submission_id=sid,
            error=f"v0.2 unterstuetzt nur action=create (erhalten: {act})",
        )

    if typ == "artifact":
        if not ART_REF_RE.match(ref):
            return MaterializationResult(
                success=False,
                submission_id=sid,
                error=f"proposed_ref hat ungueltiges Format fuer artifact: {ref}",
            )
        content = _artifact_content(data, sid)

    elif typ == "judgment":
        if not JUDG_REF_RE.match(ref):
            return MaterializationResult(
                success=False,
                submission_id=sid,
                error=f"proposed_ref hat ungueltiges Format fuer judgment: {ref} (erwartet JUDG-XXXX)",
            )
        targets = _normalize_target(sub.get("target"))
        if not targets:
            return MaterializationResult(
                success=False,
                submission_id=sid,
                error="judgment erfordert mindestens ein target",
            )
        content = _judgment_content(data, sid)

    elif typ == "contradiction":
        if not CONT_REF_RE.match(ref):
            return MaterializationResult(
                success=False,
                submission_id=sid,
                error=f"proposed_ref hat ungueltiges Format fuer contradiction: {ref} (erwartet CONT-XXXX)",
            )
        targets = _normalize_target(sub.get("target"))
        if len(targets) < 2:
            return MaterializationResult(
                success=False,
                submission_id=sid,
                error="contradiction erfordert mindestens zwei targets",
            )
        content = _contradiction_content(data, sid)

    else:
        return MaterializationResult(
            success=False,
            submission_id=sid,
            error=f"Typ '{typ}' wird noch nicht unterstuetzt",
        )

    return _do_materialize(sid, ref, content, str(sub["base_commit"]))


# ---------------------------------------------------------------------------
# Hilfsfunktion: Pending-Eintraege
# ---------------------------------------------------------------------------

def list_pending() -> list[PendingEntry]:
    if not PENDING_DIR.exists():
        return []
    entries = []
    for f in PENDING_DIR.glob("*.yaml"):
        with open(f, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        entries.append(PendingEntry(**d))
    return entries


# ---------------------------------------------------------------------------
# Contradiction-Inhalts-Generator (v0.3)
# ---------------------------------------------------------------------------

CONT_REF_RE = re.compile(r"^CONT-\d{4}$")


def _contradiction_content(data: dict, sid: str) -> str:
    cand    = data["candidate"]
    sub     = data["submission"]
    targets = _normalize_target(sub.get("target"))
    target_str = ", ".join(targets) if targets else "(kein Ziel angegeben)"
    lines = [
        f"# {cand['proposed_ref']}",
        "",
        f"**Materialisiert aus:** {sid}  ",
        f"**Basis-Commit:** {sub['base_commit']}  ",
        f"**Materialisiert am:** {_today()}",
        f"**Zwischen:** {target_str}",
        "",
        "---",
        "",
        "## Behauptung",
        "",
        str(cand["claim"]).strip(),
        "",
        "## Beobachtungsbasis",
        "",
        str(cand["basis"]).strip(),
        "",
        "## Gegenversuche",
        "",
        str(cand["counter"]).strip(),
        "",
        "## Offene Punkte",
        "",
        str(cand["open"]).strip(),
    ]
    return "\n".join(lines) + "\n"
