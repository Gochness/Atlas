"""
Atlas Submission Adapter v0.1

Nimmt bereits vollstaendig strukturierte Submission-Daten entgegen (ein
Dict im bestehenden Schema aus validator.py: {"submission": {...},
"candidate": {...}}), serialisiert sie in eine temporaere YAML-Datei und
uebergibt den Dateipfad unveraendert an submission_service.submit().

Kein neuer Submission-Pfad: validator.py, submission_service.py,
materialization_service.py und die CI bleiben vollstaendig unveraendert.
submit() kopiert den Dateiinhalt bereits selbst an den endgueltigen Ort
(THE WORKSHOPS/platform/submissions/<id>.yaml) - die temporaere Datei
dieses Adapters wird danach nicht mehr benoetigt und in jedem Fall
entfernt.

base_commit wird hier weder erzeugt noch interpretiert - es muss bereits
Bestandteil der uebergebenen Daten sein.
"""

import os
import tempfile
from pathlib import Path

import yaml

from submission_service import submit, SubmissionResult


def serialize_submission(data: dict) -> Path:
    """Schreibt strukturierte Submission-Daten in eine neue temporaere
    YAML-Datei und gibt deren Pfad zurueck. Reiner Serialisierungsschritt
    ohne Seiteneffekte auf Git oder den bestehenden Submission-Pfad."""
    fd, path_str = tempfile.mkstemp(prefix="atlas-submission-", suffix=".yaml")
    path = Path(path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def submit_structured(data: dict) -> SubmissionResult:
    """Serialisiert strukturierte Submission-Daten und uebergibt sie
    unveraendert an den bestehenden submission_service.submit()-Pfad.
    Die temporaere Datei wird danach in jedem Fall entfernt, unabhaengig
    davon ob submit() erfolgreich war."""
    path = serialize_submission(data)
    try:
        return submit(str(path))
    finally:
        path.unlink(missing_ok=True)
