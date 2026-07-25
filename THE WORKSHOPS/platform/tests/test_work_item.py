"""
Tests fuer work_item.py (start, complete, abandon) und die
Work-Item-Abschnitte in state_generator.py.

Alle Dateizugriffe laufen ueber tmp_path - keine Seiteneffekte auf
THE VAULT/work_items/ im echten Repository.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_item import start, complete, abandon  # noqa: E402
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


def test_start_increments_id(tmp_path):
    start("Erstes", "u1", work_items_dir=tmp_path)
    result = start("Zweites", "u2", work_items_dir=tmp_path)

    assert result.id == "WI-0002"


def test_start_rejects_empty_intent(tmp_path):
    result = start("   ", "u1", work_items_dir=tmp_path)

    assert result.success is False
    assert not list(tmp_path.glob("WI-*.yaml"))


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
