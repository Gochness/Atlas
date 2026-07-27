"""
Tests fuer work_item.py (start, complete, abandon) und die
Work-Item-Abschnitte in state_generator.py.

Alle Dateizugriffe laufen ueber tmp_path - keine Seiteneffekte auf
THE VAULT/work_items/ im echten Repository.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_item import (  # noqa: E402
    abandon,
    complete,
    list_work_items,
    read_context_files,
    resolve_repository_files,
    set_context_refs,
    start,
)
from state_generator import _load_work_items, _work_item_sections  # noqa: E402


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

def test_start_creates_work_item_with_all_fields(tmp_path):
    result = start("Testabsicht", "test-user", work_items_dir=tmp_path)

    assert result.success is True
    assert result.id == "WI-0001"

    path = tmp_path / "WI-0001.yaml"
    assert path.exists()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["id"] == "WI-0001"
    assert data["intent"] == "Testabsicht"
    assert data["created_by"] == "test-user"
    assert data["status"] == "open"
    assert data["created_at"]
    assert data["base_commit"]
    assert data["context_refs"] == []


def test_start_increments_id(tmp_path):
    start("Erstes", "u1", work_items_dir=tmp_path)
    result = start("Zweites", "u2", work_items_dir=tmp_path)

    assert result.id == "WI-0002"


def test_start_rejects_empty_intent(tmp_path):
    result = start("   ", "u1", work_items_dir=tmp_path)

    assert result.success is False
    assert not list(tmp_path.glob("WI-*.yaml"))


# ---------------------------------------------------------------------------
# context_refs
# ---------------------------------------------------------------------------

def _create_context_work_item(tmp_path):
    work_items_dir = tmp_path / "work_items"
    result = start("Kontexttest", "test-user", work_items_dir=work_items_dir)
    return result, work_items_dir


def test_list_work_items_defaults_missing_context_refs_to_empty(tmp_path):
    path = tmp_path / "WI-0001.yaml"
    path.write_text(
        "id: WI-0001\nintent: Alt\ncreated_by: test\n"
        "created_at: '2026-01-01T00:00:00Z'\nbase_commit: abc\nstatus: open\n",
        encoding="utf-8",
    )

    items = list_work_items(tmp_path)

    assert items[0]["context_refs"] == []
    assert "context_refs" not in yaml.safe_load(path.read_text(encoding="utf-8"))


def test_set_context_refs_persists_valid_reference(tmp_path):
    result, work_items_dir = _create_context_work_item(tmp_path)
    context_file = tmp_path / "docs" / "context.txt"
    context_file.parent.mkdir()
    context_file.write_text("Atlas-Kontext", encoding="utf-8")

    updated = set_context_refs(
        result.id,
        ["docs/context.txt"],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )

    assert updated.success is True
    data = yaml.safe_load((work_items_dir / f"{result.id}.yaml").read_text(encoding="utf-8"))
    assert data["context_refs"] == ["docs/context.txt"]
    assert data["intent"] == "Kontexttest"
    assert read_context_files(data["context_refs"], tmp_path) == [
        {"path": "docs/context.txt", "content": "Atlas-Kontext"}
    ]


def test_set_context_refs_rejects_absolute_path(tmp_path):
    result, work_items_dir = _create_context_work_item(tmp_path)
    target = tmp_path / "context.txt"
    target.write_text("text", encoding="utf-8")

    updated = set_context_refs(
        result.id,
        [str(target.resolve())],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )

    assert updated.success is False
    assert "Absolute" in updated.error


def test_set_context_refs_rejects_parent_escape(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result, work_items_dir = _create_context_work_item(repo_root)
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")

    updated = set_context_refs(
        result.id,
        ["../outside.txt"],
        work_items_dir=work_items_dir,
        repo_root=repo_root,
    )

    assert updated.success is False
    assert "ausserhalb" in updated.error


def test_set_context_refs_rejects_symlink_escape(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result, work_items_dir = _create_context_work_item(repo_root)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = repo_root / "outside-link.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"Symlinks auf dieser Testplattform nicht verfuegbar: {error}")

    updated = set_context_refs(
        result.id,
        ["outside-link.txt"],
        work_items_dir=work_items_dir,
        repo_root=repo_root,
    )

    assert updated.success is False
    assert "ausserhalb" in updated.error


def test_set_context_refs_rejects_missing_file(tmp_path):
    result, work_items_dir = _create_context_work_item(tmp_path)
    updated = set_context_refs(
        result.id,
        ["missing.txt"],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )
    assert updated.success is False
    assert "nicht gefunden" in updated.error


def test_set_context_refs_rejects_directory(tmp_path):
    result, work_items_dir = _create_context_work_item(tmp_path)
    (tmp_path / "docs").mkdir()
    updated = set_context_refs(
        result.id,
        ["docs"],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )
    assert updated.success is False
    assert "keine Datei" in updated.error


@pytest.mark.parametrize(
    "reference",
    [
        ".git/config",
        ".venv/config.txt",
        ".env",
        ".env.local",
        "private.key",
        "certificate.pem",
        "credentials.json",
        "client_secret.json",
    ],
)
def test_set_context_refs_rejects_sensitive_paths(tmp_path, reference):
    result, work_items_dir = _create_context_work_item(tmp_path)
    target = tmp_path / reference
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("sensitive", encoding="utf-8")

    updated = set_context_refs(
        result.id,
        [reference],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )

    assert updated.success is False
    assert "Gesperrte" in updated.error


def test_set_context_refs_rejects_non_utf8_file(tmp_path):
    result, work_items_dir = _create_context_work_item(tmp_path)
    (tmp_path / "binary.txt").write_bytes(b"\xff\xfe\x00")
    updated = set_context_refs(
        result.id,
        ["binary.txt"],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )
    assert updated.success is False
    assert "UTF-8" in updated.error


def test_set_context_refs_rejects_closed_work_item(tmp_path):
    result, work_items_dir = _create_context_work_item(tmp_path)
    complete(result.id, work_items_dir=work_items_dir)
    context_file = tmp_path / "context.txt"
    context_file.write_text("text", encoding="utf-8")

    updated = set_context_refs(
        result.id,
        ["context.txt"],
        work_items_dir=work_items_dir,
        repo_root=tmp_path,
    )

    assert updated.success is False
    assert "nicht offen" in updated.error


# ---------------------------------------------------------------------------
# repository file resolution
# ---------------------------------------------------------------------------

def test_resolve_repository_files_finds_unique_file_case_insensitively(tmp_path):
    target = tmp_path / "THE WORKSHOPS" / "platform" / "materialization_service.py"
    target.parent.mkdir(parents=True)
    target.write_text("content is not returned", encoding="utf-8")

    assert resolve_repository_files("Materialization_Service.py", tmp_path) == [
        "THE WORKSHOPS/platform/materialization_service.py"
    ]


def test_resolve_repository_files_returns_empty_for_missing_file(tmp_path):
    assert resolve_repository_files("missing.py", tmp_path) == []


def test_resolve_repository_files_returns_all_matches_sorted(tmp_path):
    for relative_path in ("zeta/shared.py", "Alpha/shared.py", "middle/shared.py"):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True)
        target.write_text("test", encoding="utf-8")

    assert resolve_repository_files("shared.py", tmp_path) == [
        "Alpha/shared.py",
        "middle/shared.py",
        "zeta/shared.py",
    ]


@pytest.mark.parametrize(
    "relative_path",
    [
        ".git/config",
        ".venv/config",
        ".env",
        ".env.local",
        "private.key",
        "certificate.pem",
        "credentials/data.json",
        "client_secret/data.json",
    ],
)
def test_resolve_repository_files_hides_sensitive_existing_files(
    tmp_path,
    relative_path,
):
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("sensitive", encoding="utf-8")

    assert resolve_repository_files(target.name, tmp_path) == []


def test_resolve_repository_files_hides_symlink_escape(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("outside", encoding="utf-8")
    link = repo_root / "outside.py"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"Symlinks auf dieser Testplattform nicht verfuegbar: {error}")

    assert resolve_repository_files("outside.py", repo_root) == []


@pytest.mark.parametrize(
    "filename",
    ["", " ", "../file.py", "folder/file.py", r"folder\file.py", "*.py", "file?.py"],
)
def test_resolve_repository_files_rejects_non_exact_filename(tmp_path, filename):
    with pytest.raises(ValueError):
        resolve_repository_files(filename, tmp_path)


def test_resolve_repository_files_does_not_mutate_repository(tmp_path):
    work_item = tmp_path / "THE VAULT" / "work_items" / "WI-0001.yaml"
    work_step = tmp_path / "THE VAULT" / "work_steps" / "WS-0001.yaml"
    candidate = tmp_path / "docs" / "context.txt"
    for path, content in (
        (work_item, "work item"),
        (work_step, "work step"),
        (candidate, "context"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert resolve_repository_files("context.txt", tmp_path) == ["docs/context.txt"]
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert after == before


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------

def test_complete_transitions_open_to_completed(tmp_path):
    s = start("Absicht", "u1", work_items_dir=tmp_path)

    result = complete(s.id, work_items_dir=tmp_path)

    assert result.success is True
    assert result.status == "completed"
    data = yaml.safe_load((tmp_path / f"{s.id}.yaml").read_text(encoding="utf-8"))
    assert data["status"] == "completed"


def test_complete_nonexistent_fails(tmp_path):
    result = complete("WI-9999", work_items_dir=tmp_path)

    assert result.success is False
    assert "nicht gefunden" in result.error


def test_double_complete_fails(tmp_path):
    s = start("Absicht", "u1", work_items_dir=tmp_path)

    first = complete(s.id, work_items_dir=tmp_path)
    second = complete(s.id, work_items_dir=tmp_path)

    assert first.success is True
    assert second.success is False
    assert "bereits abgeschlossen" in second.error
    # Status bleibt "completed", wird durch den fehlgeschlagenen zweiten
    # Versuch nicht ueberschrieben oder korrumpiert.
    data = yaml.safe_load((tmp_path / f"{s.id}.yaml").read_text(encoding="utf-8"))
    assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# abandon
# ---------------------------------------------------------------------------

def test_abandon_transitions_open_to_abandoned(tmp_path):
    s = start("Absicht", "u1", work_items_dir=tmp_path)

    result = abandon(s.id, work_items_dir=tmp_path)

    assert result.success is True
    assert result.status == "abandoned"


def test_abandon_after_complete_fails(tmp_path):
    s = start("Absicht", "u1", work_items_dir=tmp_path)
    complete(s.id, work_items_dir=tmp_path)

    result = abandon(s.id, work_items_dir=tmp_path)

    assert result.success is False
    data = yaml.safe_load((tmp_path / f"{s.id}.yaml").read_text(encoding="utf-8"))
    assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# state_generator: Laden und Formatierung
# ---------------------------------------------------------------------------

def test_load_work_items_reads_from_directory(tmp_path):
    start("Erstes", "u1", work_items_dir=tmp_path)
    start("Zweites", "u2", work_items_dir=tmp_path)

    items = _load_work_items(tmp_path)

    assert len(items) == 2
    assert {i["id"] for i in items} == {"WI-0001", "WI-0002"}


def test_load_work_items_empty_dir_returns_empty_list(tmp_path):
    assert _load_work_items(tmp_path / "does-not-exist") == []


def test_work_item_sections_categorizes_by_status():
    items = [
        {"id": "WI-0001", "status": "open", "created_by": "a", "intent": "offen", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "WI-0002", "status": "in_progress", "created_by": "b", "intent": "aktiv", "created_at": "2026-01-02T00:00:00Z"},
        {"id": "WI-0003", "status": "completed", "created_by": "c", "intent": "fertig", "created_at": "2026-01-03T00:00:00Z"},
        {"id": "WI-0004", "status": "abandoned", "created_by": "d", "intent": "verworfen", "created_at": "2026-01-04T00:00:00Z"},
    ]

    lines = _work_item_sections(items)
    text = "\n".join(lines)

    assert "## Work Items – Offen" in text
    assert "WI-0001" in text
    assert "## Work Items – Aktiv (status: in_progress)" in text
    assert "WI-0002" in text
    assert "## Work Items – Abgeschlossen" in text
    assert "WI-0003" in text
    assert "WI-0004" in text
    assert "## Aktuelle Teilnehmer" in text
    assert "- b" in text  # nur der Teilnehmer des aktiven (in_progress) Items
    assert "- a" not in text.split("## Aktuelle Teilnehmer")[1].split("## Activity Stream")[0]


def test_work_item_sections_activity_stream_sorted_newest_first():
    items = [
        {"id": "WI-0001", "status": "open", "created_by": "a", "intent": "alt", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "WI-0002", "status": "open", "created_by": "b", "intent": "neu", "created_at": "2026-01-05T00:00:00Z"},
    ]

    lines = _work_item_sections(items)
    stream = "\n".join(lines).split("## Activity Stream")[1]

    assert stream.index("WI-0002") < stream.index("WI-0001")


def test_work_item_sections_no_in_progress_items_is_empty():
    """
    Aktuelle work_item.py-Befehle (start/complete/abandon) setzen nie
    status=in_progress. Diese Kategorie und die Teilnehmerliste sind
    mit dem heutigen Befehlsumfang daher immer leer.
    """
    items = [
        {"id": "WI-0001", "status": "open", "created_by": "a", "intent": "x", "created_at": "2026-01-01T00:00:00Z"},
    ]

    lines = _work_item_sections(items)
    text = "\n".join(lines)

    assert "(keine aktiven Work Items)" in text
    assert "(keine aktiven Teilnehmer)" in text


def test_work_item_sections_empty_input():
    lines = _work_item_sections([])
    text = "\n".join(lines)

    assert "(keine offenen Work Items)" in text
    assert "(keine aktiven Work Items)" in text
    assert "(keine abgeschlossenen Work Items)" in text
    assert "(keine aktiven Teilnehmer)" in text
    assert "(keine Work-Item-Ereignisse)" in text


# ---------------------------------------------------------------------------
# End-to-End: work_item.py -> state_generator.py Zusammenspiel
# ---------------------------------------------------------------------------

def test_end_to_end_work_items_flow_into_state_generator(tmp_path):
    s1 = start("Wird fertig", "u1", work_items_dir=tmp_path)
    s2 = start("Wird abgebrochen", "u2", work_items_dir=tmp_path)
    s3 = start("Bleibt offen", "u3", work_items_dir=tmp_path)

    complete(s1.id, work_items_dir=tmp_path)
    abandon(s2.id, work_items_dir=tmp_path)

    items = _load_work_items(tmp_path)
    lines = _work_item_sections(items)
    text = "\n".join(lines)

    offen_block = text.split("## Work Items – Offen")[1].split("## Work Items – Aktiv")[0]
    abgeschlossen_block = text.split("## Work Items – Abgeschlossen")[1].split("## Aktuelle Teilnehmer")[0]

    assert s3.id in offen_block
    assert s1.id not in offen_block
    assert s1.id in abgeschlossen_block
    assert s2.id in abgeschlossen_block
