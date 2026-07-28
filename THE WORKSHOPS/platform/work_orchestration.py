"""
Atlas Orchestrierung V1.

Orchestriert die drei Arbeitsweisen ueber die bestehenden
Untersuchungszyklen in openai_work_step.py, anthropic_work_step.py und
gemini_work_step.py. Die Modelladapter und ihre Atlas-internen
Such-/Lesewerkzeuge bleiben die einzige Untersuchungslogik.

Verwendung:
    python work_orchestration.py run \
        --work-item WI-XXXX \
        --mode single|independent|refutation \
        --participants openai[,anthropic,gemini] \
        [--status-file <path>]
"""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import anthropic_work_step
import gemini_work_step
import independent_run
import openai_work_step
from work_step import list_for_work_item, publish


SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini")
SUPPORTED_MODES = ("single", "independent", "refutation")

REFUTATION_TASK_Y = (
    "Versuche den Befund von X zu widerlegen. "
    "Untersuche selbststaendig den Atlas-Wissensraum. "
    "Suche insbesondere nach Gegenbelegen, widersprechenden Grundlagen, "
    "unbelegten Annahmen und Grenzen der Aussagen von X. "
    "Bestaetige oder verbessere X nicht lediglich. "
    "Kann eine fuer die Pruefung notwendige Information innerhalb Atlas "
    "nicht festgestellt werden, MUSS diese Informationsluecke ausdruecklich "
    "benannt werden."
)

REFUTATION_TASK_Z = (
    "Versuche erneut, den nach X und Y noch tragfaehigen Stand zu widerlegen. "
    "Untersuche dafuer selbststaendig den Atlas-Wissensraum. "
    "Pruefe sowohl die Grundlagen von X als auch die Gegenposition von Y. "
    "Suche nach Gegenbelegen, Widerspruechen, unbelegten Annahmen und Grenzen. "
    "Du bist kein Schiedsrichter und musst keinen Konsens herstellen. "
    "Bleiben Widersprueche oder Informationsluecken bestehen, muessen sie "
    "sichtbar bleiben."
)

_ADAPTERS = {
    "openai": openai_work_step,
    "anthropic": anthropic_work_step,
    "gemini": gemini_work_step,
}

StatusCallback = Callable[[dict], None]
STATUS_REPLACE_ATTEMPTS = 20
STATUS_REPLACE_RETRY_SECONDS = 0.005


def validate_configuration(mode: str, participants: list[str]) -> None:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unbekannte Arbeitsweise: {mode}")
    if any(provider not in SUPPORTED_PROVIDERS for provider in participants):
        invalid = [p for p in participants if p not in SUPPORTED_PROVIDERS]
        raise ValueError(f"Unbekannte Teilnehmer: {', '.join(invalid)}")
    if len(set(participants)) != len(participants):
        raise ValueError("Teilnehmer duerfen nicht doppelt ausgewaehlt werden")
    if mode == "single" and len(participants) != 1:
        raise ValueError("Einzeluntersuchung erfordert genau einen Teilnehmer")
    if mode == "independent" and len(participants) < 2:
        raise ValueError(
            "Unabhaengige Untersuchung erfordert mindestens zwei Teilnehmer"
        )
    if mode == "refutation" and len(participants) != 3:
        raise ValueError("Widerlegungspruefung erfordert genau drei Teilnehmer")


def _new_work_step(
    provider: str,
    work_item_id: str,
    work_steps_snapshot: list[dict],
    additional_task: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    before_ids = {
        step["id"] for step in list_for_work_item(work_item_id)
    }
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = _ADAPTERS[provider].generate(
            work_item_id,
            work_steps_snapshot=work_steps_snapshot,
            additional_task=additional_task,
        )

    if exit_code != 0:
        detail = stderr.getvalue().strip() or stdout.getvalue().strip()
        return None, detail or f"{provider} ist fehlgeschlagen"

    created = [
        step
        for step in list_for_work_item(work_item_id)
        if step["id"] not in before_ids
    ]
    if len(created) != 1:
        return None, (
            f"{provider} meldete Erfolg, erzeugte aber "
            f"{len(created)} neue WorkSteps"
        )
    return created[0], None


def _generate_content(
    provider: str,
    work_item_id: str,
    work_steps_snapshot: list[dict],
) -> tuple[Optional[dict], Optional[str]]:
    try:
        participant_id, content = _ADAPTERS[provider].generate_content(
            work_item_id,
            work_steps_snapshot=work_steps_snapshot,
        )
    except (ValueError, RuntimeError) as error:
        return None, f"FEHLER: {error}"
    return {
        "provider": provider,
        "participant_id": participant_id,
        "content": content,
    }, None


def run(
    work_item_id: str,
    mode: str,
    participants: list[str],
    status_callback: Optional[StatusCallback] = None,
) -> dict:
    validate_configuration(mode, participants)
    starting_snapshot = list_for_work_item(work_item_id)
    snapshot_ids = [step["id"] for step in starting_snapshot]
    results: list[dict] = []
    persistent_run = None
    run_id = None

    if mode == "independent":
        work_item = openai_work_step._read_work_item(work_item_id)
        persistent_run = independent_run.create_run(
            {
                "id": work_item_id,
                "intent": work_item.get("intent"),
                "context_refs": work_item.get("context_refs", []),
            },
            participants,
            starting_snapshot,
        )
        run_id = persistent_run["run_id"]

    def report(state: str, phase: str, message: str) -> None:
        if status_callback:
            status = {
                "state": state,
                "mode": mode,
                "phase": phase,
                "message": message,
                "work_item_id": work_item_id,
                "participants": participants,
                "starting_snapshot_ids": snapshot_ids,
                "results": results,
            }
            if run_id:
                status["run_id"] = run_id
            status_callback(status)

    report("working", "start", "Arbeit wird gestartet")

    if mode == "single":
        provider = participants[0]
        report("working", "single", f"{provider} untersucht")
        step, error = _new_work_step(
            provider,
            work_item_id,
            starting_snapshot,
        )
        if error:
            report("failed", "single", error)
            return _result(
                False, mode, participants, snapshot_ids, results, error
            )
        results.append(_participant_result(provider, "single", step))

    elif mode == "independent":
        failures = []
        pending_publications = []
        for provider in participants:
            participant_state = independent_run.participant_state(
                persistent_run, provider
            )
            participant_state["status"] = "working"
            participant_state["attempt_count"] += 1
            independent_run.save_run(persistent_run)
            report(
                "working",
                "independent",
                f"{provider} untersucht den gemeinsamen Ausgangsstand",
            )
            generated, error = _generate_content(
                provider,
                work_item_id,
                starting_snapshot,
            )
            if error:
                participant_state["status"] = "failed"
                participant_state["error"] = error
                independent_run.save_run(persistent_run)
                failure = {
                    "provider": provider,
                    "phase": "independent",
                    "status": "failed",
                    "error": error,
                }
                results.append(failure)
                failures.append(failure)
                continue
            participant_result = {
                "provider": provider,
                "phase": "independent",
                "status": "completed_pending",
                "participant_id": generated["participant_id"],
            }
            participant_state["status"] = "completed_pending"
            participant_state["participant_id"] = generated["participant_id"]
            participant_state["content"] = generated["content"]
            participant_state["error"] = None
            independent_run.save_run(persistent_run)
            results.append(participant_result)
            pending_publications.append({
                **generated,
                "result": participant_result,
            })

        if failures:
            persistent_run["status"] = "incomplete"
            independent_run.save_run(persistent_run)
            error = (
                f"{len(failures)} von {len(participants)} Teilnehmern "
                "sind fehlgeschlagen; keine Ergebnisse wurden veroeffentlicht"
            )
            report("failed", "independent", error)
            return _result(
                False,
                mode,
                participants,
                snapshot_ids,
                results,
                error,
                run_id=run_id,
            )

        persistent_run["status"] = "publishing"
        independent_run.save_run(persistent_run)
        report(
            "working",
            "publication",
            "Erfolgreiche Untersuchungen werden veroeffentlicht",
        )
        for pending in pending_publications:
            publication = publish(
                work_item_id=work_item_id,
                participant_id=pending["participant_id"],
                content=pending["content"],
            )
            participant_result = pending["result"]
            if publication.success:
                persistent_participant = independent_run.participant_state(
                    persistent_run, pending["provider"]
                )
                persistent_participant["status"] = "published"
                persistent_participant["work_step_id"] = publication.id
                independent_run.save_run(persistent_run)
                participant_result["status"] = "completed"
                participant_result["work_step_id"] = publication.id
                continue
            persistent_participant = independent_run.participant_state(
                persistent_run, pending["provider"]
            )
            persistent_participant["status"] = "publication_failed"
            persistent_participant["error"] = (
                "Publikation nach fachlichem Abschluss fehlgeschlagen: "
                f"{publication.error}"
            )
            independent_run.save_run(persistent_run)
            participant_result["status"] = "failed"
            participant_result["error"] = (
                "Publikation nach fachlichem Abschluss fehlgeschlagen: "
                f"{publication.error}"
            )
            failures.append(participant_result)

        if failures:
            any_published = any(
                state["status"] == "published"
                for state in persistent_run["participant_states"]
            )
            persistent_run["status"] = (
                "partially_published"
                if any_published
                else "publication_failed"
            )
            independent_run.save_run(persistent_run)
            error = (
                f"{len(failures)} von {len(participants)} Teilnehmern "
                "sind fehlgeschlagen"
            )
            report("failed", "independent", error)
            return _result(
                False,
                mode,
                participants,
                snapshot_ids,
                results,
                error,
                run_id=run_id,
            )
        persistent_run["status"] = "completed"
        independent_run.save_run(persistent_run)

    else:
        phase_specs = [
            ("X", participants[0], None),
            ("Y", participants[1], REFUTATION_TASK_Y),
            ("Z", participants[2], REFUTATION_TASK_Z),
        ]
        chain_steps: list[dict] = []
        for phase, provider, additional_task in phase_specs:
            message = (
                f"{phase} ({provider}) untersucht"
                if phase == "X"
                else f"{phase} ({provider}) prueft und widerlegt"
            )
            report("working", phase, message)
            phase_snapshot = [*starting_snapshot, *chain_steps]
            step, error = _new_work_step(
                provider,
                work_item_id,
                phase_snapshot,
                additional_task=additional_task,
            )
            if error:
                failure = {
                    "provider": provider,
                    "phase": phase,
                    "status": "failed",
                    "error": error,
                }
                results.append(failure)
                message = (
                    f"Phase {phase} fehlgeschlagen; "
                    "Widerlegungskette kontrolliert abgebrochen"
                )
                report("aborted", phase, message)
                return _result(
                    False, mode, participants, snapshot_ids, results, message
                )
            chain_steps.append(step)
            results.append(_participant_result(provider, phase, step))

    report("completed", "done", "Arbeit regulär abgeschlossen")
    return _result(
        True,
        mode,
        participants,
        snapshot_ids,
        results,
        None,
        run_id=run_id,
    )


def retry_independent_participant(
    run_id: str,
    provider: str,
    runs_dir: Optional[Path] = None,
) -> dict:
    """Wiederholt genau einen fehlgeschlagenen Independent-Teilnehmer."""
    persistent_run = independent_run.load_run(run_id, runs_dir)
    if persistent_run["status"] != "incomplete":
        raise ValueError(
            "IndependentRun erlaubt keinen Teilnehmer-Retry: "
            f"{persistent_run['status']}"
        )
    if provider not in persistent_run["participants"]:
        raise ValueError(
            f"Teilnehmer gehoert nicht zum IndependentRun: {provider}"
        )
    participant = independent_run.participant_state(
        persistent_run, provider
    )
    if participant["status"] != "failed":
        raise ValueError(
            f"Teilnehmer ist nicht retryfaehig: {participant['status']}"
        )

    participant["status"] = "working"
    participant["attempt_count"] += 1
    independent_run.save_run(persistent_run, runs_dir)
    generated, error = _generate_content(
        provider,
        persistent_run["work_item_id"],
        persistent_run["original_input"]["starting_snapshot"],
    )
    if error:
        participant["status"] = "failed"
        participant["error"] = error
        persistent_run["status"] = "incomplete"
        independent_run.save_run(persistent_run, runs_dir)
        return _retry_result(
            persistent_run,
            provider,
            success=False,
            error=error,
        )

    participant["status"] = "completed_pending"
    participant["participant_id"] = generated["participant_id"]
    participant["content"] = generated["content"]
    participant["error"] = None
    independent_run.save_run(persistent_run, runs_dir)

    if any(
        state["status"] != "completed_pending"
        for state in persistent_run["participant_states"]
    ):
        persistent_run["status"] = "incomplete"
        independent_run.save_run(persistent_run, runs_dir)
        return _retry_result(
            persistent_run,
            provider,
            success=True,
            error=None,
        )

    persistent_run["status"] = "publishing"
    independent_run.save_run(persistent_run, runs_dir)
    publication_failures = []
    for state in persistent_run["participant_states"]:
        publication = publish(
            work_item_id=persistent_run["work_item_id"],
            participant_id=state["participant_id"],
            content=state["content"],
        )
        if publication.success:
            state["status"] = "published"
            state["work_step_id"] = publication.id
            independent_run.save_run(persistent_run, runs_dir)
            continue
        state["status"] = "publication_failed"
        state["error"] = (
            "Publikation nach fachlichem Abschluss fehlgeschlagen: "
            f"{publication.error}"
        )
        publication_failures.append(state)
        independent_run.save_run(persistent_run, runs_dir)

    if publication_failures:
        any_published = any(
            state["status"] == "published"
            for state in persistent_run["participant_states"]
        )
        persistent_run["status"] = (
            "partially_published"
            if any_published
            else "publication_failed"
        )
        independent_run.save_run(persistent_run, runs_dir)
        return _retry_result(
            persistent_run,
            provider,
            success=False,
            error=(
                f"{len(publication_failures)} von "
                f"{len(persistent_run['participants'])} Publikationen "
                "sind fehlgeschlagen"
            ),
        )

    persistent_run["status"] = "completed"
    independent_run.save_run(persistent_run, runs_dir)
    return _retry_result(
        persistent_run,
        provider,
        success=True,
        error=None,
    )


def _retry_result(
    persistent_run: dict,
    provider: str,
    success: bool,
    error: Optional[str],
) -> dict:
    return {
        "success": success,
        "run_id": persistent_run["run_id"],
        "work_item_id": persistent_run["work_item_id"],
        "mode": "independent",
        "retried_provider": provider,
        "status": persistent_run["status"],
        "participant_states": [
            dict(state) for state in persistent_run["participant_states"]
        ],
        "error": error,
    }


def _participant_result(provider: str, phase: str, step: dict) -> dict:
    return {
        "provider": provider,
        "phase": phase,
        "status": "completed",
        "work_step_id": step["id"],
        "participant_id": step["participant_id"],
    }


def _result(
    success: bool,
    mode: str,
    participants: list[str],
    snapshot_ids: list[str],
    results: list[dict],
    error: Optional[str],
    run_id: Optional[str] = None,
) -> dict:
    result = {
        "success": success,
        "mode": mode,
        "participants": participants,
        "starting_snapshot_ids": snapshot_ids,
        "results": results,
        "error": error,
    }
    if run_id:
        result["run_id"] = run_id
    return result


def _status_file_callback(path: Path) -> StatusCallback:
    def write_status(status: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(status, temporary, ensure_ascii=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            for attempt in range(STATUS_REPLACE_ATTEMPTS):
                try:
                    temporary_path.replace(path)
                    break
                except PermissionError:
                    if attempt == STATUS_REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(
                        STATUS_REPLACE_RETRY_SECONDS * (attempt + 1)
                    )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    return write_status


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atlas Orchestrierung V1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--work-item", required=True)
    run_parser.add_argument("--mode", required=True, choices=SUPPORTED_MODES)
    run_parser.add_argument("--participants", required=True)
    run_parser.add_argument("--status-file")
    retry_parser = subparsers.add_parser("retry-independent")
    retry_parser.add_argument("--run-id", required=True)
    retry_parser.add_argument(
        "--provider",
        required=True,
        choices=SUPPORTED_PROVIDERS,
    )
    get_parser = subparsers.add_parser("get-independent-run")
    get_parser.add_argument("--run-id", required=True)
    find_parser = subparsers.add_parser("find-incomplete-independent-run")
    find_parser.add_argument("--work-item", required=True)
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_args()
    if args.command == "retry-independent":
        try:
            result = retry_independent_participant(
                args.run_id,
                args.provider,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    if args.command == "get-independent-run":
        try:
            result = independent_run.load_run(args.run_id)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    if args.command == "find-incomplete-independent-run":
        result = independent_run.find_latest_incomplete_run(
            args.work_item
        )
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    participants = [
        value.strip()
        for value in args.participants.split(",")
        if value.strip()
    ]
    callback = (
        _status_file_callback(Path(args.status_file))
        if args.status_file
        else None
    )
    try:
        result = run(
            args.work_item,
            args.mode,
            participants,
            status_callback=callback,
        )
    except ValueError as error:
        result = _result(
            False,
            args.mode,
            participants,
            [],
            [],
            str(error),
        )
        if callback:
            callback({
                "state": "failed",
                "mode": args.mode,
                "phase": "configuration",
                "message": str(error),
                "work_item_id": args.work_item,
                "participants": participants,
                "starting_snapshot_ids": [],
                "results": [],
            })

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
