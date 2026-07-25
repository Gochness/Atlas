"""
Atlas Materialization Service v0.1

Verantwortung:
    Uebernahme eines bereits abgeschlossenen semantischen Urteils und
    Ueberfuehrung in den Wissensraum (THE LIBRARY/artifacts/).

Architekturvorgaben (MATERIALIZATION_GEMINI_REVIEW_001):
    B1 – Versionsbindung:   Materialisierung wird gegen base_commit geprueft.
                            Liegt HEAD vor oder nach base_commit, wird
                            abgebrochen.
    B2 – Persistenter Uebergang:
                            Vor Materialisierung wird ein Pending-Eintrag
                            unter THE VAULT/materialization_pending/ angelegt.
                            Er wird erst nach erfolgreichem Commit geloescht.
                            Faellt der Prozess zwischendurch aus, ist der
                            Zustand rekonstruierbar.
    B3 – Atomare Materialisierung:
                            Alle Artefakt-Dateien werden als einzelner
                            Git-Commit materialisiert. Schlaegt der Commit
                            fehl, werden alle erzeugten Dateien zurueckgerollt.
                            Es gibt keine partiellen Ergebnisse auf master.

Grenzen dieser Version:
    - Kein Judgment- oder Contradiction-Artefakt (folgen spaeter)
    - Keine automatische Zusammenfuehrung von Urteilen
    - merge workflow: Materialisierung setzt voraus, dass der PR bereits
      gemergt ist (master enthaelt die Submission)
"""

import os
import re
import subprocess
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SUBMISSIONS_DIR   = Path("THE WORKSHOPS/platform/submissions")
ARTIFACTS_DIR     = Path("THE LIBRARY/artifacts")
PENDING_DIR       = Path("THE VAULT/materialization_pending")
VALIDATOR         = Path("THE WORKSHOPS/platform/validator/validator.py")

REF_RE = re.compile(r"^ART-\d{4}$")


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class MaterializationResult:
    success: bool
    submission_id: Optional[str]    = None
    artifact_ref:  Optional[str]    = None
    artifact_path: Optional[str]    = None
    commit_sha:    Optional[str]    = None
    error:         Optional[str]    = None


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
    """Prueft ob base_commit Vorfahre des aktuellen HEAD ist."""
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
    path = _pending_path(entry.submission_id)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({
            "submission_id": entry.submission_id,
            "proposed_ref":  entry.proposed_ref,
            "base_commit":   entry.base_commit,
            "initiated_at":  entry.initiated_at,
            "artifact_path": entry.artifact_path,
        }, f, allow_unicode=True)


def _delete_pending(sid: str) -> None:
    path = _pending_path(sid)
    if path.exists():
        path.unlink()


def _artifact_content(data: dict, sid: str) -> str:
    """Erzeugt den Inhalt der materialisierten Artefakt-Datei."""
    cand = data["candidate"]
    sub  = data["submission"]
    lines = [
        f"# {cand['proposed_ref']}",
        "",
        f"**Materialisiert aus:** {sid}  ",
        f"**Basis-Commit:** {sub['base_commit']}  ",
        f"**Materialisiert am:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
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

def materialize(submission_id: str) -> MaterializationResult:
    """
    Materialisiert eine akzeptierte Submission.

    Ablauf:
        1. Submission laden und validieren
        2. B1: Versionsbindung pruefen
        3. B2: Pending-Eintrag anlegen
        4. Artefakt-Datei erzeugen
        5. B3: Atomarer Commit (oder vollstaendiges Rollback)
        6. Pending-Eintrag loeschen
    """

    # ------------------------------------------------------------------
    # 1. Submission laden
    # ------------------------------------------------------------------
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

    # Nur artifact/create wird in v0.1 unterstuetzt
    if sub["type"] != "artifact" or sub["action"] != "create":
        return MaterializationResult(
            success=False,
            submission_id=sid,
            error=f"v0.1 unterstuetzt nur type=artifact action=create (erhalten: {sub['type']}/{sub['action']})",
        )

    if not REF_RE.match(ref):
        return MaterializationResult(
            success=False,
            submission_id=sid,
            error=f"proposed_ref hat ungueltiges Format: {ref}",
        )

    # ------------------------------------------------------------------
    # 2. B1 – Versionsbindung
    # ------------------------------------------------------------------
    base_commit = str(sub["base_commit"])
    head        = _head_sha()

    if not _commit_reachable(base_commit):
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=(
                f"Versionsbindung verletzt: base_commit {base_commit} ist kein "
                f"Vorfahre des aktuellen HEAD {head}. "
                f"Bitte Zustand pruefen."
            ),
        )

    # Zieldatei
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS_DIR / f"{ref}.md"

    if artifact_path.exists():
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"Artefakt existiert bereits: {artifact_path}",
        )

    # ------------------------------------------------------------------
    # 3. B2 – Persistenter Uebergangszustand
    # ------------------------------------------------------------------
    pending = PendingEntry(
        submission_id=sid,
        proposed_ref=ref,
        base_commit=base_commit,
        initiated_at=datetime.now(timezone.utc).isoformat(),
        artifact_path=str(artifact_path),
    )
    _write_pending(pending)

    # ------------------------------------------------------------------
    # 4. Artefakt-Datei erzeugen
    # ------------------------------------------------------------------
    content = _artifact_content(data, sid)
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

    # ------------------------------------------------------------------
    # 5. B3 – Atomarer Commit (oder Rollback)
    # ------------------------------------------------------------------
    pending_file = _pending_path(sid)

    r_add = _run(f'git add "{artifact_path}" "{pending_file}"')
    if r_add.returncode != 0:
        # Rollback
        artifact_path.unlink(missing_ok=True)
        _delete_pending(sid)
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"git add fehlgeschlagen: {r_add.stderr}",
        )

    r_commit = _run(
        f'git commit -m "[{sid}] Materialize {ref}"'
    )
    if r_commit.returncode != 0:
        # Rollback
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

    # ------------------------------------------------------------------
    # 6. B2 abschliessen – Pending-Eintrag loeschen
    # ------------------------------------------------------------------
    # Pending-Eintrag wurde im Commit eingeschlossen; jetzt auf Disk loeschen
    # und diese Loeschung committen.
    _delete_pending(sid)
    pending_file_deleted = not pending_file.exists()

    if pending_file_deleted:
        r_del = _run(f'git add "{pending_file}"')
        _run(f'git commit -m "[{sid}] Clear materialization pending"')

    return MaterializationResult(
        success=True,
        submission_id=sid,
        artifact_ref=ref,
        artifact_path=str(artifact_path),
        commit_sha=sha,
    )


# ---------------------------------------------------------------------------
# Hilfsfunktion: offene Pending-Eintraege pruefen
# ---------------------------------------------------------------------------

def list_pending() -> list[PendingEntry]:
    """Gibt alle offenen Pending-Eintraege zurueck (fuer Recovery)."""
    if not PENDING_DIR.exists():
        return []
    entries = []
    for f in PENDING_DIR.glob("*.yaml"):
        with open(f, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        entries.append(PendingEntry(**d))
    return entries
