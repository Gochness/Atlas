import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic_work_step  # noqa: E402
import openai_work_step  # noqa: E402


def test_build_context_includes_valid_context_file(tmp_path):
    context_file = tmp_path / "docs" / "context.txt"
    context_file.parent.mkdir()
    context_file.write_text("Belegter Dateiinhalt", encoding="utf-8")

    context = json.loads(
        openai_work_step._build_context(
            {
                "id": "WI-0001",
                "intent": "Kontext pruefen",
                "context_refs": ["docs/context.txt"],
            },
            [],
            repo_root=tmp_path,
        )
    )

    assert context["context_files"] == [
        {
            "path": "docs/context.txt",
            "content": "Belegter Dateiinhalt",
        }
    ]
    assert "Automatischer Atlas-Wissensindex" in context["atlas_knowledge_index"]


def test_build_context_provides_current_compact_index_before_first_tool_call(tmp_path):
    source = tmp_path / "THE NORTH STAR" / "PLATFORM_STATUS.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Platform Status\nAktueller Atlas-Stand", encoding="utf-8")

    context = json.loads(
        openai_work_step._build_context(
            {"id": "WI-0001", "intent": "Status untersuchen", "context_refs": []},
            [],
            repo_root=tmp_path,
        )
    )

    index = context["atlas_knowledge_index"]
    assert "dokumentation=1" in index
    assert "THE NORTH STAR/PLATFORM_STATUS.md" in index
    assert "Aktueller Atlas-Stand" not in index


def test_read_old_work_item_defaults_context_refs_to_empty(tmp_path, monkeypatch):
    path = tmp_path / "WI-0001.yaml"
    path.write_text(
        yaml.dump(
            {
                "id": "WI-0001",
                "intent": "Altbestand",
                "created_by": "test",
                "created_at": "2026-01-01T00:00:00Z",
                "base_commit": "abc",
                "status": "open",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(openai_work_step, "WORK_ITEMS_DIR", tmp_path)

    work_item = openai_work_step._read_work_item("WI-0001")

    assert work_item["context_refs"] == []


def test_invalid_context_ref_prevents_model_request_and_publish(monkeypatch):
    model_requested = False
    published = False

    def request_model(*_args):
        nonlocal model_requested
        model_requested = True
        return "Antwort"

    def publish(*_args, **_kwargs):
        nonlocal published
        published = True
        raise AssertionError("publish darf nicht aufgerufen werden")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        openai_work_step,
        "_read_work_item",
        lambda _work_item_id: {
            "id": "WI-0001",
            "intent": "Test",
            "context_refs": [r"C:\outside.txt"],
        },
    )
    monkeypatch.setattr(openai_work_step, "list_for_work_item", lambda _work_item_id: [])
    monkeypatch.setattr(openai_work_step, "_request_model", request_model)
    monkeypatch.setattr(openai_work_step, "publish", publish)

    assert openai_work_step.generate("WI-0001") == 1
    assert model_requested is False
    assert published is False


def test_anthropic_uses_shared_context_builder():
    assert anthropic_work_step._build_context is openai_work_step._build_context
