"""
Atlas Materialization Service v0.4

Neu in v0.4:
    - Test-Modus (test_mode=True): materialize() schreibt Artefakt- und
      Pending-Dateien wie gewohnt, fuehrt aber kein `git add` / `git commit`
      aus. Dadurch lassen sich alle Pruefpfade (B1 Versionsbindung, Ref-Format,
      target-Anforderungen, "existiert bereits") isoliert testen, ohne die
      reale Git-Historie zu veraendern.
    - Verzeichnisse sind ueber MaterializationConfig konfigurierbar
      (submissions_dir, artifacts_dir, pending_dir) statt hart codiert.
      Der Produktionspfad bleibt unveraendert der Default.

Neu in v0.3:
    - Contradiction-Artefakte (type=contradiction) werden als CONT-XXXX.md
      materialisiert. Erfordert mindestens zwei target-Eintraege.

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
                            Im Test-Modus entfaellt B3 (kein Commit), B1 und B2
                            werden unveraendert geprueft.
"""

import re
import subprocess
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SUBMISSIONS_DIR = Path("THE WORKSHOPS/platform/submissions")
ARTIFACTS_DIR   = Path("THE LIBRARY/artifacts")
PENDING_DIR     = Path("THE VAULT/materialization_pending")

ART_REF_RE  = re.compile(r"^ART-\d{4}$")
JUDG_REF_RE = re.compile(r"^JUDG-\d{4}$")
CONT_REF_RE = re.compile(r"^CONT-\d{4}$")


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

@dataclass
class MaterializationConfig:
    submissions_dir: Path = SUBMISSIONS_DIR
    artifacts_dir:   Path = ARTIFACTS_DIR
    pending_dir:     Path = PENDING_DIR
    test_mode:       bool = False  # True: kein git add / git commit


DEFAULT_CONFIG = MaterializationConfig()


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


def _load_submission(sid: str, config: MaterializationConfig = DEFAULT_CONFIG) -> Optional[dict]:
    path = config.submissions_dir / f"{sid}.yaml"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pending_path(sid: str, config: MaterializationConfig = DEFAULT_CONFIG) -> Path:
    return config.pending_dir / f"{sid}.yaml"


def _write_pending(entry: PendingEntry, config: MaterializationConfig = DEFAULT_CONFIG) -> None:
    config.pending_dir.mkdir(parents=True, exist_ok=True)
    with open(_pending_path(entry.submission_id, config), "w", encoding="utf-8") as f:
        yaml.dump({
            "submission_id": entry.submission_id,
            "proposed_ref":  entry.proposed_ref,
            "base_commit":   entry.base_commit,
            "initiated_at":  entry.initiated_at,
            "artifact_path": entry.artifact_path,
        }, f, allow_unicode=True)


def _delete_pending(sid: str, config: MaterializationConfig = DEFAULT_CONFIG) -> None:
    p = _pending_path(sid, config)
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


# ---------------------------------------------------------------------------
# Kern: Materialisierung
# ---------------------------------------------------------------------------

def _do_materialize(
    sid: str,
    ref: str,
    content: str,
    base_commit: str,
    config: MaterializationConfig = DEFAULT_CONFIG,
) -> MaterializationResult:
    """
    Gemeinsamer Materialisierungskern fuer artifact, judgment und contradiction.
    B1, B2 und (ausser im Test-Modus) B3 sind hier implementiert.
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

    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = config.artifacts_dir / f"{ref}.md"

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
    _write_pending(pending, config)

    # Datei schreiben
    try:
        artifact_path.write_text(content, encoding="utf-8")
    except OSError as e:
        _delete_pending(sid, config)
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"Datei konnte nicht geschrieben werden: {e}",
        )

    # Test-Modus: kein Commit, Pending direkt aufloesen
    if config.test_mode:
        _delete_pending(sid, config)
        return MaterializationResult(
            success=True,
            submission_id=sid,
            artifact_ref=ref,
            artifact_path=str(artifact_path),
            commit_sha=None,
        )

    # B3 – Atomarer Commit
    pending_file = _pending_path(sid, config)
    r_add = _run(f'git add "{artifact_path}" "{pending_file}"')
    if r_add.returncode != 0:
        artifact_path.unlink(missing_ok=True)
        _delete_pending(sid, config)
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
        _delete_pending(sid, config)
        return MaterializationResult(
            success=False,
            submission_id=sid,
            artifact_ref=ref,
            error=f"git commit fehlgeschlagen: {r_commit.stderr}",
        )

    # B2 abschliessen – Pending loeschen
    _delete_pending(sid, config)
    if not _pending_path(sid, config).exists():
        _run(f'git add "{pending_file}"')
        _run(f'git commit -m "[{sid}] Clear materialization pending"')

    return MaterializationResult(
        success=True,
        submission_id=sid,
        artifact_ref=ref,
        artifact_path=str(artifact_path),
        commit_sha=_head_sha(),
    )


def materialize(
    submission_id: str,
    config: MaterializationConfig = DEFAULT_CONFIG,
) -> MaterializationResult:
    data = _load_submission(submission_id, config)
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
            error=f"v0.4 unterstuetzt nur action=create (erhalten: {act})",
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

    return _do_materialize(sid, ref, content, str(sub["base_commit"]), config)


# ---------------------------------------------------------------------------
# Hilfsfunktion: Pending-Eintraege
# ---------------------------------------------------------------------------

def list_pending(config: MaterializationConfig = DEFAULT_CONFIG) -> list[PendingEntry]:
    if not config.pending_dir.exists():
        return []
    entries = []
    for f in config.pending_dir.glob("*.yaml"):
        with open(f, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        entries.append(PendingEntry(**d))
    return entries
