"""Persistenter technischer Betriebszustand fuer independent-Laeufe.

Die Daten liegen bewusst ausserhalb des Atlas-Repositories und damit
ausserhalb des Atlas-Wissensraums. Sie sind keine WorkSteps und kein
fachliches Atlas-Wissen.
"""

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")

PARTICIPANT_STATUSES = {
    "pending",
    "working",
    "completed_pending",
    "failed",
    "published",
    "publication_failed",
}
RUN_STATUSES = {
    "running",
    "incomplete",
    "publishing",
    "completed",
    "publication_failed",
    "partially_published",
}


def default_runs_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path(tempfile.gettempdir())
    return base / "Atlas" / "independent-runs"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(run_id: str, runs_dir: Path) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Ungueltige run_id")
    return runs_dir / f"{run_id}.json"


def create_run(
    work_item: dict,
    participants: list[str],
    starting_snapshot: list[dict],
    runs_dir: Path | None = None,
) -> dict:
    timestamp = _now()
    run = {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid.uuid4().hex,
        "work_item_id": work_item["id"],
        "mode": "independent",
        "participants": list(participants),
        "status": "running",
        "created_at": timestamp,
        "updated_at": timestamp,
        "original_input": {
            "intent": work_item.get("intent"),
            "context_refs": list(work_item.get("context_refs") or []),
            "starting_snapshot": [
                dict(work_step) for work_step in starting_snapshot
            ],
        },
        "participant_states": [
            {
                "provider": provider,
                "status": "pending",
                "participant_id": None,
                "content": None,
                "error": None,
                "work_step_id": None,
                "attempt_count": 0,
            }
            for provider in participants
        ],
    }
    save_run(run, runs_dir)
    return run


def save_run(run: dict, runs_dir: Path | None = None) -> Path:
    validate_run(run)
    directory = runs_dir or default_runs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    run["updated_at"] = _now()
    path = _path(run["run_id"], directory)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(run, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_run(run_id: str, runs_dir: Path | None = None) -> dict:
    directory = runs_dir or default_runs_dir()
    path = _path(run_id, directory)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"IndependentRun nicht gefunden: {run_id}") from error
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(
            f"IndependentRun kann nicht gelesen werden: {run_id}"
        ) from error
    data = _upgrade_legacy_run(data)
    validate_run(data)
    if data["run_id"] != run_id:
        raise ValueError("IndependentRun enthaelt eine abweichende run_id")
    return data


def find_latest_incomplete_run(
    work_item_id: str,
    runs_dir: Path | None = None,
) -> dict | None:
    directory = runs_dir or default_runs_dir()
    if not directory.exists():
        return None
    candidates = []
    for path in directory.glob("*.json"):
        try:
            run = load_run(path.stem, directory)
        except ValueError:
            continue
        if (
            run["work_item_id"] == work_item_id
            and run["status"] == "incomplete"
        ):
            candidates.append(run)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda run: (run["updated_at"], run["run_id"]),
    )


def _upgrade_legacy_run(data: object) -> object:
    if not isinstance(data, dict):
        return data
    if data.get("schema_version") != LEGACY_SCHEMA_VERSION:
        return data
    states = data.get("participant_states")
    if not isinstance(states, list):
        return data
    upgraded = {
        **data,
        "schema_version": SCHEMA_VERSION,
        "participant_states": [
            {
                **state,
                "attempt_count": (
                    0
                    if isinstance(state, dict)
                    and state.get("status") == "pending"
                    else 1
                ),
            }
            if isinstance(state, dict)
            else state
            for state in states
        ],
    }
    return upgraded


def participant_state(run: dict, provider: str) -> dict:
    matches = [
        state
        for state in run["participant_states"]
        if state["provider"] == provider
    ]
    if len(matches) != 1:
        raise ValueError(f"Teilnehmerzustand nicht eindeutig: {provider}")
    return matches[0]


def validate_run(run: object) -> None:
    if not isinstance(run, dict):
        raise ValueError("IndependentRun muss ein Objekt sein")
    if run.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unbekannte IndependentRun-Schemaversion")
    if not isinstance(run.get("run_id"), str) or not RUN_ID_RE.fullmatch(
        run["run_id"]
    ):
        raise ValueError("Ungueltige run_id")
    if not isinstance(run.get("work_item_id"), str) or not run["work_item_id"]:
        raise ValueError("IndependentRun benoetigt work_item_id")
    if run.get("mode") != "independent":
        raise ValueError("IndependentRun besitzt ungueltigen Modus")
    participants = run.get("participants")
    if (
        not isinstance(participants, list)
        or not participants
        or any(not isinstance(value, str) or not value for value in participants)
        or len(set(participants)) != len(participants)
    ):
        raise ValueError("IndependentRun besitzt ungueltige Teilnehmer")
    if run.get("status") not in RUN_STATUSES:
        raise ValueError("IndependentRun besitzt ungueltigen Status")
    if not isinstance(run.get("created_at"), str) or not isinstance(
        run.get("updated_at"), str
    ):
        raise ValueError("IndependentRun benoetigt Zeitstempel")
    original_input = run.get("original_input")
    if (
        not isinstance(original_input, dict)
        or (
            original_input.get("intent") is not None
            and not isinstance(original_input.get("intent"), str)
        )
        or not isinstance(original_input.get("context_refs"), list)
        or not isinstance(original_input.get("starting_snapshot"), list)
    ):
        raise ValueError("IndependentRun besitzt keinen Ausgangssnapshot")
    states = run.get("participant_states")
    if not isinstance(states, list) or [
        state.get("provider") if isinstance(state, dict) else None
        for state in states
    ] != participants:
        raise ValueError("Teilnehmerzustaende entsprechen nicht der Reihenfolge")
    if any(state.get("status") not in PARTICIPANT_STATUSES for state in states):
        raise ValueError("IndependentRun besitzt ungueltigen Teilnehmerstatus")
    optional_text_fields = (
        "participant_id",
        "content",
        "error",
        "work_step_id",
    )
    if any(
        field not in state
        or (
            state[field] is not None
            and not isinstance(state[field], str)
        )
        for state in states
        for field in optional_text_fields
    ):
        raise ValueError("IndependentRun besitzt ungueltige Teilnehmerdaten")
    if any(
        not isinstance(state.get("attempt_count"), int)
        or isinstance(state.get("attempt_count"), bool)
        or state["attempt_count"] < 0
        for state in states
    ):
        raise ValueError("IndependentRun besitzt ungueltigen Versuchszähler")
    for state in states:
        if state["status"] in {
            "completed_pending",
            "published",
            "publication_failed",
        } and (
            not state["participant_id"]
            or not state["content"]
        ):
            raise ValueError(
                "Abgeschlossener Teilnehmer besitzt kein Ergebnis"
            )
        if state["status"] == "failed" and not state["error"]:
            raise ValueError(
                "Fehlgeschlagener Teilnehmer besitzt keine Fehlerursache"
            )
        if state["status"] == "published" and not state["work_step_id"]:
            raise ValueError(
                "Publizierter Teilnehmer besitzt keine WorkStep-ID"
            )
        if state["status"] == "publication_failed" and not state["error"]:
            raise ValueError(
                "Publikationsfehler besitzt keine Fehlerursache"
            )
